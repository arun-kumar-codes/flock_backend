import os
import resend

from app import db
from app.models.auth import Invitation

FROM_EMAIL = "admin@notifications.flocktogether.xyz"
resend.api_key = os.getenv("RESEND_API_KEY")


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
        "from": "FlockTogether <admin@notifications.flocktogether.xyz>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": body
        }
        result = resend.Emails.send(params)
        print(result)
        print(f"Invitation email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        db.session.rollback()
        return False
    
    
    
def send_reset_password_email(to_email: str, username: str, reset_url: str) -> bool:
    """
    Send password reset email using Resend API
    """
    try:
        # Extract first name for greeting
        first_name = username

        subject = "Reset Your FLOCK Password"

        # Plain text fallback
        text_body = f"""
Dear {first_name},

We received a request to reset your FLOCK password.

Reset your password using the link below:
{reset_url}

If you didn’t request this, please ignore this email.

— The FLOCK Team
"""

        # HTML body
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f7f7f7; color: #333;">
    <div style="max-width: 550px; margin: auto; background: white; padding: 30px; border-radius: 12px; 
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);">

        <h2 style="color:#684098; text-align:center; margin-bottom: 20px;">
            Reset Your FLOCK Password
        </h2>

        <p style="font-size: 15px;">
            Dear <strong>{first_name}</strong>,
        </p>

        <p style="font-size: 15px; line-height: 1.6;">
            We received a request to reset your password.  
            Click the button below to set a new one.
        </p>

        <!-- Button -->
        <div style="text-align:center; margin: 25px 0;">
            <a href="{reset_url}"
               style="padding: 14px 28px; background:#6A5ACD; color:white; 
                      text-decoration:none; border-radius:8px; font-size: 16px;">
                Reset Password
            </a>
        </div>

        <p style="font-size: 14px; line-height: 1.6; color:#555;">
            If you didn’t request this, please ignore this email.
        </p>

        <p style="margin-top: 25px; font-size: 14px; color:#777;">
            — The FLOCK Team
        </p>
    </div>
</body>
</html>
"""

        params: resend.Emails.SendParams = {
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        resend.Emails.send(params)
        print(f"Password reset email sent to {to_email}")
        return True

    except Exception as e:
        print("Reset email sending error:", e)
        return False
    
    
def send_verification_email(to_email: str, first_name: str, code: str) -> bool:
    """
    Send email verification OTP using Resend API.
    """
    try:
        subject = "Verify Your FLOCK Account"

        # TEXT VERSION (fallback)
        text_body = f"""
Dear {first_name},

Welcome to FLOCK! Please confirm your email by entering the verification code below:

Verification Code: {code}

This code will expire in 10 minutes.

If you did not request this, please ignore this email.

