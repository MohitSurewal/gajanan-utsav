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
from google.auth.exceptions import RefreshError
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

# ==========================================
# GLOBAL ADMIN PROTECTION
# ==========================================

@app.before_request
def protect_admin_routes():

    # Sirf /admin/ wale pages protect karo
    if not request.path.startswith("/admin"):
        return None

    # Login page ko public rakho
    if request.path == "/admin/login":
        return None

    # Logout ko bhi allow karo
    if request.path == "/admin/logout":
        return None

    # Admin login check
    if not session.get("admin"):
        return redirect(
            url_for("admin_login")
        )

    return None


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

    doc_ref = (
        db
        .collection("settings")
        .document("youtube")
    )

    doc = doc_ref.get()

    # ==========================================
    # YOUTUBE NOT CONNECTED
    # ==========================================

    if not doc.exists:
        print("[YouTube] Account is not connected.")
        return None

    data = doc.to_dict() or {}

    refresh_token = data.get("refresh_token")

    if not refresh_token:
        print("[YouTube] Refresh token missing.")
        return None

    # ==========================================
    # CREATE CREDENTIALS
    # ==========================================

    youtube_credentials = Credentials(

        token=data.get("token"),

        refresh_token=refresh_token,

        token_uri=data.get(
            "token_uri",
            "https://oauth2.googleapis.com/token"
        ),

        client_id=data.get(
            "client_id",
            YOUTUBE_CLIENT_ID
        ),

        client_secret=YOUTUBE_CLIENT_SECRET,

        scopes=data.get(
            "scopes",
            YOUTUBE_SCOPES
        )
    )

    # ==========================================
    # REFRESH ACCESS TOKEN
    # ==========================================

    if youtube_credentials.expired:

        try:

            print(
                "[YouTube] Access token expired. "
                "Refreshing..."
            )

            youtube_credentials.refresh(
                Request()
            )

            # Save new access token
            doc_ref.update({

                "token":
                    youtube_credentials.token

            })

            print(
                "[YouTube] Access token refreshed successfully."
            )

        except RefreshError as e:

            print(
                "[YouTube] Refresh token is invalid "
                "or revoked."
            )

            print(
                "[YouTube] RefreshError:",
                str(e)
            )

            # Mark connection as invalid
            try:

                doc_ref.update({

                    "connection_status":
                        "reauthorization_required"

                })

            except Exception:
                pass

            return None

        except Exception as e:

            print(
                "[YouTube] Token refresh failed:",
                str(e)
            )

            return None

    return youtube_credentials


def get_youtube_service():

    try:

        youtube_credentials = (
            get_youtube_credentials()
        )

        if not youtube_credentials:

            print(
                "[YouTube] No valid credentials."
            )

            return None

        youtube = build(
            "youtube",
            "v3",
            credentials=youtube_credentials
        )

        return youtube

    except Exception as e:

        print(
            "[YouTube] Service creation failed:",
            str(e)
        )

        return None
    
    
    

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










def slugify_event(text):
    return (
        str(text or "")
        .strip()
        .lower()
        .replace(" ", "-")
    )


def load_winners():

    winners = defaultdict(list)

    try:

        docs = (
            db.collection("winners")
            .stream()
        )

        for doc in docs:

            game = doc.to_dict()

            if not game:
                continue

            # ==========================================
            # YEAR
            # ==========================================

            year = str(
                game.get("year", "")
            ).strip()

            if not year:

                # Firestore ID example:
                # 2025-best-dancer

                doc_id = doc.id

                if "-" in doc_id:
                    year = doc_id.split("-", 1)[0]

            if not year:
                continue


            # ==========================================
            # BASIC DATA
            # ==========================================

            game["year"] = year

            game["doc_id"] = doc.id

            game["slug"] = (
                game.get("slug")
                or doc.id.replace(
                    f"{year}-",
                    "",
                    1
                )
            )


            # ==========================================
            # GALLERY EVENT
            # ==========================================
            #
            # Gallery me event generally game-name
            # ka slug hai.
            #
            # Example:
            # Dance Competition
            #       ↓
            # dance-competition
            #
            # Isse purane winners ke wrong gallery
            # slug ka problem bhi fix hoga.
            # ==========================================

            game["gallery_event"] = slugify_event(
                game.get("game")
            )

            # Keep gallery field compatible
            game["gallery"] = game["gallery_event"]


            # ==========================================
            # STATUS NORMALIZE
            # ==========================================

            status = str(
                game.get(
                    "status",
                    "Completed"
                )
            ).strip().lower()

            game["status"] = status


            # ==========================================
            # DATE
            # ==========================================

            game["date"] = str(
                game.get(
                    "date",
                    ""
                )
            ).strip()


            winners[year].append(game)


        # ==========================================
        # SORT EACH YEAR
        # ==========================================
        #
        # Latest date first.
        #
        # Example:
        #
        # 2025-09-10
        # 2025-09-08
        # 2025-09-03
        #
        # ==========================================

        for year in winners:

            winners[year].sort(
                key=lambda game: (
                    game.get("date", ""),
                    game.get("created_at", "")
                ),
                reverse=True
            )


        # ==========================================
        # SORT YEARS
        # ==========================================

        winners = dict(
            sorted(
                winners.items(),
                key=lambda item: int(
                    item[0]
                )
                if str(item[0]).isdigit()
                else 0,
                reverse=True
            )
        )


        print(
            f"[Winner Loader] Loaded "
            f"{sum(len(v) for v in winners.values())} "
            f"winner games from Firestore."
        )


        return winners


    except Exception as e:

        import traceback

        print(
            "======================================"
        )

        print(
            "WINNER FIRESTORE LOAD ERROR"
        )

        print(
            traceback.format_exc()
        )

        print(
            "======================================"
        )

        return {}


