from services.firebase_service import get_db

db = get_db()


def add_gallery_image(year, event, url, public_id):

    db.collection("gallery").add({

        "year": year,

        "event": event,

        "url": url,

        "public_id": public_id

    })


def get_gallery():

    gallery = {}

    docs = db.collection("gallery").stream()

    for doc in docs:

        data = doc.to_dict()

        year = data["year"]

        event = data["event"]

        gallery.setdefault(year, {})

        gallery[year].setdefault(event, [])

        gallery[year][event].append({

            "url": data["url"],

            "public_id": data["public_id"],

            "doc_id": doc.id

        })

    return gallery