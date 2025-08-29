import os
import resend

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
        existing_invitation = Invitation.query.filter_by(email=to_email).first()
        if not existing_invitation:
            invitation = Invitation(email=to_email)
            db.session.add(invitation)
            db.session.commit()

        resend.api_key = os.getenv('RESEND_API_KEY')
        
        subject = "You're Invited to Join Flock Platform!"
        
        body = f"""

        Hi there,
        
        You've been invited to join Flock Platform as a Creator!
        
        Flock Platform is a collaborative space where creators can:
        - 
        - 
        - 
        
        To accept this invitation, please visit our platform by clicking on the link below.
        http://116.202.210.102:3003/signup
        
        We're excited to have you join our community!
        
        Best regards,
        The Flock Platform Team
        """
        
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
                    <a href="http://116.202.210.102:3003/signup" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Join Flock Platform</a>
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
        
        params: resend.Emails.SendParams = {
        "from": "onboarding@resend.dev",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": body
        }
        resend.Emails.send(params)
        print(f"Invitation email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        db.session.rollback()
        return False