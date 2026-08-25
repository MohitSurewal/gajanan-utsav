from services.firebase_service import get_db

db = get_db()


def upload_gallery_image(year, event, image_data):

    db.collection("gallery").add({

        "year": year,
        "event": event,
        "url": image_data["url"],
        "public_id": image_data["public_id"]

    })


def get_gallery():
    pass


def delete_gallery():
    pass