# ============================================================
# HALL OF FAME CALCULATOR
# ============================================================

def load_hall_of_fame():

    winners_data = load_winners()

    # =========================================================
    # FIND CURRENT / LATEST YEAR
    # =========================================================

    if not winners_data:
        return {
            "year": None,
            "players": [],
            "champion": None,
            "is_tie": False,
            "tie_players": [],
            "highest_wins": 0
        }

    valid_years = []

    for year in winners_data.keys():
        try:
            valid_years.append(int(year))
        except (ValueError, TypeError):
            continue

    if not valid_years:
        return {
            "year": None,
            "players": [],
            "champion": None,
            "is_tie": False,
            "tie_players": [],
            "highest_wins": 0
        }

    current_year = max(valid_years)

    games = winners_data.get(str(current_year), [])

    if not games:
        games = winners_data.get(current_year, [])

    # =========================================================
    # PLAYER DATA
    # =========================================================

    players = {}

    def get_player(name):

        name = (name or "").strip()

        if not name:
            return None

        key = " ".join(name.lower().split())

        if key not in players:

            players[key] = {
                "name": name,
                "wins": 0,
                "gold": 0,
                "silver": 0,
                "bronze": 0,
                "total": 0,
                "awards": []
            }

        return players[key]

    # =========================================================
    # PROCESS CURRENT YEAR GAMES ONLY
    # =========================================================

    for game in games:

        game_type = game.get("type", "ranking")

        game_name = game.get(
            "game",
            "Competition"
        )

        # =====================================================
        # RANKING GAME
        # =====================================================

        if game_type == "ranking":

            for person in game.get("winners", []):

                name = person.get(
                    "name",
                    ""
                ).strip()

                if not name:
                    continue

                player = get_player(name)

                position = person.get(
                    "position",
                    1
                )

                try:
                    position = int(position)
                except (ValueError, TypeError):
                    position = 1

                # ONE GAME WIN = ONE WIN
                player["wins"] += 1
                player["total"] += 1

                # Medal information
                if position == 1:
                    player["gold"] += 1

                elif position == 2:
                    player["silver"] += 1

                elif position == 3:
                    player["bronze"] += 1

                player["awards"].append({
                    "year": current_year,
                    "game": game_name,
                    "position": position
                })

        # =====================================================
        # AGE GROUP GAME
        # =====================================================

        elif game_type == "age_group":

            for group in game.get(
                "groups",
                []
            ):

                winner = group.get(
                    "winner",
                    {}
                )

                name = winner.get(
                    "name",
                    ""
                ).strip()

                if not name:
                    continue

                player = get_player(name)

                # ONE AGE GROUP WIN = ONE WIN
                player["wins"] += 1
                player["total"] += 1

                # Winner of age group
                player["gold"] += 1

                age_group = group.get(
                    "age_group",
                    ""
                ).strip()

                display_game = game_name

                if age_group:
                    display_game = (
                        f"{game_name} ({age_group})"
                    )

                player["awards"].append({
                    "year": current_year,
                    "game": display_game,
                    "position": 1
                })

        # =====================================================
        # TEAM GAME
        # =====================================================

        elif game_type == "team":

            for team in game.get(
                "teams",
                []
            ):

                name = (
                    team.get("name")
                    or team.get("team")
                    or ""
                ).strip()

                if not name:
                    continue

                player = get_player(name)

                # ONE TEAM WIN = ONE WIN
                player["wins"] += 1
                player["total"] += 1
                player["gold"] += 1

                player["awards"].append({
                    "year": current_year,
                    "game": game_name,
                    "position": 1
                })

    # =========================================================
    # CONVERT TO LIST
    # =========================================================

    player_list = list(
        players.values()
    )

    # =========================================================
    # SORT
    # MOST WINS FIRST
    # =========================================================

    player_list.sort(
        key=lambda person: (
            -person["wins"],
            -person["gold"],
            -person["silver"],
            -person["bronze"],
            person["name"].lower()
        )
    )

    # =========================================================
    # NO PLAYERS
    # =========================================================

    if not player_list:

        return {
            "year": current_year,
            "players": [],
            "champion": None,
            "is_tie": False,
            "tie_players": [],
            "highest_wins": 0
        }

    # =========================================================
    # HIGHEST NUMBER OF WINS
    # =========================================================

    highest_wins = player_list[0]["wins"]

    # =========================================================
    # FIND ALL PLAYERS WITH HIGHEST WINS
    # =========================================================

    tie_players = [
        person
        for person in player_list
        if person["wins"] == highest_wins
    ]

    is_tie = len(tie_players) > 1

    # =========================================================
    # CHAMPION RULE
    #
    # Minimum 2 wins
    # AND
    # No tie
    # =========================================================

    champion = None

    if (
        highest_wins >= 2
        and not is_tie
    ):

        champion = player_list[0]

    # =========================================================
    # RANK + GAP + PRIZE ELIGIBILITY
    # =========================================================

    for index, person in enumerate(
        player_list,
        start=1
    ):

        person["rank"] = index

        person["wins_behind"] = (
            highest_wins
            - person["wins"]
        )

        person["eligible_for_prize"] = (
            person["wins"] >= 2
            and index == 1
            and not is_tie
        )

    # =========================================================
    # FINAL RESULT
    # =========================================================

    return {
        "year": current_year,

        "players": player_list,

        "champion": champion,

        "is_tie": is_tie,

        "tie_players": tie_players,

        "highest_wins": highest_wins
    }

