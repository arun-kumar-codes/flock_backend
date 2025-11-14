import os
import requests
from base64 import b64encode
from urllib.parse import urlencode, quote
import uuid


class PayPalService:
    def __init__(self):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        self.redirect_uri = os.getenv("PAYPAL_REDIRECT_URI")
        self.base_url = (
            "https://api-m.sandbox.paypal.com"
            if os.getenv("PAYPAL_SANDBOX", "true").lower() == "true"
            else "https://api-m.paypal.com"
        )

    # Generate OAuth authorization URL
    def get_authorize_url(self):
        paypal_domain = (
            "www.sandbox.paypal.com" if "sandbox" in self.base_url else "www.paypal.com"
        )

        scope = "openid email profile"
        query = (
            f"client_id={self.client_id}"
            f"&response_type=code"
            f"&scope={quote(scope)}"
            f"&redirect_uri={quote(self.redirect_uri, safe='')}"
            f"&state=paypal_auth_state"
        )

        url = f"https://{paypal_domain}/connect?{query}"
        print("DEBUG PAYPAL AUTH URL:", url)
        return url

    # Exchange OAuth code for access token
    def get_access_token_from_code(self, code):
        auth = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "authorization_code", "code": code}

        r = requests.post(f"{self.base_url}/v1/oauth2/token", headers=headers, data=data)
        r.raise_for_status()
        return r.json()

    # Retrieve verified user email
    def get_user_info(self, access_token):
        headers = {"Authorization": f"Bearer {access_token}"}
        r = requests.get(
            f"{self.base_url}/v1/identity/openidconnect/userinfo/?schema=openid", headers=headers
        )
        r.raise_for_status()
        return r.json()

    # === ADDED PAYOUT FUNCTIONS BELOW ===

    # App-level access token for payouts
    def get_payout_access_token(self):
        url = f"{self.base_url}/v1/oauth2/token"
        headers = {"Accept": "application/json"}
        data = {"grant_type": "client_credentials"}

        r = requests.post(
            url,
            auth=(self.client_id, self.client_secret),
            data=data,
            headers=headers
        )
        r.raise_for_status()
        return r.json()["access_token"]

    # Send payout
    def send_payout(self, receiver_email: str, amount: float):
        token = self.get_payout_access_token()

        url = f"{self.base_url}/v1/payments/payouts"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        body = {
            "sender_batch_header": {
                "sender_batch_id": f"batch_{uuid.uuid4().hex}",
                "email_subject": "You received a payout",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": receiver_email,
                    "note": "Creator withdrawal",
                    "amount": {
                        "value": f"{float(amount):.2f}",
                        "currency": "USD",
                    },
                }
            ],
        }

        r = requests.post(url, json=body, headers=headers)

        if r.status_code >= 400:
            print("\n PAYPAL PAYOUT FAILED ")
            print("Status Code:", r.status_code)
            print("Response:", r.text)
            print("=====================================\n")

            return {
                "error": True,
                "status_code": r.status_code,
                "details": r.json()
            }

        # Return parsed response
        print("\n PAYPAL PAYOUT SUCCESS")
        print("Status Code:", r.status_code)
        print("Response:", r.text)
        print("=====================================\n")

        return r.json()

    
    
    
    def get_batch_status(self, batch_id):
        token = self.get_payout_access_token()
        url = f"{self.base_url}/v1/payments/payouts/{batch_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        r = requests.get(url, headers=headers)
        data = r.json()
        return data.get("batch_header", {}).get("batch_status", "UNKNOWN")

