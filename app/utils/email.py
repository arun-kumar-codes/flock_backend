import os
import resend

from app import db
from app.models.auth import Invitation

FROM_EMAIL = os.getenv("FROM_EMAIL")

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
        
        subject = "You’re Invited to Join FLOCK as a Creator"
        
        body = f"""

        Hi there,
        
        You've been invited to join Flock Platform as a Creator!
        
        FLOCK is a next-generation space designed exclusively for creators across the Caribbean and diaspora.
        As a Creator, you’ll be able to:
        - Upload and share your videos and blogs with a growing community.
        - Engage your audience through comments, likes, shares, and saves.
        - Monetize your content with earnings calculated from real watch time and engagement.
        - Track performance with detailed dashboards showing your views, watch time, and revenue in real-time.
        - Withdraw your earnings securely through integrated payout systems.
        
        To accept this invitation and set up your Creator account, click below:
        https://beta.flocktogether.xyz/signup
        
        Welcome to a new era of content creation. We’re excited to have you on board!
        
        Best regards,
        The Flock Team
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                
                <p>Hi there,</p>
                
                <p>You've been invited to join <strong>FLOCK Platform</strong> as a <strong>Creator</strong>!</p>
                
                <p>FLOCK is a next-generation space designed exclusively for creators across the Caribbean and the diaspora. As a Creator, you’ll be able to:</p>
                <ul>
                    <li>Upload and share your videos and blogs with a growing community.</li>
                    <li>Engage your audience through comments, likes, shares, and saves.</li>
                    <li>Monetize your content with earnings calculated from real watch time and engagement.</li>
                    <li>Track performance with detailed dashboards showing your views, watch time, and revenue in real-time.</li>
                    <li>Withdraw your earnings securely through integrated payout systems.</li>
                </ul>
                
                <p>To accept this invitation and set up your Creator account, click below:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://beta.flocktogether.xyz/signup" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Join FLOCK Now</a>
                </div>
                
                <p>Welcome to a new era of content creation. We’re excited to have you on board!</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="text-align: center; color: #7f8c8d; font-size: 14px;">
                    Best regards,<br>
                    The Flock Team
                </p>
            </div>
        </body>
        </html>
        """
        
        params: resend.Emails.SendParams = {
        "from": f"FlockTogether <{FROM_EMAIL}>",
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