import os
from datetime import timedelta
import pytz
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///tracktime.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Weather configuration
    WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
    CACHE_TIMEOUT_MINUTES = 15
    LOCATION_LAT = os.getenv('LOCATION_LAT')
    LOCATION_LON = os.getenv('LOCATION_LON')
    TIMEZONE = pytz.timezone('Australia/Sydney')
    
    # Email configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    DEFAULT_SENDER = os.getenv('DEFAULT_SENDER')
    ALLOWED_EMAILS_FILE = os.getenv('ALLOWED_EMAILS_FILE')
    
    # Notification configuration
    NTFY_ENDPOINT = os.getenv('NTFY_ENDPOINT')
    NTFY_TOKEN = os.getenv('NTFY_TOKEN')