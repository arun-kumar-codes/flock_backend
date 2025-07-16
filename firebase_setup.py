import firebase_admin


cred = firebase_admin.credentials.Certificate("firebase-service-account.json")
firebase_admin.initialize_app(cred)