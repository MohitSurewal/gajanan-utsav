import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_KEY

def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_KEY)
        firebase_admin.initialize_app(cred)

    return firestore.client()