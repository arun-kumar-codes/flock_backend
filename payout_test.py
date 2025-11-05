import requests
import json
from base64 import b64encode

# ---------- CONFIG ----------
CLIENT_ID = "AbVGGWwfWZk8Tc8a3vlercfoytdjXVjhfHRwr95LbmLwAMaKCXTePQ8wH6WA3KAYb0dD_ouo7jZ8n-ZN"
CLIENT_SECRET = "EFUHmlGSR8-2KoyKWZnE6eFYH_z6QcLmdFKDd3yfRPH2-awGBCCX7n_45Zs_SOPhs9rTKOqjfMBKZjXH"
RECEIVER_EMAIL = "sb-v9xyr46938773@personal.example.com"  # replace with a PayPal sandbox personal email
SANDBOX = True  # set False for live

BASE_URL = "https://api.sandbox.paypal.com" if SANDBOX else "https://api.paypal.com"

# ---------- STEP 1: Get Access Token ----------
def get_access_token():
    auth = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(f"{BASE_URL}/v1/oauth2/token", headers=headers, data=data)
    if response.status_code != 200:
        raise Exception(f"Auth failed: {response.text}")
    return response.json()["access_token"]

# ---------- STEP 2: Send a Payout ----------
def send_payout(access_token):
    url = f"{BASE_URL}/v1/payments/payouts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
        "sender_batch_header": {
            "sender_batch_id": "FLOCK_TEST_" + str(id(object())),
            "email_subject": "You have a payout from Flock Creator!",
            "email_message": "You have received a test payment!"
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": "1.00", "currency": "USD"},
                "note": "Test payout from Flock platform",
                "receiver": RECEIVER_EMAIL,
                "sender_item_id": "item_001"
            }
        ]
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Status:", response.status_code)
    print("Response:")
    print(json.dumps(response.json(), indent=4))

def main():
    token = get_access_token()
    print("✅ Access token retrieved.")
    print("Access Token:", token)
    send_payout(token)

if __name__ == "__main__":
    main()
