from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import base64
import hashlib

from flask import current_app

from app import db
from app.models.auth import Invitation


def send_invitation_email(to_email: str) -> bool:
    """
    Send an invitation email and create an Invitation model object
    
    Args:
        to_email (str): Recipient email address
        
    Returns:
        bool: True if email sent successfully and invitation created, False otherwise
    """
    try:
        # Check if invitation already exists
        existing_invitation = Invitation.query.filter_by(email=to_email).first()
        if not existing_invitation:
            # current_app.logger.warning(f"Invitation already exists for {to_email}")
            # return False
        
            # Create invitation record
            invitation = Invitation(email=to_email)
            db.session.add(invitation)
            db.session.commit()
        
        # Create token by encoding the email
        token = base64.urlsafe_b64encode(hashlib.sha256(to_email.encode()).digest()).decode('utf-8')
        
        # Email configuration
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('FROM_EMAIL', smtp_username)
        
        # Email content
        subject = "You're Invited to Join Flock Platform!"
        
        # Plain text version
        body = f"""

        Hi there,
        
        You've been invited to join Flock Platform as a Creator!
        
        Flock Platform is a collaborative space where creators can:
        - 
        - 
        - 
        
        To accept this invitation, please visit our platform by clicking on the link below.
        http://localhost:3000/login?token={token}
        
        We're excited to have you join our community!
        
        Best regards,
        The Flock Platform Team
        """
        
        # HTML version
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50; text-align: center;">You're Invited to Join Flock Platform!</h2>
                
                <p>Hi there,</p>
                
                <p>You've been invited to join <strong>Flock Platform</strong> as a <strong>Creator</strong>!</p>
                
                <p>Flock Platform is a collaborative space where creators can:</p>
                <ul>
                    <li></li>
                    <li></li>
                    <li></li>
                </ul>
                
                <p>To accept this invitation, please visit our platform by clicking on the link below.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://localhost:3000/login?token={token}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Join Flock Platform</a>
                </div>
                
                <p>We're excited to have you join our community!</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="text-align: center; color: #7f8c8d; font-size: 14px;">
                    Best regards,<br>
                    The Flock Platform Team
                </p>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add plain text body
        text_part = MIMEText(body, 'plain')
        msg.attach(text_part)
        
        # Add HTML body
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        current_app.logger.info(f"Invitation email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        # Rollback database changes if email sending fails
        db.session.rollback()
        current_app.logger.error(f"Failed to send invitation email to {to_email}: {str(e)}")
        return False