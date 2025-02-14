import logging
import secrets
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import current_app
from typing import Tuple, Dict, Optional, Union
from functools import wraps
from flask import session, redirect, url_for, flash
from models import Registration

logger = logging.getLogger(__name__)

def login_required(f):
    """Decorator to protect routes that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def validate_duration(duration: str) -> Tuple[bool, Union[float, str]]:
    """
    Validate check-in duration.
    
    Args:
        duration: String representing the duration in hours
    
    Returns:
        Tuple of (is_valid, result)
        - If valid: (True, float_duration)
        - If invalid: (False, error_message)
    """
    try:
        duration = float(duration)
        if duration <= 0 or duration > 24:
            return False, "Duration must be between 0 and 24 hours"
        return True, duration
    except ValueError:
        return False, "Invalid duration format"

def mask_email(email: str) -> str:
    """
    Mask email address for logging purposes.
    Example: john.doe@example.com -> joh***@example.com
    """
    try:
        username, domain = email.split('@')
        masked_username = username[:3] + '***' if len(username) > 3 else username + '***'
        return f"{masked_username}@{domain}"
    except:
        return "invalid_email"

def generate_otp() -> str:
    """Generate a 6-digit OTP"""
    return ''.join(secrets.choice('0123456789') for _ in range(6))

def send_notification(message: str) -> None:
    """Send notification using NTFY"""
    if not current_app.config.get('NTFY_ENDPOINT'):
        logger.warning("NTFY endpoint not configured")
        return
    
    if not current_app.config.get('NTFY_TOKEN'):
        logger.warning("NTFY token not configured")
        return
    
    try:
        response = requests.post(
            current_app.config['NTFY_ENDPOINT'],
            data=message.encode(encoding='utf-8'),
            headers={
                'Title': 'Driver Check-In',
                'Authorization': f'Bearer {current_app.config["NTFY_TOKEN"]}',
                'Priority': '3',
                'Tags': 'checkered_flag',
                'Click': 'https://tracktime.yourdomain.com'
            },
            timeout=5
        )
        response.raise_for_status()
        logger.info(f"Notification sent successfully: {message}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send notification: {str(e)}")

def send_email(to_email: str, subject: str, body: str, is_html: bool = False) -> bool:
    """
    Send an email using SMTP configuration.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body content
        is_html: Whether the body contains HTML content
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = current_app.config['DEFAULT_SENDER']
        msg['To'] = to_email
        msg['Subject'] = subject

        # If HTML email, attach both plain text and HTML versions
        if is_html:
            # Create plain text version by stripping HTML
            plain_text = body.replace('<p>', '\n').replace('</p>', '\n')
            plain_text = plain_text.replace('<br>', '\n').replace('<br/>', '\n')
            plain_text = ' '.join(plain_text.split())  # Normalize whitespace
            
            # Remove other HTML tags
            while '<' in plain_text and '>' in plain_text:
                start = plain_text.find('<')
                end = plain_text.find('>', start) + 1
                if start != -1 and end != -1:
                    plain_text = plain_text[:start] + plain_text[end:]
            
            msg.attach(MIMEText(plain_text, 'plain'))
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(
            current_app.config['SMTP_SERVER'], 
            current_app.config['SMTP_PORT']
        ) as server:
            server.starttls()
            server.login(
                current_app.config['SMTP_USERNAME'],
                current_app.config['SMTP_PASSWORD']
            )
            server.send_message(msg)
            
        logger.info(f"Email sent successfully to {mask_email(to_email)}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {mask_email(to_email)}: {str(e)}")
        return False

def send_otp_email(email: str, otp: str, name: Optional[str] = None) -> bool:
    """Send OTP verification email"""
    subject = 'Your Track Time Authentication Code'
    greeting = f"Hello {name}" if name else "Hello"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #333333; font-size: 24px; margin: 0 0 20px; text-align: center;">Authentication Code</h1>
            
            <p style="color: #555555; margin-bottom: 20px;">{greeting},</p>
            
            <div style="background-color: #f8f9fa; border-radius: 6px; padding: 20px; margin: 30px 0; text-align: center;">
                <p style="color: #333333; font-size: 32px; font-family: monospace; letter-spacing: 4px; margin: 0;">{otp}</p>
            </div>
            
            <p style="color: #555555; margin-bottom: 10px;">This code will expire in 10 minutes.</p>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center;">
                <p style="color: #888888; font-size: 14px; margin-bottom: 10px;">Best regards,<br>The Track Time Team</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return send_email(email, subject, body, is_html=True)

