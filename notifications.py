# notifications.py
import requests
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def send_notification(message):
    """Send notification using NTFY"""
    if not current_app.config['NTFY_ENDPOINT']:
        logger.warning("NTFY endpoint not configured")
        return
    
    if not current_app.config['NTFY_TOKEN']:
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