# WINNERS - MIGRATE JSON DATA TO FIRESTORE
# ============================================================

def migrate_winners_to_firestore():

    """
    Existing JSON winners ko Firestore me safely migrate karta hai.

    IMPORTANT:
    - Original JSON files delete nahi hoti.
    - Existing Firestore documents overwrite nahi hote.
    - Same migration baar-baar chalane par duplicate nahi banega.
    - Har JSON winner/game ek Firestore document banega.
    """

    winners_path = os.path.join(
        BASE_DIR,
        "data",
        "winners"
    )


    # ========================================================
    # CHECK WINNERS FOLDER
    # ========================================================

    if not os.path.exists(winners_path):

        return {
            "success": False,
            "message": (
                "data/winners folder nahi mila."
            ),
            "migrated": 0,
            "skipped": 0,
            "errors": []
        }


    migrated = 0
    skipped = 0

    errors = []

    migrated_documents = []

    skipped_documents = []


    # ========================================================
    # READ YEAR FOLDERS
    # ========================================================

    years = sorted(
        os.listdir(winners_path),
        reverse=True
    )


    for year in years:

        year_path = os.path.join(
            winners_path,
            year
        )


        # Ignore files
        if not os.path.isdir(year_path):
            continue


        # ====================================================
        # READ JSON FILES
        # ====================================================

        files = sorted(
            os.listdir(year_path)
        )


        for filename in files:

            if not filename.lower().endswith(
                ".json"
            ):
                continue


            file_path = os.path.join(
                year_path,
                filename
            )


            try:

                # ==========================================
                # LOAD JSON
                # ==========================================

                with open(
                    file_path,
                    "r",
                    encoding="utf-8"
                ) as f:

                    game = json.load(f)


                # ==========================================
                # VALIDATE JSON
                # ==========================================

                if not isinstance(
                    game,
                    dict
                ):

                    skipped += 1

                    skipped_documents.append({
                        "year": year,
                        "file": filename,
                        "reason": (
                            "JSON object nahi hai."
                        )
                    })

                    continue


                # ==========================================
                # GET SLUG
                # ==========================================

                slug = (
                    game.get("slug")
                    or game.get("id")
                )


                if not slug:

                    skipped += 1

                    skipped_documents.append({
                        "year": year,
                        "file": filename,
                        "reason": (
                            "slug/id missing hai."
                        )
                    })

                    continue


                slug = str(slug).strip()


                # ==========================================
                # DOCUMENT ID
                # ==========================================

                document_id = (
                    f"{year}-{slug}"
                )


                document_ref = (
                    db
                    .collection("winners")
                    .document(document_id)
                )


                # ==========================================
                # CHECK EXISTING DOCUMENT
                # ==========================================

                existing_doc = (
                    document_ref.get()
                )


                if existing_doc.exists:

                    skipped += 1

                    skipped_documents.append({
                        "year": year,
                        "file": filename,
                        "document": document_id,
                        "reason": (
                            "Already Firestore me exist karta hai."
                        )
                    })

                    continue


                # ==========================================
                # PREPARE DATA
                # ==========================================

                firestore_data = dict(game)


                # Make sure year exists
                firestore_data["year"] = str(
                    year
                )


                # Make sure slug exists
                firestore_data["slug"] = slug


                # Migration information
                firestore_data[
                    "migrated_from"
                ] = "json"


                firestore_data[
                    "source_file"
                ] = filename


                firestore_data[
                    "created_at"
                ] = firestore.SERVER_TIMESTAMP


                # ==========================================
                # SAVE FIRESTORE
                # ==========================================

                document_ref.set(
                    firestore_data
                )


                migrated += 1


                migrated_documents.append({
                    "year": year,
                    "game": game.get(
                        "game",
                        "Unknown Game"
                    ),
                    "document": document_id
                })


                print(
                    "[WINNERS MIGRATION SUCCESS]",
                    document_id
                )


            except Exception as e:

                skipped += 1

                error_message = (
                    f"{type(e).__name__}: {str(e)}"
                )


                errors.append({
                    "year": year,
                    "file": filename,
                    "error": error_message
                })


                print(
                    "[WINNERS MIGRATION ERROR]"
                )

                print(
                    "Year:",
                    year
                )

                print(
                    "File:",
                    filename
                )

                print(
                    "Error:",
                    error_message
                )


    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {

        "success": True,

        "message": (
            "Winner migration complete."
        ),

        "migrated": migrated,

        "skipped": skipped,

        "errors": errors,

        "migrated_documents":
            migrated_documents,

        "skipped_documents":
            skipped_documents
    }


# ============================================================
# ADMIN - RUN WINNER MIGRATION
# ============================================================

