from unittest import result
import firebase_admin
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin import credentials
from firebase_admin import firestore
from google.cloud.firestore_v1.client import Client
from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_wtf.csrf import CSRFProtect
import json
import os
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import time 
from pathlib import Path
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import *
from config import FIREBASE_KEY
from google.auth.transport.requests import Request

app = Flask(__name__)
csrf = CSRFProtect(app)

cred = credentials.Certificate(FIREBASE_KEY)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()


MAX_LOGIN_ATTEMPTS = 5
LOCK_TIME = 15 * 60   # 15 minutes

login_attempts = {}


cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

app.secret_key = SECRET_KEY


app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SECURE=True,

    SESSION_COOKIE_SAMESITE="Lax",

    PERMANENT_SESSION_LIFETIME=1800

)


def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )




from collections import defaultdict

def load_gallery(event=None, year=None):

    gallery = defaultdict(lambda: defaultdict(list))

    docs = db.collection("gallery").stream()

    for doc in docs:

        data = doc.to_dict()

        y = data.get("year")
        e = data.get("event")

        if year and y != year:
            continue

        if event and e != event:
            continue

        gallery[y][e].append({

            "url": data.get("url"),

            "public_id": data.get("public_id"),

            "doc_id": doc.id

        })

    return dict(gallery)


def load_notice():
    file_path = os.path.join(BASE_DIR, "data", "notice.json")

    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_notice(data):
    file_path = os.path.join(BASE_DIR, "data", "notice.json")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    
def load_schedule():
    file_path = os.path.join(BASE_DIR, "data", "schedule.json")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
    
def load_videos():

    file_path = os.path.join(BASE_DIR, "data", "videos.json")

    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:

        return json.load(f)


