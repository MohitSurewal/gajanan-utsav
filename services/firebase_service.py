from firebase_admin import firestore

db = firestore.client()


def get_db():
    return db