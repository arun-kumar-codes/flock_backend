# app/services/paypal_service.py
import os
import requests
from base64 import b64encode

class PayPalService:
    def __init__(self):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        self.redirect_uri = os.getenv("PAYPAL_REDIRECT_URI")
        self.base_url = (
            "https://api.sandbox.paypal.com"
            if os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"
            else "https://api.paypal.com"
        )

    # Generate OAuth authorization URL (for "Connect with PayPal")
    def get_authorize_url(self):
        """Generate correct PayPal OAuth authorization URL (auto-handles live vs sandbox)"""
        scope = "openid email"
        paypal_domain = (
            "www.sandbox.paypal.com" if "sandbox" in self.base_url else "www.paypal.com"
        )
        return (
            f"https://{paypal_domain}/signin/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&redirect_uri={self.redirect_uri}"
        )

    # Exchange OAuth code for access token
    def get_access_token_from_code(self, code):
        auth = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
        }

        r = requests.post(f"{self.base_url}/v1/oauth2/token", headers=headers, data=data)
        r.raise_for_status()
        return r.json()

    # Retrieve verified user email
    def get_user_info(self, access_token):
        headers = {"Authorization": f"Bearer {access_token}"}
        r = requests.get(f"{self.base_url}/v1/identity/openidconnect/userinfo/?schema=openid", headers=headers)
        r.raise_for_status()
        return r.json()