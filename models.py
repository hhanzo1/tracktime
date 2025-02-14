from enum import Enum
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask import current_app

db = SQLAlchemy()

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(current_app.config['TIMEZONE']))
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Registration {self.email} - {self.status}>'

class CheckInStatus(Enum):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'

class CheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(current_app.config['TIMEZONE']))
    notify = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum(CheckInStatus), default=CheckInStatus.PENDING, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<CheckIn {self.name} - {self.start_time} - {self.duration}h - {self.status.value}>'

    @property
    def needs_confirmation(self):
        """
        Check if the check-in is eligible for confirmation.
        
        Confirmation is possible:
        - When the status is PENDING
        - Anytime on the day of the event
        - Until 1 hour after the start time
        
        Returns:
        bool: True if the check-in can be confirmed, False otherwise.
        """
        # Get the current time in the configured timezone
        now = datetime.now(current_app.config['TIMEZONE'])
        
        # Ensure start_time is timezone-aware
        if not self.start_time.tzinfo:
            check_time = current_app.config['TIMEZONE'].localize(self.start_time)
        else:
            check_time = self.start_time
        
        # Calculate the confirmation window end (1 hour after start time)
        confirmation_window_end = check_time + timedelta(hours=1)
        
        # Check if the current time is on the same day as the event
        same_day = (
            now.year == check_time.year and 
            now.month == check_time.month and 
            now.day == check_time.day
        )
        
        # Check if the current status is pending and within the confirmation window
        return (
            self.status == CheckInStatus.PENDING and 
            (
                # Either on the same day with status PENDING
                same_day or 
                # Or within 1 hour after start time
                (check_time <= now <= confirmation_window_end)
            )
        )

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<OTP {self.email} - {self.otp_code}>'

    @property
    def is_expired(self):
        """Check if the OTP is expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self):
        """Check if the OTP is still valid"""
        return not self.is_used and not self.is_expired