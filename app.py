from unittest import result
from urllib import response
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
from config import FIREBASE_CREDENTIALS
from google.auth.transport.requests import Request
import hashlib
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile
from google.auth.transport.requests import Request
import secrets
import string


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
csrf = CSRFProtect(app)

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REDIRECT_URI = os.environ.get(
    "YOUTUBE_REDIRECT_URI"
)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

cred = credentials.Certificate(FIREBASE_CREDENTIALS)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()


ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "mov",
    "avi",
    "mkv",
    "webm",
    "m4v"
}



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

def allowed_video_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_VIDEO_EXTENSIONS




def load_gallery(event=None, year=None):

    gallery = defaultdict(lambda: defaultdict(list))

    docs = db.collection("gallery").stream()

    for doc in docs:

        data = doc.to_dict()

        y = data.get("year")
        e = data.get("event")

        if not y or not e or not data.get("url"):
            continue

        if year and y != year:
            continue

        if event and e != event:
            continue

        gallery[y][e].append({
            "url": data["url"],
            "public_id": data["public_id"],
            "doc_id": doc.id
        })

    return {
        year: dict(gallery[year])
        for year in sorted(gallery.keys(), key=lambda x: int(x), reverse=True)
    }

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


def get_youtube_credentials():

    doc = (
        db.collection("settings")
        .document("youtube")
        .get()
    )

    if not doc.exists:
        return None

    data = doc.to_dict()

    credentials = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get(
            "token_uri",
            "https://oauth2.googleapis.com/token"
        ),
        client_id=data.get("client_id"),
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=data.get("scopes", YOUTUBE_SCOPES)
    )

    # Refresh expired access token
    if credentials.expired and credentials.refresh_token:

        credentials.refresh(Request())

        db.collection("settings").document("youtube").update({
            "token": credentials.token
        })

    return credentials


def get_youtube_service():

    credentials = get_youtube_credentials()

    if not credentials:
        return None

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )

def calculate_file_hash(file_path):

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:

        while True:

            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


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







@app.route("/youtube/connect")
def youtube_connect():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    client_config = {
        "web": {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [YOUTUBE_REDIRECT_URI]
        }
    }

    # Generate PKCE code verifier
    characters = string.ascii_letters + string.digits + "-._~"

    code_verifier = "".join(
        secrets.choice(characters)
        for _ in range(128)
    )

    flow = Flow.from_client_config(
        client_config,
        scopes=YOUTUBE_SCOPES,
        code_verifier=code_verifier
    )

    flow.redirect_uri = YOUTUBE_REDIRECT_URI

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    # Save BOTH values for callback
    session["youtube_oauth_state"] = state
    session["youtube_code_verifier"] = code_verifier

    return redirect(authorization_url)