def save_videos(data):

    file_path = os.path.join(BASE_DIR, "data", "videos.json")

    with open(file_path, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

REQUIRED_FIELDS = {
    "id",
    "slug",
    "game",
    "icon",
    "date",
    "status",
    "type",
    "gallery"
}


def load_committee():

    file_path = os.path.join(BASE_DIR, "data", "committee.json")

    with open(file_path, "r", encoding="utf-8") as f:

        return json.load(f)


def save_committee(data):

    file_path = os.path.join(BASE_DIR, "data", "committee.json")

    with open(file_path, "w", encoding="utf-8") as f:

        json.dump(data, f, indent=4, ensure_ascii=False)


def validate_game(game, filename):

    missing = REQUIRED_FIELDS - game.keys()

    if missing:
        print(f"\n❌ {filename}")
        print("Missing Fields:", ", ".join(sorted(missing)))
        return False

    return True



def load_winners():

    winners = {}

    winners_path = os.path.join(BASE_DIR, "data", "winners")

    if not os.path.exists(winners_path):
        return winners

    for year in sorted(os.listdir(winners_path), reverse=True):

        year_path = os.path.join(winners_path, year)

        if not os.path.isdir(year_path):
            continue

        winners[year] = []

        for file in sorted(os.listdir(year_path)):

            if not file.endswith(".json"):
                continue

            file_path = os.path.join(year_path, file)

            try:

                with open(file_path, "r", encoding="utf-8") as f:

                    game = json.load(f)

                if validate_game(game, file):
                    winners[year].append(game)

            except Exception as e:

                print(f"[Winner Loader] {file} : {e}")

    return winners


def load_hall_of_fame():

    winners_data = load_winners()

    players = {}

    for year, games in winners_data.items():

        for game in games:

            game_name = game["game"]

            # Ranking Games
            if game["type"] == "ranking":

                for person in game.get("winners", []):

                    name = person["name"].strip()

                    if name not in players:

                        players[name] = {
                            "name": name,
                            "gold": 0,
                            "silver": 0,
                            "bronze": 0,
                            "total": 0,
                            "awards": []
                        }

                    if person["position"] == 1:
                        players[name]["gold"] += 1

                    elif person["position"] == 2:
                        players[name]["silver"] += 1

                    elif person["position"] == 3:
                        players[name]["bronze"] += 1

                    players[name]["total"] += 1

                    players[name]["awards"].append({

                        "year": year,
                        "game": game_name,
                        "position": person["position"]

                    })

            # Age Group Games

            elif game["type"] == "age_group":

                for group in game.get("groups", []):

                    winner = group["winner"]

                    name = winner["name"].strip()

                    if name not in players:

                        players[name] = {
                            "name": name,
                            "gold": 0,
                            "silver": 0,
                            "bronze": 0,
                            "total": 0,
                            "awards": []
                        }

                    players[name]["gold"] += 1
                    players[name]["total"] += 1

                    players[name]["awards"].append({

                        "year": year,
                        "game": f'{game_name} ({group["age_group"]})',
                        "position": 1

                    })

    hall = list(players.values())

    hall.sort(

        key=lambda x: (
            -x["gold"],
            -x["silver"],
            -x["bronze"],
            x["name"]
        )

    )

    return hall

@app.route("/token-test")
def token_test():
    try:
        cred.refresh(Request())

        return {
            "valid": cred.valid,
            "expired": cred.expired,
            "service_account": cred.service_account_email,
            "token_start": cred.token[:30]
        }

    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>"

@app.route("/iam-test")
def iam_test():
    import requests

    with open(FIREBASE_KEY) as f:
        data = json.load(f)

    return {
        "client_email": data["client_email"],
        "private_key_id": data["private_key_id"],
        "project_id": data["project_id"]
    }




@app.route("/firebase-info")
def firebase_info():
    with open(FIREBASE_KEY, "r") as f:
        data = json.load(f)

    return {
        "project_id": data.get("project_id"),
        "client_email": data.get("client_email"),
        "private_key_id": data.get("private_key_id")
    }

@app.route("/firebase-test")
def firebase_test():

    import traceback

    try:

        test_ref = db.collection("test").document("connection")

        return {
            "doc_path": test_ref.path,
            "project": db.project
        }

    except Exception:

        return f"<pre>{traceback.format_exc()}</pre>"

@app.route("/migrate-gallery")
def migrate_gallery():

    gallery = load_gallery()

    total = 0

    for year, events in gallery.items():

        for event, images in events.items():

            for image in images:

                db.collection("gallery").add({

                    "year": year,
                    "event": event,
                    "url": image["url"],
                    "public_id": image["public_id"]

                })

                total += 1

    return f"{total} images migrated successfully."

import sys

@app.route("/python-version")
def python_version():
    return {
        "python": sys.version,
        "executable": sys.executable
    }



@app.route("/schedule")
def schedule():

    data = load_schedule()

    return render_template(
        "schedule.html",
        schedule=data,
        active_page="schedule"
    )

@app.route("/gallery")
def gallery():

    event = request.args.get("event")
    year = request.args.get("year")
    gallery_data = load_gallery(event, year)

    return render_template(
        "gallery.html",
        gallery=gallery_data,
        selected_event=event,
        active_page="gallery"
    )


@app.route("/videos")
def videos():

    videos = load_videos()

    return render_template(
        "videos.html",
        videos=videos,
        active_page="videos"
    )

@app.route("/committee")
def committee():

    return render_template(
        "committee.html",
        active_page="committee"
    )

@app.route("/donate")
def donate():
    return render_template("donate.html", active_page="donate")

@app.route("/contact")
def contact():
    return render_template("contact.html", active_page="contact")

@app.route("/winners")
def winners():

    winners_data = load_winners()

    years = sorted(winners_data.keys(), reverse=True)

    games = []
    seen = set()

    for year_games in winners_data.values():

        for game in year_games:

            slug = game.get("slug")

            if slug not in seen:

                seen.add(slug)

                games.append({
                    "slug": slug,
                    "game": game.get("game")
                })

    games.sort(key=lambda x: x["game"])

    return render_template(
        "winners.html",
        winners=winners_data,
        years=years,
        games=games,
        active_page="winners"
    )
@app.route("/hall-of-fame")
def hall_of_fame():

    hall = load_hall_of_fame()

    top_three = hall[:3]

    return render_template(

        "hall_of_fame.html",

        hall_of_fame=hall,

        top_three=top_three,

        active_page="hall_of_fame"

    )
    
    

    
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        ip = request.remote_addr

        # Check if IP is locked
        if ip in login_attempts:

            data = login_attempts[ip]

            if data["attempts"] >= MAX_LOGIN_ATTEMPTS:

                elapsed = time.time() - data["locked_at"]

                if elapsed < LOCK_TIME:

                    remaining = int((LOCK_TIME - elapsed) / 60) + 1

                    flash(
                        f"Too many failed attempts. Try again in {remaining} minute(s).",
                        "danger"
                    )

                    return render_template("admin/login.html")

                else:
                    del login_attempts[ip]

        username = request.form.get("username")
        password = request.form.get("password")

        if (
            username == ADMIN_USERNAME
            and ADMIN_PASSWORD_HASH
            and check_password_hash(ADMIN_PASSWORD_HASH, password)
        ):

            # Reset failed attempts after successful login
            login_attempts.pop(ip, None)

            session.permanent = True
            session["admin"] = True
            session["admin_username"] = username

            return redirect(url_for("admin_dashboard"))

        # Wrong password
        if ip not in login_attempts:

            login_attempts[ip] = {
                "attempts": 1,
                "locked_at": 0
            }

        else:

            login_attempts[ip]["attempts"] += 1

            if login_attempts[ip]["attempts"] >= MAX_LOGIN_ATTEMPTS:
                login_attempts[ip]["locked_at"] = time.time()

        flash("Invalid username or password.", "danger")

    return render_template("admin/login.html")


@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin"):

        return redirect(url_for("admin_login"))

    return render_template("admin/dashboard.html")


@app.route("/admin/notice", methods=["GET", "POST"])
def admin_notice():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    notice = load_notice()

    if request.method == "POST":

        notice["title"] = request.form.get("title", "").strip()
        notice["message"] = request.form.get("message", "").strip()

        save_notice(notice)

        flash("Notice updated successfully!", "success")

        return redirect(url_for("admin_notice"))

    return render_template("admin/notice.html", notice=notice)




@app.route("/admin/winners")
def admin_winners():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    winners = load_winners()

    return render_template(
        "admin/winners.html",
        winners=winners
    )
    
@app.route("/admin/winners/edit/<year>/<slug>", methods=["GET", "POST"])
def admin_edit_winner(year, slug):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "winners",
        year,
        f"{slug}.json"
    )

    if not os.path.exists(file_path):

        flash("Winner file not found.", "danger")

        return redirect(url_for("admin_winners"))

    with open(file_path, "r", encoding="utf-8") as f:

        game = json.load(f)
        
    if request.method == "POST":
        
        game["game"] = request.form.get("game", "").strip()

        if game["type"] == "ranking":

            for i, person in enumerate(game["winners"], start=1):

                person["name"] = request.form.get(f"name{i}")

                photo = request.files.get(f"photo{i}")

                if photo and photo.filename:

                    result = cloudinary.uploader.upload(

                        photo,

                        folder=f"Gajanan-Utsav/Winners/{year}"

                    )

                    person["photo"] = result["secure_url"]

                else:

                    person["photo"] = request.form.get(f"old_photo{i}")
                
        elif game["type"] == "age_group":

            for i, group in enumerate(game["groups"], start=1):

                group["winner"]["name"] = request.form.get(f"winner{i}")

                group["winner"]["photo"] = request.form.get(f"photo{i}")

        with open(file_path, "w", encoding="utf-8") as f:

            json.dump(
                game,
                f,
                indent=4,
                ensure_ascii=False
            )

        flash(
            "Winner Updated Successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin_edit_winner",
                year=year,
                slug=slug
            )
        )
        

    return render_template(

        "admin/edit_winner.html",

        game=game,

        year=year

    )
    
    

