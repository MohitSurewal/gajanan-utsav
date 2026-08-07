import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key-change-this"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Adhyaksha"
)

ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH"
)

CLOUDINARY_CLOUD_NAME = os.environ.get(
    "CLOUDINARY_CLOUD_NAME"
)

CLOUDINARY_API_KEY = os.environ.get(
    "CLOUDINARY_API_KEY"
)

CLOUDINARY_API_SECRET = os.environ.get(
    "CLOUDINARY_API_SECRET"
)

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

FIREBASE_KEY = os.path.join(
    BASE_DIR,
    "gajanan-utsav-firebase-adminsdk-fbsvc-2c74b0955d.json"
)