@app.route(
    "/admin/migrate-winners",
    methods=["GET"]
)
def admin_migrate_winners():

    # ========================================================
    # ADMIN LOGIN CHECK
    # ========================================================

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    # ========================================================
    # RUN MIGRATION
    # ========================================================

    try:

        result = (
            migrate_winners_to_firestore()
        )


        # ====================================================
        # PREPARE RESULT
        # ====================================================

        migrated = result.get(
            "migrated",
            0
        )

        skipped = result.get(
            "skipped",
            0
        )

        errors = result.get(
            "errors",
            []
        )

        migrated_documents = (
            result.get(
                "migrated_documents",
                []
            )
        )

        skipped_documents = (
            result.get(
                "skipped_documents",
                []
            )
        )


        # ====================================================
        # SUCCESS PAGE
        # ====================================================

        return render_template(
            "admin/migration_result.html",

            success=result.get(
                "success",
                False
            ),

            message=result.get(
                "message",
                ""
            ),

            migrated=migrated,

            skipped=skipped,

            errors=errors,

            migrated_documents=
                migrated_documents,

            skipped_documents=
                skipped_documents
        )


    except Exception as e:

        import traceback

        error = traceback.format_exc()


        print(
            "========================================"
        )

        print(
            "WINNERS MIGRATION FATAL ERROR"
        )

        print(
            error
        )

        print(
            "========================================"
        )


        return f"""
        <html>

        <head>

            <title>
                Winners Migration Error
            </title>

            <meta
                name="viewport"
                content="width=device-width,
                         initial-scale=1"
            >

            <style>

                body {{
                    font-family: Arial, sans-serif;
                    background: #f5f5f5;
                    padding: 30px;
                }}

                .box {{
                    max-width: 1000px;
                    margin: auto;
                    background: white;
                    padding: 30px;
                    border-radius: 16px;
                    box-shadow:
                        0 10px 30px
                        rgba(0,0,0,.10);
                }}

                h1 {{
                    color: #c62828;
                }}

                pre {{
                    background: #111;
                    color: #ff7777;
                    padding: 20px;
                    border-radius: 10px;
                    overflow-x: auto;
                    white-space: pre-wrap;
                }}

                a {{
                    display: inline-block;
                    margin-top: 20px;
                    padding: 12px 18px;
                    background: #b8860b;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                }}

            </style>

        </head>


        <body>

            <div class="box">

                <h1>
                    ❌ Winners Migration Failed
                </h1>

                <pre>
{error}
                </pre>

                <a href="/admin/winners">
                    ← Back to Winners Manager
                </a>

            </div>

        </body>

        </html>
        """







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
    # ==========================================
    # CHECK REFRESH TOKEN
    # ==========================================

    if not credentials.refresh_token:

        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>YouTube Connection Failed</title>
        </head>

        <body style="
            font-family: Arial;
            text-align: center;
            padding: 80px;
        ">

            <h1 style="color:#c62828;">
                ❌ YouTube Connection Failed
            </h1>

            <p>
                Google did not provide a refresh token.
            </p>

            <p>
                Please try connecting YouTube again.
            </p>

        </body>
        </html>
        """, 400


    # ==========================================
    # SAVE FRESH YOUTUBE CREDENTIALS
    # ==========================================

    db.collection("settings").document("youtube").set({

        "token":
            credentials.token,

        "refresh_token":
            credentials.refresh_token,

        "token_uri":
            credentials.token_uri,

        "client_id":
            credentials.client_id,

        "scopes":
            credentials.scopes,

        "connection_status":
            "connected",

        "updated_at":
            firestore.SERVER_TIMESTAMP

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

    # ==========================================
    # YEARS — LATEST FIRST
    # ==========================================

    years = sorted(
        winners_data.keys(),
        key=lambda x: (
            int(x)
            if str(x).isdigit()
            else 0
        ),
        reverse=True
    )


    # ==========================================
    # ALL GAMES
    # ==========================================
    #
    # Already sorted by load_winners():
    #
    # Year:
    #   latest → oldest
    #
    # Within year:
    #   latest date → oldest date
    #
    # ==========================================

    games = []

    seen = set()

    for year in years:

        for game in winners_data.get(
            year,
            []
        ):

            slug = game.get(
                "slug"
            )

            unique_id = (
                f"{year}-{slug}"
            )

            if unique_id in seen:
                continue

            seen.add(
                unique_id
            )

            games.append({

                "year":
                    year,

                "slug":
                    slug,

                "game":
                    game.get(
                        "game",
                        ""
                    ),

                "date":
                    game.get(
                        "date",
                        ""
                    )

            })


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

    players = hall.get("players", [])

    top_three = players[:3]

    return render_template(
        "hall_of_fame.html",

        hall_of_fame=players,

        top_three=top_three,

        current_year=hall.get("year"),

        champion=hall.get("champion"),

        is_tie=hall.get("is_tie", False),

        tie_players=hall.get("tie_players", []),

        highest_wins=hall.get("highest_wins", 0),

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
        return redirect(
            url_for("admin_login")
        )

    winners = load_winners()

    return render_template(
        "admin/winners.html",
        winners=winners
    )
    
    
    
@app.route("/admin/winners/edit/<year>/<slug>", methods=["GET", "POST"])
def admin_edit_winner(year, slug):

    # ==========================================
    # ADMIN LOGIN CHECK
    # ==========================================

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    # ==========================================
    # FIRESTORE DOCUMENT
    # ==========================================

    document_id = f"{year}-{slug}"

    winner_ref = (
        db
        .collection("winners")
        .document(document_id)
    )


    # ==========================================
    # LOAD FROM FIRESTORE
    # ==========================================

    winner_doc = winner_ref.get()


    if not winner_doc.exists:

        # --------------------------------------
        # FALLBACK TO JSON
        # --------------------------------------

        winner_file = os.path.join(
            BASE_DIR,
            "data",
            "winners",
            str(year),
            f"{slug}.json"
        )


        if not os.path.exists(winner_file):

            flash(
                "Winner record not found.",
                "danger"
            )

            return redirect(
                url_for("admin_winners")
            )


        try:

            with open(
                winner_file,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)


        except Exception as e:

            print(
                "Winner JSON Load Error:",
                e
            )

            flash(
                "Unable to load winner record.",
                "danger"
            )

            return redirect(
                url_for("admin_winners")
            )


    else:

        data = winner_doc.to_dict()


    if not data:

        flash(
            "Winner data is empty.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # POST
    # ==========================================

    if request.method == "POST":

        try:

            game_type = data.get(
                "type",
                "ranking"
            )


            # ======================================
            # RANKING GAME
            # ======================================

            if game_type == "ranking":

                winners = []

                winner_count = int(
                    request.form.get(
                        "winner_count",
                        0
                    )
                )


                old_winners = data.get(
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


                    position = request.form.get(
                        f"winner_position_{i}",
                        str(i)
                    ).strip()


                    age = request.form.get(
                        f"winner_age_{i}",
                        ""
                    ).strip()


                    # ----------------------------------
                    # SKIP EMPTY WINNER
                    # ----------------------------------

                    if not name:

                        continue


                    # ----------------------------------
                    # POSITION
                    # ----------------------------------

                    try:

                        position_value = int(
                            position
                        )

                    except:

                        position_value = i


                    # ----------------------------------
                    # AGE
                    # ----------------------------------

                    if age:

                        try:

                            age_value = int(
                                age
                            )

                        except:

                            age_value = age

                    else:

                        age_value = ""


                    # ----------------------------------
                    # OLD PHOTO
                    # ----------------------------------

                    old_photo = ""

                    old_photo_public_id = ""


                    if i <= len(old_winners):

                        old_winner = (
                            old_winners[
                                i - 1
                            ]
                        )


                        if isinstance(
                            old_winner,
                            dict
                        ):

                            old_photo = (
                                old_winner.get(
                                    "photo",
                                    ""
                                )
                            )


                            old_photo_public_id = (
                                old_winner.get(
                                    "photo_public_id",
                                    ""
                                )
                            )


                    # ----------------------------------
                    # NEW PHOTO
                    # ----------------------------------

                    photo_file = request.files.get(
                        f"winner_photo_{i}"
                    )


                    photo_url = old_photo

                    photo_public_id = (
                        old_photo_public_id
                    )


                    if (
                        photo_file
                        and photo_file.filename
                    ):

                        if not allowed_file(
                            photo_file.filename
                        ):

                            flash(
                                f"Invalid photo format for Winner {i}.",
                                "danger"
                            )

                            return redirect(
                                url_for(
                                    "admin_edit_winner",
                                    year=year,
                                    slug=slug
                                )
                            )


                        upload_result = (
                            cloudinary
                            .uploader
                            .upload(
                                photo_file,
                                folder=(
                                    "Gajanan-Utsav/"
                                    f"Winners/"
                                    f"{year}/"
                                    f"{slug}"
                                ),
                                resource_type="image"
                            )
                        )


                        photo_url = (
                            upload_result.get(
                                "secure_url",
                                old_photo
                            )
                        )


                        photo_public_id = (
                            upload_result.get(
                                "public_id",
                                old_photo_public_id
                            )
                        )


                    # ----------------------------------
                    # SAVE WINNER
                    # ----------------------------------

                    winner_data = {

                        "position":
                            position_value,

                        "name":
                            name,

                        "age":
                            age_value,

                        "photo":
                            photo_url,

                        "photo_public_id":
                            photo_public_id

                    }


                    winners.append(
                        winner_data
                    )


                # ----------------------------------
                # SORT BY POSITION
                # ----------------------------------

                winners.sort(
                    key=lambda x:
                        x.get(
                            "position",
                            999
                        )
                )


                data["winners"] = winners


            # ======================================
            # AGE GROUP GAME
            # ======================================

            elif game_type == "age_group":

                groups = []

                group_count = int(
                    request.form.get(
                        "group_count",
                        0
                    )
                )


                old_groups = data.get(
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


                    winner_name = request.form.get(
                        f"age_winner_{i}",
                        ""
                    ).strip()


                    winner_age = request.form.get(
                        f"age_winner_age_{i}",
                        ""
                    ).strip()


                    # ----------------------------------
                    # SKIP EMPTY GROUP
                    # ----------------------------------

                    if (
                        not age_group
                        and not winner_name
                    ):

                        continue


                    # ----------------------------------
                    # AGE
                    # ----------------------------------

                    if winner_age:

                        try:

                            age_value = int(
                                winner_age
                            )

                        except:

                            age_value = winner_age

                    else:

                        age_value = ""


                    # ----------------------------------
                    # OLD PHOTO
                    # ----------------------------------

                    old_photo = ""

                    old_photo_public_id = ""


                    if i <= len(old_groups):

                        old_group = (
                            old_groups[
                                i - 1
                            ]
                        )


                        if isinstance(
                            old_group,
                            dict
                        ):

                            old_winner = (
                                old_group.get(
                                    "winner",
                                    {}
                                )
                            )


                            if isinstance(
                                old_winner,
                                dict
                            ):

                                old_photo = (
                                    old_winner.get(
                                        "photo",
                                        ""
                                    )
                                )


                                old_photo_public_id = (
                                    old_winner.get(
                                        "photo_public_id",
                                        ""
                                    )
                                )


                    # ----------------------------------
                    # NEW PHOTO
                    # ----------------------------------

                    photo_file = request.files.get(
                        f"age_photo_{i}"
                    )


                    photo_url = old_photo

                    photo_public_id = (
                        old_photo_public_id
                    )


                    if (
                        photo_file
                        and photo_file.filename
                    ):

                        if not allowed_file(
                            photo_file.filename
                        ):

                            flash(
                                f"Invalid photo format for Age Group {i}.",
                                "danger"
                            )

                            return redirect(
                                url_for(
                                    "admin_edit_winner",
                                    year=year,
                                    slug=slug
                                )
                            )


                        upload_result = (
                            cloudinary
                            .uploader
                            .upload(
                                photo_file,
                                folder=(
                                    "Gajanan-Utsav/"
                                    f"Winners/"
                                    f"{year}/"
                                    f"{slug}"
                                ),
                                resource_type="image"
                            )
                        )


                        photo_url = (
                            upload_result.get(
                                "secure_url",
                                old_photo
                            )
                        )


                        photo_public_id = (
                            upload_result.get(
                                "public_id",
                                old_photo_public_id
                            )
                        )


                    # ----------------------------------
                    # SAVE GROUP
                    # ----------------------------------

                    group_data = {

                        "age_group":
                            age_group,

                        "winner": {

                            "name":
                                winner_name,

                            "age":
                                age_value,

                            "photo":
                                photo_url,

                            "photo_public_id":
                                photo_public_id

                        }

                    }


                    groups.append(
                        group_data
                    )


                data["groups"] = groups


            # ======================================
            # TEAM GAME
            # ======================================

            elif game_type == "team":

                teams = []

                team_count = int(
                    request.form.get(
                        "team_count",
                        0
                    )
                )


                old_teams = data.get(
                    "teams",
                    []
                )


                for i in range(
                    1,
                    team_count + 1
                ):

                    team_name = request.form.get(
                        f"team_name_{i}",
                        ""
                    ).strip()


                    if not team_name:

                        continue


                    old_photo = ""

                    old_photo_public_id = ""


                    if i <= len(old_teams):

                        old_team = (
                            old_teams[
                                i - 1
                            ]
                        )


                        if isinstance(
                            old_team,
                            dict
                        ):

                            old_photo = (
                                old_team.get(
                                    "photo",
                                    ""
                                )
                            )

                            old_photo_public_id = (
                                old_team.get(
                                    "photo_public_id",
                                    ""
                                )
                            )


                    photo_file = request.files.get(
                        f"team_photo_{i}"
                    )


                    photo_url = old_photo

                    photo_public_id = (
                        old_photo_public_id
                    )


                    if (
                        photo_file
                        and photo_file.filename
                    ):

                        if not allowed_file(
                            photo_file.filename
                        ):

                            flash(
                                f"Invalid photo format for Team {i}.",
                                "danger"
                            )

                            return redirect(
                                url_for(
                                    "admin_edit_winner",
                                    year=year,
                                    slug=slug
                                )
                            )


                        upload_result = (
                            cloudinary
                            .uploader
                            .upload(
                                photo_file,
                                folder=(
                                    "Gajanan-Utsav/"
                                    f"Winners/"
                                    f"{year}/"
                                    f"{slug}"
                                ),
                                resource_type="image"
                            )
                        )


                        photo_url = (
                            upload_result.get(
                                "secure_url",
                                old_photo
                            )
                        )


                        photo_public_id = (
                            upload_result.get(
                                "public_id",
                                old_photo_public_id
                            )
                        )


                    teams.append({

                        "team":
                            team_name,

                        "photo":
                            photo_url,

                        "photo_public_id":
                            photo_public_id

                    })


                data["teams"] = teams


            # ======================================
            # UPDATE BASIC DATA
            # ======================================

            data["year"] = str(year)

            data["id"] = slug

            data["slug"] = slug


            # ======================================
            # UPDATE FIRESTORE
            # ======================================

            data["updated_at"] = (
                firestore.SERVER_TIMESTAMP
            )


            winner_ref.set(
                data
            )


            # ======================================
            # JSON BACKUP
            # ======================================

            winner_file = os.path.join(
                BASE_DIR,
                "data",
                "winners",
                str(year),
                f"{slug}.json"
            )


            os.makedirs(
                os.path.dirname(
                    winner_file
                ),
                exist_ok=True
            )


            backup_data = dict(data)


            # Firestore timestamp JSON me
            # serialize nahi hota.

            backup_data.pop(
                "updated_at",
                None
            )

            backup_data.pop(
                "created_at",
                None
            )


            with open(
                winner_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    backup_data,
                    f,
                    indent=4,
                    ensure_ascii=False
                )


            # ======================================
            # SUCCESS
            # ======================================

            flash(
                "Winner updated successfully and saved permanently.",
                "success"
            )


            return redirect(
                url_for("admin_winners")
            )


        except Exception as e:

            import traceback

            print(
                "===================================="
            )

            print(
                "EDIT WINNER ERROR:"
            )

            print(
                traceback.format_exc()
            )

            print(
                "===================================="
            )


            flash(
                f"Winner update failed: {str(e)}",
                "danger"
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
        game=data,
        year=year,
        slug=slug
    )

@app.route("/admin/winners/add", methods=["GET", "POST"])
def admin_add_winner():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        try:

            # ==========================================
            # BASIC DETAILS
            # ==========================================

            year = request.form.get(
                "year",
                ""
            ).strip()

            slug = (
                request.form.get(
                    "slug",
                    ""
                )
                .strip()
                .lower()
                .replace(" ", "-")
            )

            game = request.form.get(
                "game",
                ""
            ).strip()

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
            # VALIDATION
            # ==========================================

            if not year or not slug or not game:

                flash(
                    "Year, Game Name and Slug are required.",
                    "danger"
                )

                return redirect(
                    url_for("admin_add_winner")
                )


            # ==========================================
            # FIRESTORE DOCUMENT ID
            # ==========================================

            document_id = f"{year}-{slug}"

            winner_ref = (
                db
                .collection("winners")
                .document(document_id)
            )


            # ==========================================
            # DUPLICATE CHECK
            # ==========================================

            if winner_ref.get().exists:

                flash(
                    f"Winner game already exists: "
                    f"{game} ({year})",
                    "warning"
                )

                return redirect(
                    url_for("admin_add_winner")
                )


            # ==========================================
            # RANKING GAME
            # ==========================================

            if winner_type == "ranking":

                winners = []

                try:

                    winner_count = int(
                        request.form.get(
                            "winner_count",
                            0
                        )
                    )

                except ValueError:

                    winner_count = 0


                for i in range(
                    1,
                    winner_count + 1
                ):

                    name = request.form.get(
                        f"winner_name_{i}",
                        ""
                    ).strip()

                    age = request.form.get(
                        f"winner_age_{i}",
                        ""
                    ).strip()

                    position = request.form.get(
                        f"winner_position_{i}",
                        str(i)
                    ).strip()

                    photo = request.files.get(
                        f"winner_photo_{i}"
                    )

                    photo_url = ""


                    # ==================================
                    # PHOTO UPLOAD
                    # ==================================

                    if photo and photo.filename:

                        if not allowed_file(
                            photo.filename
                        ):

                            flash(
                                f"Invalid photo format "
                                f"for Winner {i}.",
                                "danger"
                            )

                            return redirect(
                                url_for(
                                    "admin_add_winner"
                                )
                            )


                        result = (
                            cloudinary
                            .uploader
                            .upload(
                                photo,
                                folder=(
                                    "Gajanan-Utsav/"
                                    "Winners/"
                                    f"{year}/"
                                    f"{slug}"
                                )
                            )
                        )

                        photo_url = result.get(
                            "secure_url",
                            ""
                        )


                    # ==================================
                    # SAVE WINNER
                    # ==================================

                    if name:

                        try:
                            position_value = int(
                                position
                            )

                        except ValueError:
                            position_value = i


                        winners.append({

                            "position":
                                position_value,

                            "name":
                                name,

                            "age":
                                age,

                            "photo":
                                photo_url

                        })


                data = {

                    "id":
                        slug,

                    "slug":
                        slug,

                    "game":
                        game,

                    "icon":
                        icon,

                    "date":
                        date,

                    "status":
                        "Completed",

                    "type":
                        "ranking",

                    "gallery":
                        slug,

                    "winners":
                        winners,

                    "year":
                        str(year)

                }


            # ==========================================
            # AGE GROUP GAME
            # ==========================================

            elif winner_type == "age_group":

                groups = []

                try:

                    group_count = int(
                        request.form.get(
                            "group_count",
                            0
                        )
                    )

                except ValueError:

                    group_count = 0


                for i in range(
                    1,
                    group_count + 1
                ):

                    age_group = request.form.get(
                        f"age_group_{i}",
                        ""
                    ).strip()

                    winner_name = request.form.get(
                        f"group_winner_name_{i}",
                        ""
                    ).strip()

                    winner_age = request.form.get(
                        f"group_winner_age_{i}",
                        ""
                    ).strip()

                    photo = request.files.get(
                        f"group_winner_photo_{i}"
                    )

                    photo_url = ""


                    # ==================================
                    # PHOTO UPLOAD
                    # ==================================

                    if photo and photo.filename:

                        if not allowed_file(
                            photo.filename
                        ):

                            flash(
                                f"Invalid photo format "
                                f"for Age Group {i}.",
                                "danger"
                            )

                            return redirect(
                                url_for(
                                    "admin_add_winner"
                                )
                            )


                        result = (
                            cloudinary
                            .uploader
                            .upload(
                                photo,
                                folder=(
                                    "Gajanan-Utsav/"
                                    "Winners/"
                                    f"{year}/"
                                    f"{slug}"
                                )
                            )
                        )

                        photo_url = result.get(
                            "secure_url",
                            ""
                        )


                    # ==================================
                    # SAVE GROUP
                    # ==================================

                    if age_group or winner_name:

                        groups.append({

                            "age_group":
                                age_group,

                            "winner": {

                                "name":
                                    winner_name,

                                "age":
                                    winner_age,

                                "photo":
                                    photo_url

                            }

                        })


                data = {

                    "id":
                        slug,

                    "slug":
                        slug,

                    "game":
                        game,

                    "icon":
                        icon,

                    "date":
                        date,

                    "status":
                        "Completed",

                    "type":
                        "age_group",

                    "gallery":
                        slug,

                    "groups":
                        groups,

                    "year":
                        str(year)

                }


            # ==========================================
            # TEAM GAME
            # ==========================================

            elif winner_type == "team":

                teams = []

                try:

                    team_count = int(
                        request.form.get(
                            "team_count",
                            0
                        )
                    )

                except ValueError:

                    team_count = 0


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

                            "team":
                                team_name

                        })


                data = {

                    "id":
                        slug,

                    "slug":
                        slug,

                    "game":
                        game,

                    "icon":
                        icon,

                    "date":
                        date,

                    "status":
                        "Completed",

                    "type":
                        "team",

                    "gallery":
                        slug,

                    "teams":
                        teams,

                    "year":
                        str(year)

                }


            else:

                flash(
                    "Invalid winner type.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "admin_add_winner"
                    )
                )


            # ==========================================
            # SAVE TO FIRESTORE
            # ==========================================

            data["created_at"] = (
                firestore.SERVER_TIMESTAMP
            )

            data["source"] = "admin"

            winner_ref.set(
                data
            )


            # ==========================================
            # SUCCESS
            # ==========================================

            print(
                "======================================"
            )

            print(
                "WINNER ADDED SUCCESSFULLY"
            )

            print(
                f"Year : {year}"
            )

            print(
                f"Game : {game}"
            )

            print(
                f"Slug : {slug}"
            )

            print(
                f"Type : {winner_type}"
            )

            print(
                f"Firestore ID : {document_id}"
            )

            print(
                "======================================"
            )


            flash(
                "Winner Added Successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_winners"
                )
            )


        except Exception as e:

            import traceback

            error_text = traceback.format_exc()

            print(
                "======================================"
            )

            print(
                "❌ ADD WINNER ERROR"
            )

            print(
                error_text
            )

            print(
                "======================================"
            )


            flash(
                f"Error adding winner: {str(e)}",
                "danger"
            )

            return redirect(
                url_for(
                    "admin_add_winner"
                )
            )


    return render_template(
        "admin/add_winner.html"
    )
# ==========================================
# ADMIN - DELETE WINNER
# ==========================================

@app.route(
    "/admin/winners/delete/<year>/<slug>"
)
def admin_delete_winner(year, slug):

    # ==========================================
    # ADMIN LOGIN CHECK
    # ==========================================

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    # ==========================================
    # FIRESTORE DOCUMENT
    # ==========================================

    document_id = (
        f"{year}-{slug}"
    )

    winner_ref = (
        db
        .collection("winners")
        .document(document_id)
    )


    # ==========================================
    # GET FIRESTORE DATA
    # ==========================================

    firestore_doc = winner_ref.get()


    # ==========================================
    # GET DATA
    # ==========================================

    game = None


    if firestore_doc.exists:

        game = firestore_doc.to_dict()


    # ==========================================
    # IF FIRESTORE DATA NOT FOUND
    # ==========================================

    if not game:

        # --------------------------------------
        # FALLBACK TO JSON
        # --------------------------------------

        file_path = os.path.join(
            BASE_DIR,
            "data",
            "winners",
            str(year),
            f"{slug}.json"
        )


        if os.path.exists(file_path):

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
    # NOTHING FOUND
    # ==========================================

    if not game:

        flash(
            "Winner record not found.",
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


        # ======================================
        # RANKING
        # ======================================

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


        # ======================================
        # AGE GROUP
        # ======================================

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


        # ======================================
        # TEAM
        # ======================================

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
    # DELETE FROM FIRESTORE
    # ==========================================

    try:

        if firestore_doc.exists:

            winner_ref.delete()

            print(
                "Deleted Firestore winner:",
                document_id
            )


    except Exception as e:

        print(
            "Firestore winner delete error:",
            e
        )

        flash(
            "Could not delete winner from Firestore.",
            "danger"
        )

        return redirect(
            url_for("admin_winners")
        )


    # ==========================================
    # DELETE JSON BACKUP
    # ==========================================

    file_path = os.path.join(
        BASE_DIR,
        "data",
        "winners",
        str(year),
        f"{slug}.json"
    )


    if os.path.exists(file_path):

        try:

            os.remove(
                file_path
            )

            print(
                "Deleted JSON backup:",
                file_path
            )

        except Exception as e:

            print(
                "Winner JSON delete error:",
                e
            )


            # IMPORTANT:
            # Firestore already deleted,
            # so don't report complete failure.

            print(
                "Firestore deletion was successful."
            )


    # ==========================================
    # SUCCESS
    # ==========================================

    flash(
        "Winner and associated record deleted successfully.",
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

    # ==========================================
    # LATEST WINNER — HOME PAGE ONLY
    # ==========================================

    latest_winners = []

    for year, year_games in winners.items():

        if not year_games:
            continue

        # load_winners() already sorts
        # latest date first.
        latest_game = year_games[0]

        latest_winners.append({

            "year": year,

            "game": latest_game.get(
                "game",
                ""
            ),

            "slug": latest_game.get(
                "slug",
                ""
            ),

            "gallery": latest_game.get(
                "gallery_event",
                ""
            ),

            "type": latest_game.get(
                "type",
                "ranking"
            ),

            "data": (
                latest_game.get(
                    "winners",
                    []
                )
                if latest_game.get("type") == "ranking"
                else latest_game.get(
                    "groups",
                    []
                )
            )

        })

        # ONLY ONE LATEST GAME
        break


 

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

    print("\n" + "=" * 70)
    print("INTERNAL SERVER ERROR")
    print("=" * 70)
    print(error)
    print("=" * 70 + "\n")

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Server Error</title>
    </head>

    <body style="
        font-family: Arial, sans-serif;
        text-align: center;
        padding: 80px 20px;
    ">

        <h1>500 - Internal Server Error</h1>

        <p>
            Something went wrong on the server.
        </p>

        <p>
            Please try again later.
        </p>

    </body>
    </html>
    """, 500
    
if __name__ == "__main__":
    app.run()
