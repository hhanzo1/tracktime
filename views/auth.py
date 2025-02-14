from flask import (
    render_template, request, redirect, url_for, 
    flash, session, current_app
)
from models import db, OTP, Registration
from utils import (
    send_otp_email, generate_otp,
    send_registration_notification, send_admin_notification
)
from datetime import datetime, timedelta
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def log_auth_event(email, event_type, status, details=None, request=None):
    """Log authentication events"""
    try:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) if request else 'unknown'
        user_agent = request.headers.get('User-Agent', 'unknown') if request else 'unknown'
        logger.info(f"Auth event: {email} - {event_type} - {status} - IP: {ip_address}")
    except Exception as e:
        logger.error(f"Failed to log auth event: {str(e)}")

def register_auth_routes(app):
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email', '').lower().strip()
            
            # Validate email format
            if not email or '@' not in email:
                log_auth_event(email, 'LOGIN_ATTEMPT', 'FAILED', 
                             'Invalid email format', request)
                flash('Invalid email format', 'error')
                return redirect(url_for('login'))
            
            # Check if user is approved
            user = Registration.query.filter_by(
                email=email,
                status='approved'
            ).first()
            
            if not user:
                log_auth_event(email, 'LOGIN_ATTEMPT', 'FAILED', 
                             'Email not authorized', request)
                flash('Invalid email or not authorized', 'error')
                return redirect(url_for('login'))
            
            try:
                # Generate and store OTP
                otp = generate_otp()
                expires_at = datetime.utcnow() + timedelta(minutes=10)
                
                # Invalidate any existing unused OTPs
                OTP.query.filter_by(email=email, is_used=False).update({'is_used': True})
                
                new_otp = OTP(
                    email=email,
                    otp_code=otp,
                    expires_at=expires_at
                )
                db.session.add(new_otp)
                db.session.commit()
                
                # Send OTP email
                if send_otp_email(email, otp, name=user.name):
                    session['pending_email'] = email
                    session['login_attempts'] = 0
                    log_auth_event(email, 'LOGIN_ATTEMPT', 'SUCCESS', 
                                 'OTP sent successfully', request)
                    return redirect(url_for('verify_otp'))
                else:
                    raise Exception("Failed to send OTP email")
                    
            except Exception as e:
                logger.error(f"Login error: {str(e)}")
                log_auth_event(email, 'LOGIN_ATTEMPT', 'FAILED', 
                             f'Error: {str(e)}', request)
                flash('An error occurred during login. Please try again.', 'error')
                return redirect(url_for('login'))
                
        return render_template('auth/login.html')

    @app.route('/verify-otp', methods=['GET', 'POST'])
    def verify_otp():
        if 'pending_email' not in session:
            return redirect(url_for('login'))
            
        email = session['pending_email']
        
        if request.method == 'POST':        
            otp_input = request.form.get('otp', '').strip()
            
            # Validate OTP format
            if not otp_input.isdigit() or len(otp_input) != 6:
                log_auth_event(email, 'OTP_VERIFY', 'FAILED', 
                             'Invalid OTP format', request)
                flash('Invalid OTP format', 'error')
                return render_template('auth/verify_otp.html')
            
            # Verify OTP
            valid_otp = OTP.query.filter_by(
                email=email,
                otp_code=otp_input,
                is_used=False
            ).first()
            
            if valid_otp and valid_otp.expires_at > datetime.utcnow():
                valid_otp.is_used = True
                db.session.commit()
                
                session.pop('pending_email', None)
                session['email'] = email
                session.permanent = True
                
                log_auth_event(email, 'OTP_VERIFY', 'SUCCESS', 
                             'Login successful', request)
                flash('Successfully logged in!', 'success')
                return redirect(url_for('index'))
            else:
                log_auth_event(email, 'OTP_VERIFY', 'FAILED', 
                             'Invalid or expired OTP', request)
                flash('Invalid or expired OTP', 'error')
                
        return render_template('auth/verify_otp.html')

    @app.route('/logout')
    def logout():
        if 'email' in session:
            log_auth_event(session['email'], 'LOGOUT', 'SUCCESS', 
                         'User logged out', request)
        session.clear()
        flash('Logged out successfully', 'success')
        return redirect(url_for('login'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        # Check registration limit
        total_registrations = Registration.query.filter(
            Registration.status.in_(['approved', 'pending'])
        ).count()
        
        if total_registrations >= 10:
            flash('Registration is currently closed as maximum capacity has been reached.', 'info')
            return render_template('auth/register.html', registration_closed=True)
            
        if request.method == 'POST':
            email = request.form.get('email', '').lower().strip()
            name = request.form.get('name', '').strip()
            
            if not email or not name:
                flash('Please provide both email and name', 'error')
                return redirect(url_for('register'))
            
            # Check if email is already registered
            if Registration.query.filter_by(
                email=email, 
                status='approved'
            ).first():
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            
            # Check if already pending
            if Registration.query.filter_by(
                email=email, 
                status='pending'
            ).first():
                flash('Your registration is already pending approval', 'info')
                return redirect(url_for('register'))

            try:
                # Generate and store OTP
                otp_code = generate_otp()
                expiry_time = datetime.utcnow() + timedelta(minutes=10)
                
                new_otp = OTP(
                    email=email,
                    otp_code=otp_code,
                    expires_at=expiry_time
                )
                
                db.session.add(new_otp)
                db.session.commit()
                
                # Send OTP email
                if send_otp_email(email, otp_code, name):
                    session['pending_registration'] = {
                        'email': email,
                        'name': name
                    }
                    return redirect(url_for('verify_registration_otp'))
                else:
                    flash('Failed to send OTP email. Please try again.', 'error')
                    return redirect(url_for('register'))
                    
            except Exception as e:
                db.session.rollback()
                logger.error(f"Registration error: {str(e)}")
                flash('An error occurred. Please try again.', 'error')
                return redirect(url_for('register'))
                
        return render_template('auth/register.html', registration_closed=False)

    @app.route('/verify-registration', methods=['GET', 'POST'])
    def verify_registration_otp():
        if 'pending_registration' not in session:
            return redirect(url_for('register'))
            
        if request.method == 'POST':
            entered_otp = request.form.get('otp', '').strip()
            email = session['pending_registration']['email']
            name = session['pending_registration']['name']
            
            # Verify OTP
            otp_record = OTP.query.filter_by(
                email=email,
                otp_code=entered_otp,
                is_used=False
            ).first()
            
            if otp_record and datetime.utcnow() <= otp_record.expires_at:
                try:
                    # Mark OTP as used
                    otp_record.is_used = True
                    
                    # Create pending registration
                    pending_reg = Registration(
                        email=email,
                        name=name,
                        status='pending',
                        is_admin=False  # Ensure new registrations aren't admin by default
                    )
                    
                    db.session.add(pending_reg)
                    db.session.commit()

                    # Send notifications
                    send_registration_notification(pending_reg)
                    send_admin_notification(pending_reg)
                    
                    # Clear session
                    session.pop('pending_registration', None)
                    
                    flash('Email verified! Your registration is pending approval.', 'success')
                    return redirect(url_for('login'))
                    
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Registration verification error: {str(e)}")
                    flash('An error occurred during registration. Please try again.', 'error')
            else:
                flash('Invalid or expired OTP. Please try again.', 'error')
                
        return render_template('auth/verify_registration.html')