@app.route("/admin/winners/add", methods=["GET", "POST"])
def admin_add_winner():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        year = request.form.get("year").strip()

        slug = request.form.get("slug").strip().lower().replace(" ", "-")

        data = {

            "id": slug,

            "slug": slug,

            "game": request.form.get("game"),

            "icon": request.form.get("icon"),

            "date": request.form.get("date"),

            "status": "Completed",

            "type": "ranking",

            "gallery": [],

            "winners": [

                {
                    "position": 1,
                    "name": request.form.get("first"),
                    "photo": request.form.get("first_photo")
                },
                {
                    "position": 2,
                    "name": request.form.get("second"),
                    "photo": request.form.get("second_photo")
                },
                {
                    "position": 3,
                    "name": request.form.get("third"),
                    "photo": request.form.get("third_photo")
                }

            ]

        }

        year_folder = os.path.join(
            BASE_DIR,
            "data",
            "winners",
            year
        )

        os.makedirs(year_folder, exist_ok=True)

        with open(

            os.path.join(year_folder, f"{slug}.json"),

            "w",

            encoding="utf-8"

        ) as f:

            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

        flash("Winner Added Successfully.", "success")

        return redirect(url_for("admin_winners"))

    return render_template("admin/add_winner.html")




    
@app.route("/admin/winners/delete/<year>/<slug>")
def admin_delete_winner(year, slug):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "winners",
        year,
        f"{slug}.json"
    )

    if os.path.exists(file_path):

        os.remove(file_path)

        flash(
            "Winner deleted successfully.",
            "success"
        )

    else:

        flash(
            "Winner not found.",
            "danger"
        )

    return redirect(url_for("admin_winners"))




