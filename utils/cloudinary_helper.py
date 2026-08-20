import cloudinary.uploader


def upload_image(file, folder):

    result = cloudinary.uploader.upload(
        file,
        folder=folder
    )

    return {
        "url": result["secure_url"],
        "public_id": result["public_id"]
    }


def delete_image(public_id):

    cloudinary.uploader.destroy(public_id)