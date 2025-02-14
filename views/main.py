from flask import (
    app, render_template, request, redirect, url_for, 
    flash, session, Response
)
from models import Registration, db, CheckIn
from utils import validate_duration, send_notification
from datetime import datetime, timedelta
import csv
import io
from functools import wraps
import logging

from datetime import datetime, timedelta
from flask import jsonify, request, flash, redirect, url_for, render_template
from models import CheckIn, CheckInStatus

logger = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current user from database"""
    if 'email' not in session:
        return None
    return Registration.query.filter_by(
        email=session['email'],
        status='approved'
    ).first()

def register_main_routes(app):

    # Get timezone from app config
    TIMEZONE = app.config['TIMEZONE']

    from datetime import datetime, timedelta
    from enum import Enum

    @app.route('/')
    @login_required
    def index():
        from weather import get_weather
        
        # Get current time in the configured timezone
        now = datetime.now(TIMEZONE)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
        try:
            weather_data = get_weather()
        except Exception as e:
            app.logger.error(f"Failed to fetch weather data: {e}")
            weather_data = None
    
        # Fetch all today's check-ins without filtering by status
        upcoming_checkins = CheckIn.query\
            .filter(
                CheckIn.start_time >= today_start
            )\
            .order_by(CheckIn.start_time.asc())\
            .all()
    
        return render_template(
            'index.html',
            weather=weather_data,
            checkins=upcoming_checkins,
            now=now,
            duration=timedelta,
            CheckInStatus=CheckInStatus
        )

    @app.route('/checkin', methods=['GET', 'POST'])
    @login_required
    def checkin():
        user = get_current_user()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('index'))

        if request.method == 'POST':
            try:
                start_date = request.form['start_date']
                start_time = request.form['start_time']
                datetime_str = f"{start_date} {start_time}"

                start_time = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                start_time = TIMEZONE.localize(start_time)

                is_valid, duration_result = validate_duration(request.form['duration'])
                if not is_valid:
                    flash(duration_result, 'error')
                    return redirect(url_for('checkin'))

                # Create checkin with notify status
                notify = 'notify' in request.form
                checkin = CheckIn(
                    name=user.name,
                    start_time=start_time,
                    duration=duration_result,
                    notify=notify  # Save notify status
                )
                db.session.add(checkin)
                db.session.commit()

                if notify:  # Use the same notify variable
                    formatted_time = start_time.strftime('%I:%M %p')
                    formatted_date = start_time.strftime('%Y-%m-%d')
                    send_notification(
                        f'A driver has checked in on {formatted_date} {formatted_time} for {duration_result} hours'
                    )

                flash('Check-In successful!', 'success')
                return redirect(url_for('index'))

            except ValueError as e:
                flash('Invalid date/time format', 'error')
                return redirect(url_for('checkin'))
            except Exception as e:
                logger.error(f"Check-in error: {str(e)}")
                db.session.rollback()
                flash('An error occurred during check-in', 'error')
                return redirect(url_for('checkin'))

        recent_checkins = CheckIn.query.order_by(CheckIn.start_time.desc()).limit(25)
        return render_template('checkin.html', 
                             checkins=recent_checkins,
                             now=datetime.now(TIMEZONE),
                             user_name=user.name,
                             CheckInStatus=CheckInStatus)
    
    @app.route('/checkin/<int:id>/edit', methods=['GET', 'POST', 'PUT'])
    @login_required
    def edit_checkin(id):
        user = get_current_user()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('index'))
    
        checkin = CheckIn.query.get_or_404(id)
    
        if checkin.name != user.name:
            flash('You can only edit your own check-ins', 'error')
            return redirect(url_for('index'))
    
        # Handle status update (PUT request)
        if request.method == 'PUT':
            try:
                data = request.get_json()
                new_status = data.get('status')
    
                if new_status not in [status.value for status in CheckInStatus]:
                    return jsonify({'error': 'Invalid status'}), 400
    
                # Update status
                new_status = new_status.upper()  # Ensure uppercase for enum
                checkin.status = CheckInStatus[new_status]
                checkin.confirmed_at = datetime.now(TIMEZONE) if new_status == 'CONFIRMED' else None
    
                # Send notification if enabled
                if checkin.notify:
                    formatted_time = checkin.start_time.strftime('%I:%M %p')
                    formatted_date = checkin.start_time.strftime('%Y-%m-%d')
                    if new_status == 'CONFIRMED':
                        send_notification(
                            f'Driver has confirmed arrival for {formatted_date} {formatted_time} check-in'
                        )
                    elif new_status == 'CANCELLED':
                        send_notification(
                            f'Driver has cancelled their {formatted_date} {formatted_time} check-in'
                        )
    
                db.session.commit()
    
                return jsonify({
                    'id': checkin.id,
                    'status': checkin.status.value,
                    'confirmed_at': checkin.confirmed_at.isoformat() if checkin.confirmed_at else None
                })
    
            except Exception as e:
                db.session.rollback()
                logger.error(f"Status update error: {str(e)}")
                return jsonify({'error': 'Internal server error'}), 500
    
        # Handle edit form submission (POST request)
        if request.method == 'POST':
            try:
                start_date = request.form['start_date']
                start_time = request.form['start_time']
                datetime_str = f"{start_date} {start_time}"
    
                new_start_time = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                new_start_time = TIMEZONE.localize(new_start_time)
    
                is_valid, duration_result = validate_duration(request.form['duration'])
                if not is_valid:
                    flash(duration_result, 'error')
                    return redirect(url_for('edit_checkin', id=id))
    
                # Update notify status
                checkin.notify = 'notify' in request.form
                
                # Check if time or duration has changed
                time_changed = checkin.start_time != new_start_time
                duration_changed = checkin.duration != duration_result
    
                # Update the values
                checkin.start_time = new_start_time
                checkin.duration = duration_result
    
                if time_changed or duration_changed:
                    # Reset status to pending
                    checkin.status = CheckInStatus.PENDING
                    checkin.confirmed_at = None
                    
                    # Send notification if enabled and there were changes
                    if checkin.notify:
                        formatted_time = new_start_time.strftime('%I:%M %p')
                        formatted_date = new_start_time.strftime('%Y-%m-%d')
                        changes = []
                        if time_changed:
                            changes.append("time")
                        if duration_changed:
                            changes.append("duration")
                        change_text = " and ".join(changes)
                        send_notification(
                            f'Check-in {change_text} updated for {formatted_date} {formatted_time}'
                        )
    
                db.session.commit()
                flash('Check-In updated successfully!', 'success')
                return redirect(url_for('index'))
    
            except ValueError:
                flash('Invalid date/time format', 'error')
            except Exception as e:
                logger.error(f"Edit check-in error: {str(e)}")
                db.session.rollback()
                flash('An error occurred while updating check-in', 'error')
                return redirect(url_for('edit_checkin', id=id))
    
        # GET request - render edit form
        return render_template('edit_checkin.html',
                             checkin=checkin,
                             now=datetime.now(TIMEZONE))    
    
    @app.route('/checkin/<int:id>/delete', methods=['POST'])
    @login_required
    def delete_checkin(id):
        user = get_current_user()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('index'))

        checkin = CheckIn.query.get_or_404(id)

        if checkin.name != user.name:
            flash('You can only delete your own check-ins', 'error')
            return redirect(url_for('index'))

        try:
            db.session.delete(checkin)
            db.session.commit()
            flash('Check-in deleted successfully!', 'success')
        except Exception as e:
            logger.error(f"Delete check-in error: {str(e)}")
            db.session.rollback()
            flash('An error occurred while deleting check-in', 'error')

        return redirect(url_for('checkin'))

    @app.route('/checkin/export', methods=['GET'])
    @login_required
    def export_checkins():
        user = get_current_user()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('index'))
        
        checkins = CheckIn.query\
            .filter_by(name=user.name)\
            .order_by(CheckIn.start_time.desc())\
            .all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Date', 'Start Time', 'Duration (hours)'])
        
        for checkin in checkins:
            writer.writerow([
                checkin.start_time.strftime('%Y-%m-%d'),
                checkin.start_time.strftime('%I:%M %p'),
                checkin.duration
            ])
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': 
                f'attachment; filename=checkins_{user.name}_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        )

    @app.route('/stats')
    @login_required
    def stats():
        now = datetime.now(TIMEZONE)
    
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_day - timedelta(days=start_of_day.weekday())
        start_of_month = start_of_day.replace(day=1)
    
        # Get registered drivers count
        registered_drivers = Registration.query.filter_by(status='approved').count()
    
        # Get hourly activity data for the past 30 days
        thirty_days_ago = now - timedelta(days=30)
        hourly_activity = (
            db.session.query(
                db.func.extract('hour', CheckIn.start_time).label('hour'),
                db.func.count(CheckIn.id).label('count')
            )
            .filter(CheckIn.start_time >= thirty_days_ago)
            .group_by(db.func.extract('hour', CheckIn.start_time))
            .order_by('hour')
            .all()
        )
    
        # Format hourly data with all hours represented
        hourly_data = {hour: 0 for hour in range(24)}
        for hour, count in hourly_activity:
            hourly_data[int(hour)] = count
        
        hourly_activity_list = [
            {"hour": hour, "count": count} 
            for hour, count in hourly_data.items()
        ]

        stats = {
            'overall': get_period_stats(),
            'today': get_period_stats(start_time=start_of_day),
            'this_week': get_period_stats(start_time=start_of_week),
            'this_month': get_period_stats(start_time=start_of_month),
            'registered_drivers': registered_drivers,
            'hourly_activity': hourly_activity_list
        }
        
        stats['top_duration'] = get_top_stats('duration')
        stats['top_frequency'] = get_top_stats('frequency')
        
        return render_template('stats.html', stats=stats)
    
    @app.route('/faq')
    def faq():
        return render_template('faq.html')

def get_period_stats(start_time=None):
    query = db.session.query(
        CheckIn.name,
        db.func.count(CheckIn.id).label('check_in_count'),
        db.func.sum(CheckIn.duration).label('total_duration'),
        db.func.avg(CheckIn.duration).label('avg_duration'),
        db.func.max(CheckIn.start_time).label('latest_check_in')
    ).group_by(CheckIn.name)
    
    if start_time:
        query = query.filter(CheckIn.start_time >= start_time)
    
    stats = query.all()
    
    return [{
        'name': stat.name,
        'count': stat.check_in_count,
        'total_duration': round(stat.total_duration, 2) if stat.total_duration else 0,
        'avg_duration': round(stat.avg_duration, 2) if stat.avg_duration else 0,
        'latest_check_in': stat.latest_check_in.strftime('%Y-%m-%d %H:%M') if stat.latest_check_in else None
    } for stat in stats]

def get_top_stats(metric, limit=5):
    if metric == 'duration':
        query = db.session.query(
            CheckIn.name,
            db.func.sum(CheckIn.duration).label('total_duration')
        ).group_by(CheckIn.name).order_by(db.desc('total_duration')).limit(limit)
        
        return [{
            'name': stat.name,
            'value': round(stat.total_duration, 2)
        } for stat in query.all()]
    
    elif metric == 'frequency':
        query = db.session.query(
            CheckIn.name,
            db.func.count(CheckIn.id).label('check_in_count')
        ).group_by(CheckIn.name).order_by(db.desc('check_in_count')).limit(limit)
        
        return [{
            'name': stat.name,
            'value': stat.check_in_count
        } for stat in query.all()]
    