@app.route("/admin/gallery", methods=["GET", "POST"])
def admin_gallery():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        try:

            year = request.form.get("year", "").strip()

            event = (
                request.form.get("event", "")
                .strip()
                .lower()
                .replace(" ", "-")
            )

            if not year or not event:

                flash("Year and Event are required.", "danger")

                return redirect(url_for("admin_gallery"))

            files = request.files.getlist("photos")

            uploaded = 0

            for file in files:

                if not file or file.filename == "":
                    continue

                if not allowed_file(file.filename):
                    continue

                result = cloudinary.uploader.upload(

                    file,

                    folder=f"Gajanan-Utsav/{year}/{event}"

                )

                print("Saving to Firestore...")

                db.collection("gallery").document().set({

                    "year": year,

                    "event": event,

                    "url": result["secure_url"],

                    "public_id": result["public_id"]

                })

                print("Firestore Saved")
                                
                print("Cloudinary Upload Success")
                print(result["secure_url"])

                uploaded += 1

            flash(

                f"{uploaded} image(s) uploaded successfully.",

                "success"

            )

            return redirect(url_for("admin_gallery"))

        except Exception:

            import traceback

            error = traceback.format_exc()

            print(error)

            return f"<pre>{error}</pre>"

    return render_template(

        "admin/gallery.html",

        gallery={}

    )


@app.route("/admin/gallery/delete", methods=["POST"])
def delete_gallery_image():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    year = request.form["year"]
    event = request.form["event"]
    public_id = request.form["public_id"]

    # Delete from Cloudinary
    cloudinary.uploader.destroy(public_id)

    # Delete from Firestore
    docs = db.collection("gallery") \
        .where("public_id", "==", public_id) \
        .stream()

    for doc in docs:
        doc.reference.delete()

    flash("Image deleted successfully.", "success")

    return redirect(url_for("admin_gallery"))










@app.route("/admin/videos")
def admin_videos():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    videos = load_videos()

    return render_template(
        "admin/videos.html",
        videos=videos
    )
    
    
@app.route("/admin/videos/add", methods=["GET", "POST"])
def admin_add_video():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    videos = load_videos()

    if request.method == "POST":

        videos.append({

            "year": request.form.get("year"),

            "title": request.form.get("title"),

            "youtube": request.form.get("youtube")

        })

        save_videos(videos)

        flash(
            "Video Added Successfully.",
            "success"
        )

        return redirect(url_for("admin_videos"))

    return render_template(
        "admin/add_video.html"
    )
    
