from flask import Flask
from models import db
from views.main import register_main_routes
from views.auth import register_auth_routes
from views.admin import register_admin_routes
from config import Config
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from database import init_database

def setup_logging():
    """Configure application logging"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=10485760,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        ]
    )

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Setup logging
    setup_logging()
    
    # Initialize extensions
    db.init_app(app)

    # Initialize database with backup
    init_database(app, db)
    
    # Register routes
    register_auth_routes(app)
    register_main_routes(app)
    register_admin_routes(app)
    
    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://cdn.jsdelivr.net "
                "https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' "
                "https://cdn.jsdelivr.net "
                "https://cdnjs.cloudflare.com "
                "https://fonts.googleapis.com; "
            "font-src 'self' "
                "https://cdnjs.cloudflare.com "
                "https://fonts.gstatic.com "
                "https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: "
                "https://netwrk8.com "
                "/api/placeholder/*; "
            "connect-src 'self' https:; "
            "frame-src 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self'"
        )
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), interest-cohort=()'
        )
        return response
    
    # Template filters
    @app.template_filter('datetime')
    def format_datetime(value):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime('%I:%M %p')
        except ValueError as e:
            print(f"Error parsing datetime: {e}")
            return value
    
    return app

application = create_app()

if __name__ == '__main__':
    application.run(host="0.0.0.0")