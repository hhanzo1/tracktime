import os
import shutil
from datetime import datetime
import logging
from pathlib import Path

def init_database(app, db):
    """Initialize database with backup functionality"""
    logger = logging.getLogger(__name__)
    
    # Get database path from config
    db_url = app.config['SQLALCHEMY_DATABASE_URI']
    if db_url.startswith('sqlite:///'):
        db_path = db_url.replace('sqlite:///', '')
        db_file = Path(db_path)
        
        # Create backup if database exists
        if db_file.exists():
            try:
                # Create backups directory if it doesn't exist
                backup_dir = Path('backups')
                backup_dir.mkdir(exist_ok=True)
                
                # Generate backup filename with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = backup_dir / f'checkin_{timestamp}.db'
                
                # Create backup
                shutil.copy2(db_file, backup_path)
                logger.info(f"Created database backup: {backup_path}")
                
                # Keep only last 5 backups
                backups = sorted(backup_dir.glob('checkin_*.db'))
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
                        old_backup.unlink()
                        logger.info(f"Removed old backup: {old_backup}")
                        
            except Exception as e:
                logger.error(f"Failed to create database backup: {str(e)}")
    
    # Initialize database
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {str(e)}")
            raise