@app.route("/admin/videos/edit/<int:index>", methods=["GET", "POST"])
def admin_edit_video(index):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    videos = load_videos()

    if index < 0 or index >= len(videos):

        flash("Video not found.", "danger")

        return redirect(url_for("admin_videos"))

    if request.method == "POST":

        videos[index]["year"] = request.form.get("year")

        videos[index]["title"] = request.form.get("title")

        videos[index]["youtube"] = request.form.get("youtube")

        save_videos(videos)

        flash("Video updated successfully.", "success")

        return redirect(url_for("admin_videos"))

    return render_template(

        "admin/edit_video.html",

        video=videos[index],

        index=index

    )
    

@app.route("/admin/videos/delete/<int:index>")
def admin_delete_video(index):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    videos = load_videos()

    if index < 0 or index >= len(videos):

        flash("Video not found.", "danger")

        return redirect(url_for("admin_videos"))

    videos.pop(index)

    save_videos(videos)

    flash(
        "Video deleted successfully.",
        "success"
    )

    return redirect(url_for("admin_videos"))


@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(url_for("admin_login"))

@app.route("/")
def home():

    notice = load_notice()
    schedule = load_schedule()
    committee = load_committee()
    winners = load_winners()
    gallery = {}

    latest_gallery = []

    for year in sorted(gallery.keys(), reverse=True):

        for event in gallery[year]:

            for photo in gallery[year][event]:

                latest_gallery.append(photo)

    latest_gallery = latest_gallery[:6]

    latest_winners = []

    for year in sorted(winners.keys(), reverse=True):

        for game in winners[year]:

            if game["type"] == "ranking":

                latest_winners.append({
                    "year": year,
                    "game": game["game"],
                    "type": "ranking",
                    "data": game["winners"]
                })

            elif game["type"] == "age_group":

                latest_winners.append({
                    "year": year,
                    "game": game["game"],
                    "type": "age_group",
                    "data": game["groups"]
                })

    latest_winners = latest_winners[:6]

    return render_template(
        "home.html",
        notice=notice,
        schedule=schedule,
        committee=committee,
        latest_gallery=latest_gallery,
        latest_winners=latest_winners,
        active_page="home"
    )
    
@app.route("/admin/schedule", methods=["GET", "POST"])
def admin_schedule():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    schedule = load_schedule()

    if request.method == "POST":

        schedule["aarti"]["morning"] = request.form.get("morning")
        schedule["aarti"]["evening"] = request.form.get("evening")

        for i, item in enumerate(schedule["program"], start=1):

            item["date"] = request.form.get(f"program_date{i}")
            item["title"] = request.form.get(f"program_title{i}")

        for i, item in enumerate(schedule["games"], start=1):

            item["date"] = request.form.get(f"game_date{i}")
            item["game"] = request.form.get(f"game_name{i}")

        file_path = os.path.join(BASE_DIR, "data", "schedule.json")

        with open(file_path, "w", encoding="utf-8") as f:

            json.dump(
                schedule,
                f,
                indent=4,
                ensure_ascii=False
            )

        flash("Schedule updated successfully.", "success")

        return redirect(url_for("admin_schedule"))

    return render_template(
        "admin/schedule.html",
        schedule=schedule
    )


@app.route("/admin/committee", methods=["GET", "POST"])
def admin_committee():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    committee = load_committee()

    if request.method == "POST":

        for i, member in enumerate(committee, start=1):

            member["name"] = request.form.get(f"name{i}")
            member["post"] = request.form.get(f"post{i}")
            member["image"] = request.form.get(f"image{i}")

        save_committee(committee)

        flash(
            "Committee updated successfully.",
            "success"
        )

        return redirect(url_for("admin_committee"))

    return render_template(
        "admin/committee.html",
        committee=committee
    )





@app.after_request
def apply_security_headers(response):

    response.headers["X-Frame-Options"] = "DENY"

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' https:; "
        "font-src 'self' https: data:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none';"
    )

    return response


@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "404.html",
        active_page=""
    ), 404


@app.errorhandler(500)
def internal_server_error(error):

    return render_template(
        "500.html",
        active_page=""
    ), 500
    
    
    
if __name__ == "__main__":
    app.run()
