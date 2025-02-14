from flask import Flask
from models import db, Registration
from datetime import datetime
import pytz
from config import Config

def create_root_user():
    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        # Create root user with approved status and admin privileges
        root_user = Registration(
            email='frank@yourdomain.com',
            name='Frank Evans',
            status='approved',
            is_admin=True,  # Set admin status
            created_at=datetime.now(pytz.timezone('Australia/Sydney'))
        )
        
        try:
            # Check if root user already exists
            existing_user = Registration.query.filter_by(
                email='frank@yourdomain.com'
            ).first()
            
            if existing_user:
                if existing_user.status != 'approved' or not existing_user.is_admin:
                    existing_user.status = 'approved'
                    existing_user.is_admin = True
                    db.session.commit()
                    print("Root user status updated to approved admin")
                else:
                    print("Root user already exists as admin")
                return True
            
            # Create new root user
            db.session.add(root_user)
            db.session.commit()
            print("Root admin user created successfully")
            return True
            
        except Exception as e:
            print(f"Error creating root user: {str(e)}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    if create_root_user():
        print("Root admin user setup completed successfully!")
    else:
        print("Failed to setup root admin user")
