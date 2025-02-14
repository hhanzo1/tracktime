from flask import (
    render_template, request, redirect, url_for, 
    flash, session
)
from models import db, CheckIn, Registration, CheckInStatus
from datetime import datetime
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('login'))
            
        user = Registration.query.filter_by(
            email=session['email'],
            status='approved'
        ).first()
        
        if not user or not user.is_admin:
            flash('Unauthorized access', 'error')
            return redirect(url_for('index'))
            
        return f(*args, **kwargs)
    return decorated_function

def register_admin_routes(app):
    # Get timezone from app config
    TIMEZONE = app.config['TIMEZONE']

    @app.route('/approve-registrations')
    @admin_required
    def approve_registrations():
        try:
            pending_registrations = Registration.query\
                .filter_by(status='pending')\
                .all()
            return render_template(
                'admin/approve_registrations.html', 
                registrations=pending_registrations
            )
        except Exception as e:
            flash('Error loading registrations', 'error')
            logger.error(f"Error loading registrations: {str(e)}")
            return redirect(url_for('index'))

    @app.route('/process-registration/<int:reg_id>/<action>')
    @admin_required
    def process_registration(reg_id, action):
        registration = Registration.query.get_or_404(reg_id)
        
        if action == 'approve':
            try:
                registration.status = 'approved'
                db.session.commit()
                
                # Send approval notification
                from utils import send_approval_notification
                if send_approval_notification(registration):
                    flash(f'Registration approved and notification sent to {registration.email}', 'success')
                else:
                    flash(f'Registration approved but failed to send notification to {registration.email}', 'warning')
                    
            except Exception as e:
                logger.error(f"Failed to approve registration: {str(e)}")
                flash('Failed to approve registration', 'error')
                
        elif action == 'reject':
            try:
                registration.status = 'rejected'
                db.session.commit()
                
                # Send rejection notification
                from utils import send_rejection_notification
                if send_rejection_notification(registration):
                    flash(f'Registration rejected and notification sent to {registration.email}', 'info')
                else:
                    flash(f'Registration rejected but failed to send notification to {registration.email}', 'warning')
            except Exception as e:
                logger.error(f"Failed to reject registration: {str(e)}")
                flash('Failed to reject registration', 'error')
        
        return redirect(url_for('approve_registrations'))

    @app.route('/accounts')
    @admin_required
    def accounts():
        accounts = Registration.query.all()
        return render_template('admin/accounts.html', accounts=accounts)
    
    @app.route('/accounts/<int:id>/edit', methods=['GET'])
    @admin_required
    def edit_account(id):
        account = Registration.query.get_or_404(id)
        return render_template('admin/edit_account.html', account=account)
    
    @app.route('/accounts/<int:id>/update', methods=['POST'])
    @admin_required
    def update_account(id):
        account = Registration.query.get_or_404(id)
        
        if not request.form.get('email') or not request.form.get('name'):
            flash('Email and name are required', 'error')
            return redirect(url_for('edit_account', id=id))
        
        try:
            account.email = request.form.get('email')
            account.name = request.form.get('name')
            account.status = request.form.get('status')
            account.is_admin = request.form.get('is_admin') == '1'
            
            # Prevent removing own admin access
            if session['email'] == account.email and not account.is_admin:
                flash('Cannot remove your own admin access', 'error')
                return redirect(url_for('edit_account', id=id))
            
            db.session.commit()
            flash('Account updated successfully', 'success')
            return redirect(url_for('accounts'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating account: {str(e)}")
            flash(f'Error updating account: {str(e)}', 'error')
            return redirect(url_for('edit_account', id=id))

    @app.route('/accounts/<int:id>/delete', methods=['POST'])
    @admin_required
    def delete_account(id):
        account = Registration.query.get_or_404(id)
        
        # Prevent self-deletion or root account deletion
        if session['email'] == account.email:
            flash('Cannot delete your own account', 'error')
            return redirect(url_for('accounts'))
            
        if account.is_admin:
            flash('Cannot delete admin accounts', 'error')
            return redirect(url_for('accounts'))
        
        try:
            db.session.delete(account)
            db.session.commit()
            flash('Account deleted successfully', 'success')
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting account: {str(e)}")
            flash(f'Error deleting account: {str(e)}', 'error')
        
        return redirect(url_for('accounts'))

    @app.route('/admin_checkins', methods=['GET'])
    @admin_required
    def admin_checkins():
        # Get filter parameters
        name_filter = request.args.get('name', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        status_filter = request.args.get('status', '')
        
        # Base query
        query = CheckIn.query
        
        # Apply filters
        if name_filter:
            query = query.filter(CheckIn.name.ilike(f'%{name_filter}%'))
        
        if status_filter:
            query = query.filter(CheckIn.status == status_filter)
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d')
                date_from = TIMEZONE.localize(date_from)
                query = query.filter(CheckIn.start_time >= date_from)
            except ValueError:
                flash('Invalid from date format', 'error')
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d')
                date_to = TIMEZONE.localize(date_to)
                query = query.filter(CheckIn.start_time <= date_to)
            except ValueError:
                flash('Invalid to date format', 'error')
        
        # Get results
        checkins = query.order_by(CheckIn.start_time.desc()).all()
        total_hours = sum(checkin.duration for checkin in checkins)
        
        return render_template('admin/admin_checkins.html',
                             checkins=checkins,
                             name_filter=name_filter,
                             date_from=date_from,
                             date_to=date_to,
                             status_filter=status_filter,
                             total_hours=total_hours,
                             CheckInStatus=CheckInStatus)

    @app.route('/admin_checkins/<int:id>/edit', methods=['GET', 'POST'])
    @admin_required
    def admin_checkins_edit(id):
        checkin = CheckIn.query.get_or_404(id)
        
        if request.method == 'POST':
            try:
                # Parse and validate the new date/time
                start_date = request.form['start_date']
                start_time = request.form['start_time']
                datetime_str = f"{start_date} {start_time}"
                
                new_start_time = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                new_start_time = TIMEZONE.localize(new_start_time)
                
                # Validate duration
                from utils import validate_duration
                is_valid, duration_result = validate_duration(request.form['duration'])
                if not is_valid:
                    flash(duration_result, 'error')
                    return redirect(url_for('admin_checkins_edit', id=id))

                # Update the check-in
                checkin.name = request.form['name']
                checkin.start_time = new_start_time
                checkin.duration = duration_result
                db.session.commit()

                flash('Check-In updated successfully!', 'success')
                return redirect(url_for('admin_checkins'))
                
            except ValueError:
                flash('Invalid date/time format', 'error')
            except Exception as e:
                logger.error(f"Admin edit check-in error: {str(e)}")
                db.session.rollback()
                flash('An error occurred while updating check-in', 'error')
        
        return render_template('admin/admin_checkins_edit.html',
                             checkin=checkin,
                             now=datetime.now(TIMEZONE))

    @app.route('/admin_checkins/<int:id>/delete', methods=['POST'])
    @admin_required
    def admin_checkins_delete(id):
        checkin = CheckIn.query.get_or_404(id)
        
        try:
            db.session.delete(checkin)
            db.session.commit()
            flash('Check-in deleted successfully!', 'success')
        except Exception as e:
            logger.error(f"Admin delete check-in error: {str(e)}")
            db.session.rollback()
            flash('An error occurred while deleting check-in', 'error')
        
        return redirect(url_for('admin_checkins'))

    # Register context processor for admin templates
    @app.context_processor
    def inject_admin_status():
        if 'email' in session:
            user = Registration.query.filter_by(
                email=session['email'],
                status='approved'
            ).first()
            return dict(is_admin=bool(user and user.is_admin))
        return dict(is_admin=False)

    return app