– The FLOCK Team
        """

        # HTML VERSION (styled)
        html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; padding: 24px; background: #f7f7f7; color:#333;">
    
    <div style="max-width: 520px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
      
      <h2 style="margin-top: 0; color:#4a4a4a;">Verify Your FLOCK Account</h2>

      <p>Dear <b>{first_name}</b>,</p>

      <p>Welcome to <b>FLOCK</b>! Please confirm your email by entering the verification code below to verify your account.</p>

      <div style="text-align: center; margin-top: 25px; margin-bottom: 25px;">
        
        <div style="
            display: inline-block;
            padding: 14px 22px;
            background: #6A5ACD;
            color: white;
            font-size: 24px;
            letter-spacing: 4px;
            border-radius: 10px;
            font-weight: bold;
        ">
            {code}
        </div>
      </div>

      <p style="font-size:14px; color:#666;">
        This code expires in <b>10 minutes</b>.
      </p>

      <p style="font-size:13px; color:#999; margin-top: 20px;">
        – The FLOCK Team
      </p>

    </div>
  </body>
</html>
        """

        params: resend.Emails.SendParams = {
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        resend.Emails.send(params)
        print(f"Verification email sent to {to_email}")
        return True

    except Exception as e:
        print("Verification email sending error:", e)
        return False




def send_withdrawal_request_email(to_email: str, username: str,  amount: float, method: str) -> bool:
    try:
        first_name = username

        subject = "Your Withdrawal Request Has Been Submitted"

        text_body = f"""
Dear {first_name},

We have received your withdrawal request.

Amount: ${amount:.2f}
Method: {method}

We’ll notify you once it has been processed.

— The FLOCK Team
"""

        html_body = f"""
<html>
<body style="font-family: Arial; background:#f7f7f7; padding:20px;">
    <div style="max-width:550px;margin:auto;background:white;padding:25px;border-radius:12px;
    box-shadow:0 4px 12px rgba(0,0,0,0.08);">

        <h2 style="color:#684098;text-align:center;">Withdrawal Request Submitted</h2>

        <p>Dear <strong>{first_name}</strong>,</p>

        <p>Your withdrawal request has been received. Below are the details:</p>

        <ul style="font-size:15px;line-height:1.6;">
            <li><strong>Amount:</strong> ${amount:.2f}</li>
            <li><strong>Method:</strong> {method}</li>
        </ul>

        <p style="margin-top:20px;">We’ll notify you as soon as the payout is processed.</p>

        <p style="color:#777;margin-top:25px;">
            — The FLOCK Team
        </p>
    </div>
</body>
</html>
"""

        params = {
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }

        resend.Emails.send(params)
        return True

    except Exception as e:
        print("Withdrawal request email error:", e)
        return False



def send_withdrawal_processed_email(to_email: str, username: str, amount: float, method: str) -> bool:
    try:
        first_name = username

        subject = "Your Payment Has Been Sent"

        text_body = f"""
Dear {first_name},

Your payout has been successfully completed.

Amount: ${amount:.2f}
Method: {method}

The funds should arrive shortly depending on your payment provider.

— The FLOCK Team
"""

        html_body = f"""
<html>
<body style="font-family: Arial; background:#f7f7f7; padding:20px;">
    <div style="max-width:550px;margin:auto;background:white;padding:25px;border-radius:12px;
    box-shadow:0 4px 12px rgba(0,0,0,0.08);">

        <h2 style="color:#2ecc71;text-align:center;">Payment Successfully Sent</h2>

        <p>Dear <strong>{first_name}</strong>,</p>

        <p>Your payout has been completed successfully. Here are the details:</p>

        <ul style="font-size:15px;line-height:1.6;">
            <li><strong>Amount:</strong> ${amount:.2f}</li>
            <li><strong>Sent To:</strong> {method}</li>
        </ul>

        <p>Your funds are now on their way. Processing times vary by provider.</p>

        <p style="color:#777;margin-top:25px;">
            — The FLOCK Team
        </p>
    </div>
</body>
</html>
"""

        params = {
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }

        resend.Emails.send(params)
        return True

    except Exception as e:
        print("Withdrawal processed email error:", e)
        return False



def send_withdrawal_failed_email(to_email: str, amount: float, username: str, method: str, reason: str) -> bool:
    try:
        first_name = username

        subject = "We Couldn’t Process Your Withdrawal"

        text_body = f"""
Dear {first_name},

Your withdrawal of ${amount:.2f} to {method} could not be processed.

Reason: {reason}

Please update your payout settings and try again.

— The FLOCK Team
"""

        html_body = f"""
<html>
<body style="font-family: Arial; background:#f7f7f7; padding:20px;">
    <div style="max-width:550px;margin:auto;background:white;padding:25px;border-radius:12px;
    box-shadow:0 4px 12px rgba(0,0,0,0.08);">

        <h2 style="color:#e74c3c;text-align:center;">Withdrawal Failed</h2>

        <p>Dear <strong>{first_name}</strong>,</p>

        <p>Your recent withdrawal request could not be completed.</p>

        <ul style="font-size:15px;line-height:1.6;">
            <li><strong>Amount:</strong> ${amount:.2f}</li>
            <li><strong>Method:</strong> {method}</li>
            <li><strong>Reason:</strong> {reason}</li>
        </ul>

        <p>Please update your payout settings and try again.</p>

        <p style="color:#777;margin-top:25px;">
            — The FLOCK Team
        </p>
    </div>
</body>
</html>
"""

        params = {
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }

        resend.Emails.send(params)
        return True

    except Exception as e:
        print("Withdrawal failed email error:", e)
        return False


def send_security_alert_email(to_email: str, username: str, ip_address: str, location: str):
    try:
        first_name = username

        subject = "New Login to Your FLOCK Account"

        text_body = f"""
Dear {first_name},

We noticed a new login to your FLOCK account.

IP: {ip_address}
Location: {location}

If this was you, no action is needed.
If you did NOT perform this login, change your password immediately.

— The FLOCK Team
"""

        html_body = f"""
<html>
<body style="font-family: Arial; background:#f7f7f7; padding:20px;">
<div style="max-width:550px;margin:auto;background:white;padding:25px;border-radius:12px;
    box-shadow:0 4px 12px rgba(0,0,0,0.08);">

<h2 style="color:#e67e22; text-align:center;">New Login Detected</h2>

<p>Dear <strong>{first_name}</strong>,</p>

<p>We detected a login to your account from a new device or location:</p>

<ul style="font-size:15px; line-height:1.6;">
  <li><strong>IP Address:</strong> {ip_address}</li>
  <li><strong>Location:</strong> {location}</li>
</ul>

<p>If this was you, you can safely ignore this message.</p>

<p style="color:#c0392b;"><strong>If this wasn't you, change your password immediately.</strong></p>

<p style="color:#777;margin-top:25px;">— The FLOCK Team</p>

</div>
</body>
</html>
"""

        resend.Emails.send({
            "from": "FlockTogether <admin@flocktogether.xyz>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        })

        return True
    except Exception as e:
        print("Security alert email error:", e)
        return False