def send_registration_notification(registration: Registration) -> bool:
    """Send notification to user about their registration submission"""
    subject = "Registration Received - Pending Approval"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #333333; font-size: 24px; margin: 0 0 20px; text-align: center;">Registration Received</h1>
            
            <p style="color: #555555; margin-bottom: 20px;">Dear {registration.name},</p>
            
            <p style="color: #555555; margin-bottom: 20px;">Thank you for registering with Track Time. Your registration is currently pending approval from our administrators. We will notify you once your registration has been processed.</p>
            
            <!-- Registration Details Box -->
            <div style="background-color: #f8f9fa; border-radius: 6px; padding: 20px; margin: 30px 0;">
                <h2 style="color: #333333; font-size: 18px; margin: 0 0 15px;">Registration Details</h2>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Email:</strong>
                    <span style="color: #333333;">{registration.email}</span>
                </div>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Submitted:</strong>
                    <span style="color: #333333;">{registration.created_at.strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
            </div>
            
            <!-- Next Steps -->
            <div style="margin: 30px 0;">
                <h2 style="color: #333333; font-size: 18px; margin: 0 0 15px;">What's Next?</h2>
                <p style="color: #555555; margin-bottom: 10px;">1. Our team will review your registration</p>
                <p style="color: #555555; margin-bottom: 10px;">2. You'll receive an approval notification</p>
                <p style="color: #555555; margin-bottom: 10px;">3. You can then log in to your account</p>
            </div>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center;">
                <p style="color: #888888; font-size: 14px; margin-bottom: 10px;">Best regards,<br>The Track Time Team</p>
                
                <div style="color: #888888; font-size: 12px; margin-top: 20px;">
                    <p style="margin: 5px 0;">Need help? Contact our support team at tracktime@yourdomain.com</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return send_email(registration.email, subject, body, is_html=True)

def send_admin_notification(registration: Registration) -> None:
    """Send notification to admins about new registration"""
    admin_users = Registration.query.filter_by(
        status='approved',
        is_admin=True
    ).all()
    
    subject = f"New Registration Pending Approval - {registration.email}"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #333333; font-size: 24px; margin: 0 0 20px; text-align: center;">New Registration Pending Approval</h1>
            
            <div style="background-color: #f8f9fa; border-radius: 6px; padding: 20px; margin: 30px 0;">
                <h2 style="color: #333333; font-size: 18px; margin: 0 0 15px;">Registration Details</h2>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Name:</strong>
                    <span style="color: #333333;">{registration.name}</span>
                </div>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Email:</strong>
                    <span style="color: #333333;">{registration.email}</span>
                </div>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Submitted:</strong>
                    <span style="color: #333333;">{registration.created_at.strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
            </div>
            
            <p style="text-align: center;">
                <a href="https://tracktime.yourdomain.com/approve-registrations" 
                   style="display: inline-block; background-color: #007bff; color: white; padding: 12px 24px; 
                          text-decoration: none; border-radius: 4px; margin-top: 20px;">
                    Review Registration
                </a>
            </p>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center;">
                <p style="color: #888888; font-size: 14px; margin-bottom: 10px;">Best regards,<br>System Notification</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    for admin in admin_users:
        send_email(admin.email, subject, body, is_html=True)

def send_approval_notification(registration: Registration) -> bool:
    """Send notification to user about approved registration"""
    subject = "Registration Approved"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #333333; font-size: 24px; margin: 0 0 20px; text-align: center;">Registration Approved!</h1>
            
            <p style="color: #555555; margin-bottom: 20px;">Dear {registration.name},</p>
            
            <p style="color: #555555; margin-bottom: 20px;">Your registration has been approved! You can now log in to Track Time using your email address.</p>
            
            <div style="background-color: #f8f9fa; border-radius: 6px; padding: 20px; margin: 30px 0;">
                <h2 style="color: #333333; font-size: 18px; margin: 0 0 15px;">Account Details</h2>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Email:</strong>
                    <span style="color: #333333;">{registration.email}</span>
                </div>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Approved:</strong>
                    <span style="color: #333333;">{datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
            </div>
            
            <p style="text-align: center;">
                <a href="https://tracktime.yourdomain.com/" 
                   style="display: inline-block; background-color: #28a745; color: white; padding: 12px 24px; 
                          text-decoration: none; border-radius: 4px; margin-top: 20px;">
                    Log In Now
                </a>
            </p>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center;">
                <p style="color: #888888; font-size: 14px; margin-bottom: 10px;">Best regards,<br>The Track Time Team</p>
                
                <div style="color: #888888; font-size: 12px; margin-top: 20px;">
                    <p style="margin: 5px 0;">Need help? Contact our support team at tracktime@yourdomain</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return send_email(registration.email, subject, body, is_html=True)

def send_rejection_notification(registration: Registration) -> bool:
    """Send notification to user about rejected registration"""
    subject = "Registration Status Update"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #333333; font-size: 24px; margin: 0 0 20px; text-align: center;">Registration Update</h1>
            
            <p style="color: #555555; margin-bottom: 20px;">Dear {registration.name},</p>
            
            <p style="color: #555555; margin-bottom: 20px;">We regret to inform you that your registration request has been declined at this time.</p>
            
            <div style="background-color: #f8f9fa; border-radius: 6px; padding: 20px; margin: 30px 0;">
                <h2 style="color: #333333; font-size: 18px; margin: 0 0 15px;">Registration Details</h2>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Email:</strong>
                    <span style="color: #333333;">{registration.email}</span>
                </div>
                <div style="margin-bottom: 10px;">
                    <strong style="color: #666666;">Submitted:</strong>
                    <span style="color: #333333;">{registration.created_at.strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
            </div>
            
            <p style="color: #555555; margin-bottom: 20px;">If you believe this is an error, please contact our support team.</p>
            
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center;">
                <p style="color: #888888; font-size: 14px; margin-bottom: 10px;">Best regards,<br>The Track Time Team</p>
                
                <div style="color: #888888; font-size: 12px; margin-top: 20px;">
                    <p style="margin: 5px 0;">Need help? Contact our support team at tracktime@yourdomain.com</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return send_email(registration.email, subject, body, is_html=True)