@app.route("/youtube/oauth/callback")
def youtube_oauth_callback():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    state = session.get("youtube_oauth_state")
    code_verifier = session.get("youtube_code_verifier")

    if not state:
        return "OAuth session expired. Please try again.", 400

    if not code_verifier:
        return "OAuth code verifier missing. Please start the connection again.", 400

    # Verify state returned by Google
    returned_state = request.args.get("state")

    if returned_state != state:
        return "Invalid OAuth state. Please try again.", 400

    # Check if Google returned an error
    if request.args.get("error"):
        return (
            f"Google OAuth error: "
            f"{request.args.get('error')}"
        ), 400

    client_config = {
        "web": {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [YOUTUBE_REDIRECT_URI]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=YOUTUBE_SCOPES,
        state=state,
        code_verifier=code_verifier
    )

    flow.redirect_uri = YOUTUBE_REDIRECT_URI

    # Exchange authorization code for tokens
    flow.fetch_token(
        authorization_response=request.url
    )

    credentials = flow.credentials

    # Save YouTube credentials in Firestore
    db.collection("settings").document("youtube").set({

        "token": credentials.token,

        "refresh_token": credentials.refresh_token,

        "token_uri": credentials.token_uri,

        "client_id": credentials.client_id,

        "scopes": credentials.scopes

    })

    # Remove temporary OAuth values
    session.pop("youtube_oauth_state", None)
    session.pop("youtube_code_verifier", None)

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Connected</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding-top: 100px;
                background: #111;
                color: white;
            }

            .success {
                font-size: 50px;
            }

            h1 {
                color: #4caf50;
            }
        </style>
    </head>

    <body>

        <div class="success">✅</div>

        <h1>YouTube Connected Successfully</h1>

        <p>
            Your YouTube account has been connected successfully.
        </p>

        <p>
            You can close this window and return to the Admin Panel.
        </p>

    </body>
    </html>
    """






@app.route("/firestore-test")
def firestore_test():
    try:
        collections = [c.id for c in db.collections()]
        return {
            "status": "ok",
            "collections": collections
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }, 500

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

    videos = []

    try:

        docs = (
            db.collection("videos")
            .order_by(
                "created_at",
                direction=firestore.Query.DESCENDING
            )
            .stream()
        )

        for doc in docs:

            data = doc.to_dict()

            data["doc_id"] = doc.id

            videos.append(data)

    except Exception as e:

        print("Error loading videos from Firestore:")

        import traceback
        print(traceback.format_exc())

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
    
@app.route(
    "/admin/winners/edit/<year>/<slug>",
    methods=["GET", "POST"]
)
def admin_edit_winner(year, slug):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))


    # ==========================================
    # FILE PATH
    # ==========================================

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "winners",
        year,
        f"{slug}.json"
    )


    if not os.path.exists(file_path):

        flash(
            "Winner file not found.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # LOAD GAME
    # ==========================================

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as f:

        game = json.load(f)


    # ==========================================
    # POST
    # ==========================================

    if request.method == "POST":

        game_type = game.get(
            "type",
            "ranking"
        )


        # ======================================
        # RANKING
        # ======================================

        if game_type == "ranking":

            winners = []

            try:

                winner_count = int(
                    request.form.get(
                        "winner_count",
                        len(game.get("winners", []))
                    )
                )

            except ValueError:

                winner_count = len(
                    game.get(
                        "winners",
                        []
                    )
                )


            winner_count = max(
                1,
                min(winner_count, 20)
            )


            old_winners = game.get(
                "winners",
                []
            )


            for i in range(
                1,
                winner_count + 1
            ):

                name = request.form.get(
                    f"winner_name_{i}",
                    ""
                ).strip()


                # ----------------------------------
                # OLD PHOTO
                # ----------------------------------

                old_photo = ""

                old_public_id = ""


                if i <= len(old_winners):

                    old_photo = old_winners[
                        i - 1
                    ].get(
                        "photo",
                        ""
                    )

                    old_public_id = old_winners[
                        i - 1
                    ].get(
                        "photo_public_id",
                        ""
                    )


                # ----------------------------------
                # NEW PHOTO
                # ----------------------------------

                photo_file = request.files.get(
                    f"winner_photo_{i}"
                )


                photo_url = old_photo

                photo_public_id = old_public_id


                if (
                    photo_file
                    and photo_file.filename
                ):

                    result = cloudinary.uploader.upload(

                        photo_file,

                        folder=(
                            f"Gajanan-Utsav/"
                            f"Winners/"
                            f"{year}/"
                            f"{slug}"
                        )

                    )


                    photo_url = result.get(
                        "secure_url",
                        ""
                    )


                    photo_public_id = result.get(
                        "public_id",
                        ""
                    )


                # ----------------------------------
                # SAVE WINNER
                # ----------------------------------

                if name:

                    winners.append({

                        "position": i,

                        "name": name,

                        "photo": photo_url,

                        "photo_public_id":
                            photo_public_id

                    })


            game["winners"] = winners


        # ======================================
        # AGE GROUP
        # ======================================

        elif game_type == "age_group":

            groups = []

            try:

                group_count = int(
                    request.form.get(
                        "group_count",
                        len(game.get("groups", []))
                    )
                )

            except ValueError:

                group_count = len(
                    game.get(
                        "groups",
                        []
                    )
                )


            group_count = max(
                1,
                min(group_count, 20)
            )


            old_groups = game.get(
                "groups",
                []
            )


            for i in range(
                1,
                group_count + 1
            ):

                age_group = request.form.get(
                    f"age_group_{i}",
                    ""
                ).strip()


                name = request.form.get(
                    f"age_winner_{i}",
                    ""
                ).strip()


                # ----------------------------------
                # OLD PHOTO
                # ----------------------------------

                old_photo = ""

                old_public_id = ""


                if i <= len(old_groups):

                    old_winner = old_groups[
                        i - 1
                    ].get(
                        "winner",
                        {}
                    )


                    old_photo = old_winner.get(
                        "photo",
                        ""
                    )


                    old_public_id = old_winner.get(
                        "photo_public_id",
                        ""
                    )


                # ----------------------------------
                # NEW PHOTO
                # ----------------------------------

                photo_file = request.files.get(
                    f"age_photo_{i}"
                )


                photo_url = old_photo

                photo_public_id = old_public_id


                if (
                    photo_file
                    and photo_file.filename
                ):

                    result = cloudinary.uploader.upload(

                        photo_file,

                        folder=(
                            f"Gajanan-Utsav/"
                            f"Winners/"
                            f"{year}/"
                            f"{slug}"
                        )

                    )


                    photo_url = result.get(
                        "secure_url",
                        ""
                    )


                    photo_public_id = result.get(
                        "public_id",
                        ""
                    )


                # ----------------------------------
                # SAVE GROUP
                # ----------------------------------

                if age_group or name:

                    groups.append({

                        "age_group": age_group,

                        "winner": {

                            "name": name,

                            "photo": photo_url,

                            "photo_public_id":
                                photo_public_id

                        }

                    })


            game["groups"] = groups


        # ======================================
        # TEAM
        # ======================================

        elif game_type == "team":

            teams = []

            try:

                team_count = int(
                    request.form.get(
                        "team_count",
                        len(game.get("teams", []))
                    )
                )

            except ValueError:

                team_count = len(
                    game.get(
                        "teams",
                        []
                    )
                )


            team_count = max(
                1,
                min(team_count, 20)
            )


            for i in range(
                1,
                team_count + 1
            ):

                team_name = request.form.get(
                    f"team_name_{i}",
                    ""
                ).strip()


                if team_name:

                    teams.append({

                        "team": team_name

                    })


            game["teams"] = teams


        # ======================================
        # SAVE
        # ======================================

        with open(
            file_path,
            "w",
            encoding="utf-8"
        ) as f:

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


    # ==========================================
    # GET
    # ==========================================

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

        # ==========================================
        # BASIC DETAILS
        # ==========================================

        year = request.form.get(
            "year",
            ""
        ).strip()

        game = request.form.get(
            "game",
            ""
        ).strip()

        slug = request.form.get(
            "slug",
            ""
        ).strip().lower()

        icon = request.form.get(
            "icon",
            ""
        ).strip()

        date = request.form.get(
            "date",
            ""
        ).strip()

        winner_type = request.form.get(
            "type",
            "ranking"
        ).strip()


        # ==========================================
        # BASIC VALIDATION
        # ==========================================

        if not year:

            flash(
                "Year is required.",
                "danger"
            )

            return redirect(
                url_for("admin_add_winner")
            )


        if not game:

            flash(
                "Game name is required.",
                "danger"
            )

            return redirect(
                url_for("admin_add_winner")
            )


        # ==========================================
        # AUTO SLUG
        # ==========================================

        if not slug:

            slug = (
                game.lower()
                .strip()
                .replace(" ", "-")
            )


        # ==========================================
        # YEAR FOLDER
        # ==========================================

        year_folder = os.path.join(
            BASE_DIR,
            "data",
            "winners",
            year
        )

        os.makedirs(
            year_folder,
            exist_ok=True
        )


        file_path = os.path.join(
            year_folder,
            f"{slug}.json"
        )


        # ==========================================
        # DUPLICATE CHECK
        # ==========================================

        if os.path.exists(file_path):

            flash(
                f"{game} already exists for {year}.",
                "warning"
            )

            return redirect(
                url_for("admin_add_winner")
            )


        # ==========================================
        # COMMON DATA
        # ==========================================

        data = {

            "id": slug,

            "slug": slug,

            "game": game,

            "icon": icon,

            "date": date,

            "status": "completed",

            "type": winner_type,

            "gallery": []

        }


        # ==================================================
        # RANKING WINNERS
        # ==================================================

        if winner_type == "ranking":

            winners = []


            try:

                winner_count = int(
                    request.form.get(
                        "winner_count",
                        "1"
                    )
                )

            except ValueError:

                winner_count = 1


            # Safety limit

            winner_count = max(
                1,
                min(winner_count, 20)
            )


            for i in range(
                1,
                winner_count + 1
            ):

                # ------------------------------
                # WINNER NAME
                # ------------------------------

                name = request.form.get(
                    f"winner_name_{i}",
                    ""
                ).strip()


                # ------------------------------
                # WINNER PHOTO
                # ------------------------------

                photo_file = request.files.get(
                    f"winner_photo_{i}"
                )


                photo_url = ""

                photo_public_id = ""


                # ------------------------------
                # UPLOAD TO CLOUDINARY
                # ------------------------------

                if (
                    photo_file
                    and photo_file.filename
                ):

                    result = cloudinary.uploader.upload(

                        photo_file,

                        folder=(
                            f"Gajanan-Utsav/"
                            f"Winners/"
                            f"{year}/"
                            f"{slug}"
                        )

                    )


                    photo_url = result.get(
                        "secure_url",
                        ""
                    )


                    photo_public_id = result.get(
                        "public_id",
                        ""
                    )


                # ------------------------------
                # SAVE WINNER
                # ------------------------------

                if name:

                    winners.append({

                        "position": i,

                        "name": name,

                        "photo": photo_url,

                        "photo_public_id":
                            photo_public_id

                    })


            # Save ranking winners

            data["winners"] = winners


        # ==================================================
        # AGE GROUP WINNERS
        # ==================================================

        elif winner_type == "age_group":

            groups = []


            try:

                group_count = int(
                    request.form.get(
                        "group_count",
                        "2"
                    )
                )

            except ValueError:

                group_count = 2


            # Safety limit

            group_count = max(
                1,
                min(group_count, 20)
            )


            for i in range(
                1,
                group_count + 1
            ):

                # ------------------------------
                # AGE GROUP
                # ------------------------------

                age_group = request.form.get(
                    f"age_group_{i}",
                    ""
                ).strip()


                # ------------------------------
                # WINNER NAME
                # ------------------------------

                name = request.form.get(
                    f"age_winner_{i}",
                    ""
                ).strip()


                # ------------------------------
                # WINNER PHOTO
                # ------------------------------

                photo_file = request.files.get(
                    f"age_photo_{i}"
                )


                photo_url = ""

                photo_public_id = ""


                # ------------------------------
                # UPLOAD TO CLOUDINARY
                # ------------------------------

                if (
                    photo_file
                    and photo_file.filename
                ):

                    result = cloudinary.uploader.upload(

                        photo_file,

                        folder=(
                            f"Gajanan-Utsav/"
                            f"Winners/"
                            f"{year}/"
                            f"{slug}"
                        )

                    )


                    photo_url = result.get(
                        "secure_url",
                        ""
                    )


                    photo_public_id = result.get(
                        "public_id",
                        ""
                    )


                # ------------------------------
                # SAVE AGE GROUP
                # ------------------------------

                if age_group or name:

                    groups.append({

                        "age_group": age_group,

                        "winner": {

                            "name": name,

                            "photo": photo_url,

                            "photo_public_id":
                                photo_public_id

                        }

                    })


            # Save age groups

            data["groups"] = groups


        # ==================================================
        # TEAM
        # ==================================================

        elif winner_type == "team":

            teams = []


            try:

                team_count = int(
                    request.form.get(
                        "team_count",
                        "1"
                    )
                )

            except ValueError:

                team_count = 1


            team_count = max(
                1,
                min(team_count, 20)
            )


            for i in range(
                1,
                team_count + 1
            ):

                team_name = request.form.get(
                    f"team_name_{i}",
                    ""
                ).strip()


                if team_name:

                    teams.append({

                        "team": team_name

                    })


            data["teams"] = teams


        # ==================================================
        # INVALID TYPE
        # ==================================================

        else:

            flash(
                "Invalid winner type.",
                "danger"
            )

            return redirect(
                url_for("admin_add_winner")
            )


        # ==================================================
        # VALIDATE AT LEAST ONE WINNER
        # ==================================================

        if winner_type == "ranking":

            if not data.get("winners"):

                flash(
                    "Please add at least one winner.",
                    "danger"
                )

                return redirect(
                    url_for("admin_add_winner")
                )


        elif winner_type == "age_group":

            if not data.get("groups"):

                flash(
                    "Please add at least one age group.",
                    "danger"
                )

                return redirect(
                    url_for("admin_add_winner")
                )


        elif winner_type == "team":

            if not data.get("teams"):

                flash(
                    "Please add at least one team.",
                    "danger"
                )

                return redirect(
                    url_for("admin_add_winner")
                )


        # ==================================================
        # SAVE JSON
        # ==================================================

        with open(
            file_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )


        # ==================================================
        # SUCCESS
        # ==================================================

        flash(
            "Winner Added Successfully.",
            "success"
        )


        return redirect(
            url_for("admin_winners")
        )


    # ======================================================
    # GET
    # ======================================================

    return render_template(
        "admin/add_winner.html"
    )



    
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

    # ==========================================
    # CHECK FILE
    # ==========================================

    if not os.path.exists(file_path):

        flash(
            "Winner file not found.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # LOAD DATA
    # ==========================================

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:

            game = json.load(f)

    except Exception as e:

        print(
            "Winner JSON read error:",
            e
        )

        flash(
            "Unable to read winner data.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # DELETE CLOUDINARY PHOTOS
    # ==========================================

    try:

        winner_type = game.get(
            "type",
            "ranking"
        )


        # --------------------------------------
        # RANKING
        # --------------------------------------

        if winner_type == "ranking":

            for person in game.get(
                "winners",
                []
            ):

                public_id = person.get(
                    "photo_public_id"
                )

                if public_id:

                    try:

                        cloudinary.uploader.destroy(
                            public_id,
                            resource_type="image"
                        )

                        print(
                            "Deleted Cloudinary image:",
                            public_id
                        )

                    except Exception as e:

                        print(
                            "Cloudinary delete error:",
                            e
                        )


        # --------------------------------------
        # AGE GROUP
        # --------------------------------------

        elif winner_type == "age_group":

            for group in game.get(
                "groups",
                []
            ):

                winner = group.get(
                    "winner",
                    {}
                )

                public_id = winner.get(
                    "photo_public_id"
                )

                if public_id:

                    try:

                        cloudinary.uploader.destroy(
                            public_id,
                            resource_type="image"
                        )

                        print(
                            "Deleted Cloudinary image:",
                            public_id
                        )

                    except Exception as e:

                        print(
                            "Cloudinary delete error:",
                            e
                        )


        # --------------------------------------
        # TEAM
        # --------------------------------------

        elif winner_type == "team":

            for team in game.get(
                "teams",
                []
            ):

                public_id = team.get(
                    "photo_public_id"
                )

                if public_id:

                    try:

                        cloudinary.uploader.destroy(
                            public_id,
                            resource_type="image"
                        )

                        print(
                            "Deleted Cloudinary image:",
                            public_id
                        )

                    except Exception as e:

                        print(
                            "Cloudinary delete error:",
                            e
                        )


    except Exception as e:

        print(
            "Winner Cloudinary cleanup error:",
            e
        )


    # ==========================================
    # DELETE JSON
    # ==========================================

    try:

        os.remove(file_path)

    except Exception as e:

        print(
            "Winner JSON delete error:",
            e
        )

        flash(
            "Could not delete winner record.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # SUCCESS
    # ==========================================

    flash(
        "Winner and associated photos deleted successfully.",
        "success"
    )


    return redirect(
        url_for("admin_winners")
    )




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
            skipped = 0

            for file in files:

                if not file or file.filename == "":
                    continue

                if not allowed_file(file.filename):
                    continue

                try:

                    # ==============================
                    # CREATE SHA-256 FILE HASH
                    # ==============================

                    file_bytes = file.read()

                    file_hash = hashlib.sha256(file_bytes).hexdigest()

                    # Reset file position so Cloudinary can read it
                    file.seek(0)


                    # ==============================
                    # CHECK DUPLICATE IN FIRESTORE
                    # ==============================

                    duplicate_docs = (
                        db.collection("gallery")
                        .where("file_hash", "==", file_hash)
                        .limit(1)
                        .stream()
                    )

                    duplicate_found = False

                    for duplicate_doc in duplicate_docs:
                        duplicate_found = True
                        break


                    # ==============================
                    # SKIP DUPLICATE
                    # ==============================

                    if duplicate_found:

                        print(
                            f"Duplicate image skipped: {file.filename}"
                        )
                        skipped += 1
                        continue


                    # ==============================
                    # UPLOAD TO CLOUDINARY
                    # ==============================

                    result = cloudinary.uploader.upload(
                        file,
                        folder=f"Gajanan-Utsav/{year}/{event}"
                    )


                    # ==============================
                    # SAVE TO FIRESTORE
                    # ==============================

                    db.collection("gallery").document().set({

                        "year": year,

                        "event": event,

                        "url": result["secure_url"],

                        "public_id": result["public_id"],

                        "file_hash": file_hash

                    })


                    uploaded += 1

                    print(
                        f"Uploaded successfully: {file.filename}"
                    )


                except Exception as e:

                    print(
                        f"Error uploading {file.filename}: {e}"
                    )

            flash(

                f"{uploaded} image(s) uploaded, {skipped} skipped.",

                "success"

            )

            return redirect(url_for("admin_gallery"))

        except Exception:

            import traceback

            error = traceback.format_exc()

            print(error)

            return f"<pre>{error}</pre>"

    gallery = load_gallery()

    return render_template(
        "admin/gallery.html",
        gallery=gallery
    )


@app.route("/admin/gallery/delete", methods=["POST"])
def delete_gallery_image():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    public_id = request.form.get("public_id")
    doc_id = request.form.get("doc_id")

    if not public_id or not doc_id:
        flash("Invalid image data.", "danger")
        return redirect(url_for("admin_gallery"))

    try:

        # Cloudinary
        cloudinary.uploader.destroy(public_id)

        # Firestore
        db.collection("gallery").document(doc_id).delete()

        flash("Image deleted successfully.", "success")

    except Exception as e:

        print("DELETE ERROR:", e)

        flash("Unable to delete image.", "danger")

    return redirect(url_for("admin_gallery"))










@app.route("/admin/videos", methods=["GET", "POST"])
def admin_videos():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # ==============================
    # UPLOAD VIDEO
    # ==============================

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        year = request.form.get("year", "").strip()
        event = request.form.get("event", "").strip()

        video_file = request.files.get("video")

        # Basic validation
        if not title or not year or not event:
            flash(
                "Title, Year and Event are required.",
                "danger"
            )
            return redirect(url_for("admin_videos"))

        if not video_file or not video_file.filename:
            flash(
                "Please select a video.",
                "danger"
            )
            return redirect(url_for("admin_videos"))
        
        if not allowed_video_file(video_file.filename):

            flash(
                "Invalid video format. Allowed formats: MP4, MOV, AVI, MKV, WEBM and M4V.",
                "danger"
            )

            return redirect(
                url_for("admin_videos")
            )

        # Check YouTube connection
        youtube = get_youtube_service()

        if not youtube:
            flash(
                "YouTube account is not connected.",
                "danger"
            )
            return redirect(url_for("admin_videos"))

        temp_path = None

        try:

            # =====================================
            # SAVE TEMPORARILY
            # =====================================

            suffix = os.path.splitext(
                video_file.filename
            )[1]

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix
            )

            temp_path = temp_file.name

            temp_file.close()

            video_file.save(temp_path)
            
            # =====================================
            # CALCULATE VIDEO HASH
            # =====================================

            video_hash = calculate_file_hash(temp_path)

            print(
                "Video SHA-256:",
                video_hash
            )


            # =====================================
            # CHECK DUPLICATE VIDEO
            # =====================================

            duplicate_docs = (
                db.collection("videos")
                .where("file_hash", "==", video_hash)
                .limit(1)
                .stream()
            )

            duplicate_found = False

            for duplicate_doc in duplicate_docs:

                duplicate_found = True
                break


            if duplicate_found:

                flash(
                    "This exact video has already been uploaded.",
                    "warning"
                )

                return redirect(
                    url_for("admin_videos")
                )

            
            
            

            # =====================================
            # YOUTUBE VIDEO METADATA
            # =====================================

            body = {

                "snippet": {

                    "title": title,

                    "description": (
                        f"{event}\n\n"
                        f"Gajanan Utsav Samiti {year}\n"
                        f"Event: {event}\n"
                        f"Year: {year}"
                    ),

                    "categoryId": "22"

                },

                "status": {

                    "privacyStatus": "unlisted",

                    "selfDeclaredMadeForKids": False

                }

            }


            # =====================================
            # UPLOAD TO YOUTUBE
            # =====================================

            media = MediaFileUpload(
                temp_path,
                mimetype=video_file.mimetype,
                resumable=True,
                chunksize=8 * 1024 * 1024
            )


            print("Starting YouTube upload...")

            request_upload = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )


            response = None

            while response is None:

                status, response = (
                    request_upload.next_chunk()
                )

                if status:

                    progress = int(
                        status.progress() * 100
                    )

                    print(
                        f"YouTube Upload: {progress}%"
                    )


            youtube_id = response.get("id")


            if not youtube_id:

                raise Exception(
                    "YouTube did not return a video ID."
                )


            print(
                "YouTube Upload Success:",
                youtube_id
            )


            # =====================================
            # SAVE TO FIRESTORE
            # =====================================

            db.collection("videos").add({

                "title": title,

                "year": year,

                "event": event,

                "youtube_id": youtube_id,

                "youtube_url": (
                    f"https://www.youtube.com/watch?v={youtube_id}"
                ),

                "embed_url": (
                    f"https://www.youtube.com/embed/{youtube_id}"
                ),

                "privacy_status": "unlisted",

                "file_hash": video_hash,

                "created_at": firestore.SERVER_TIMESTAMP

            })


            flash(
                "Video uploaded to YouTube successfully.",
                "success"
            )

            return redirect(
                url_for("admin_videos")
            )


        except Exception as e:

            import traceback

            print(
                "YOUTUBE UPLOAD ERROR:"
            )

            print(
                traceback.format_exc()
            )

            flash(
                f"Video upload failed: {str(e)}",
                "danger"
            )

            return redirect(
                url_for("admin_videos")
            )


        finally:

            # =====================================
            # DELETE TEMPORARY FILE
            # =====================================

            if temp_path:

                try:

                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                except Exception as e:

                    print(
                        "Temporary file cleanup error:",
                        e
                    )


    # ==========================================
    # LOAD VIDEOS FROM FIRESTORE
    # ==========================================

    videos = []

    docs = (
        db.collection("videos")
        .order_by(
            "created_at",
            direction=firestore.Query.DESCENDING
        )
        .stream()
    )

    for doc in docs:

        data = doc.to_dict()

        data["doc_id"] = doc.id

        videos.append(data)


    return render_template(
        "admin/videos.html",
        videos=videos
    )
    

@app.route("/admin/videos/delete", methods=["POST"])
def delete_video():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    doc_id = request.form.get("doc_id")
    youtube_id = request.form.get("youtube_id")

    if not doc_id or not youtube_id:

        flash(
            "Invalid video information.",
            "danger"
        )

        return redirect(
            url_for("admin_videos")
        )

    try:

        # ==============================
        # DELETE FROM YOUTUBE
        # ==============================

        youtube = get_youtube_service()

        if youtube:

            youtube.videos().delete(
                id=youtube_id
            ).execute()


        # ==============================
        # DELETE FROM FIRESTORE
        # ==============================

        db.collection("videos") \
            .document(doc_id) \
            .delete()


        flash(
            "Video deleted successfully from YouTube and website.",
            "success"
        )


    except Exception as e:

        import traceback

        print(
            "VIDEO DELETE ERROR:"
        )

        print(
            traceback.format_exc()
        )

        flash(
            f"Video deletion failed: {str(e)}",
            "danger"
        )


    return redirect(
        url_for("admin_videos")
    )
    




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

    gallery = load_gallery()

    # ==========================================
    # LATEST GALLERY
    # ==========================================

    latest_gallery = []

    for year in sorted(gallery.keys(), reverse=True):

        for event in gallery[year]:

            for photo in gallery[year][event]:

                latest_gallery.append(photo)

    latest_gallery = latest_gallery[:6]


    # ==========================================
    # LATEST WINNERS
    # ==========================================

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


 

    # ==========================================
    # FESTIVAL GLIMPSE 2025
    # ==========================================

    home_video_2025 = None

    try:

        video_docs = (
            db.collection("videos")
            .stream()
        )

        all_2025_videos = []

        for doc in video_docs:

            data = doc.to_dict()

            # Year चाहे string हो या number,
            # दोनों में काम करेगा

            if str(data.get("year", "")).strip() == "2025":

                data["doc_id"] = doc.id

                all_2025_videos.append(data)


        # Latest uploaded 2025 video
        if all_2025_videos:

            all_2025_videos.sort(
                key=lambda x: x.get("created_at"),
                reverse=True
            )

            home_video_2025 = all_2025_videos[0]


    except Exception as e:

        print(
            "Home 2025 video loading error:",
            e
        )

    # ==========================================
    # HOME PAGE
    # ==========================================

    return render_template(
        "home.html",
        notice=notice,
        schedule=schedule,
        committee=committee,
        latest_gallery=latest_gallery,
        latest_winners=latest_winners,
        home_video_2025=home_video_2025,
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
        "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; "
        "media-src 'self' blob:; "
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
