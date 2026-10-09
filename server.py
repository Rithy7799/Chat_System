from pathlib import Path
from hashlib import sha256
from io import BytesIO
import os
import secrets
from threading import Lock
from time import time
from uuid import uuid4

from flask import Flask, abort, g, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from database import ChatDatabase


APP_DIR = Path(__file__).resolve().parent
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()


def load_host_secret_key(app_dir, key_file=None):
    key_path = Path(key_file).expanduser() if key_file and str(key_file).strip() else Path(app_dir) / "data" / ".flask_secret_key"
    if not key_path.is_absolute():
        key_path = Path(app_dir) / key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with key_path.open("x", encoding="ascii") as key_file_handle:
            key = secrets.token_hex(32)
            key_file_handle.write(key)
            return key
    except FileExistsError:
        key = key_path.read_text(encoding="ascii").strip()
        if key:
            return key
        raise RuntimeError("The Flask signing key file is empty.")

app = Flask(__name__)
app.config["SECRET_KEY"] = load_host_secret_key(
    APP_DIR, os.environ.get("SECRET_KEY_FILE")
)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
app.config["COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}
APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", APP_DIR / "chat_history.db")).expanduser()
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", APP_DIR / "uploads")).expanduser()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
database = ChatDatabase(DATABASE_PATH)
clients = {}
clients_lock = Lock()
MAX_MESSAGE_LENGTH = 2000
CLIENT_TIMEOUT_SECONDS = 45
ALLOWED_FILE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/profile")
def profile():
    return render_template("profile.html")


@app.get("/healthz")
def health_check():
    try:
        database.list_groups()
    except Exception:
        app.logger.exception("Health check failed")
        return jsonify(status="unavailable"), 503
    return jsonify(status="ok")


@app.before_request
def load_current_user():
    if request.endpoint in {"static", "health_check"}:
        return
    token = request.cookies.get("chat_user")
    token_hash = sha256(token.encode("utf-8")).hexdigest() if token else ""
    user = database.get_user_by_session(token_hash) if token_hash else None
    if user is None:
        token = secrets.token_urlsafe(32)
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        user = database.create_user(token_hash)
        g.new_user_token = token
    g.current_user = user


@app.get("/api/me")
def get_current_user():
    return g.current_user


@app.put("/api/me")
def update_current_user():
    data = request.get_json(silent=True) or {}
    username = clean_username(data["username"]) if "username" in data else None
    photo = data.get("photo")
    if photo is not None:
        if not isinstance(photo, str) or len(photo) > 2 * 1024 * 1024:
            abort(400, "Profile photos must be valid images up to 2 MB.")
    group_id = None
    if "group_id" in data:
        try:
            group_id = int(data["group_id"])
        except (TypeError, ValueError):
            abort(400, "Choose a valid group.")
        if database.get_group(group_id) is None:
            abort(404, "Group not found.")
    return database.update_user(
        g.current_user["user_id"],
        username=username,
        photo=photo,
        selected_group_id=group_id,
    )


@app.delete("/api/me")
def delete_current_user():
    database.delete_user(g.current_user["user_id"])
    g.clear_user_cookie = True
    return "", 204


@app.after_request
def add_security_headers(response):
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    token = getattr(g, "new_user_token", None)
    if getattr(g, "clear_user_cookie", False):
        response.delete_cookie("chat_user", path="/", samesite="Lax")
    elif token:
        response.set_cookie(
            "chat_user",
            token,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=app.config["COOKIE_SECURE"],
            samesite="Lax",
            path="/",
        )
    return response


def clean_username(value):
    username = str(value or "").strip()[:32]
    if not username:
        abort(400, "A display name is required.")
    return username


@app.post("/upload")
def upload_file():
    username = g.current_user["username"]
    uploaded_file = request.files.get("file")
    group_id = g.current_user["selected_group_id"]
    if uploaded_file is None or not uploaded_file.filename:
        abort(400, "Choose a file to upload.")
    if database.get_group(group_id) is None:
        abort(404, "Group not found.")

    safe_name = secure_filename(uploaded_file.filename)
    suffix = Path(safe_name).suffix.lower()
    mime_type = ALLOWED_FILE_TYPES.get(suffix)
    if not safe_name or mime_type is None:
        abort(415, "Supported files: images, PDF, TXT, and CSV.")

    contents = uploaded_file.stream.read(app.config["MAX_CONTENT_LENGTH"] + 1)
    if not contents:
        abort(400, "The selected file is empty.")
    if len(contents) > app.config["MAX_CONTENT_LENGTH"]:
        abort(413, "Files must be 10 MB or smaller.")

    file_id = uuid4().hex
    message = database.save_file_message(
        g.current_user["user_id"], username, file_id, safe_name, len(contents),
        mime_type, contents, group_id
    )
    return {"ok": True, "message": message}, 201


def file_response(file_id, download):
    metadata = database.find_file(file_id)
    if metadata is None:
        abort(404)
    suffix = Path(metadata["file_name"]).suffix.lower()
    if suffix not in ALLOWED_FILE_TYPES:
        abort(404)
    file_path = UPLOAD_DIR / (file_id + suffix)
    file_data = metadata["file_data"]
    if file_data is None and not file_path.is_file():
        abort(404)
    response = send_file(
        BytesIO(file_data) if file_data is not None else file_path,
        mimetype=metadata["mime_type"],
        as_attachment=download,
        download_name=metadata["file_name"],
        conditional=True,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    if not download:
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@app.get("/files/<file_id>/view")
def view_file(file_id):
    return file_response(file_id, download=False)


@app.get("/files/<file_id>/download")
def download_file(file_id):
    return file_response(file_id, download=True)


@app.get("/api/chat")
def chat_state():
    group_id = g.current_user["selected_group_id"]
    group = database.get_group(group_id)
    if group is None:
        group_id = 1
        group = database.get_group(group_id)
        database.update_user(g.current_user["user_id"], selected_group_id=group_id)
    now = time()
    with clients_lock:
        clients[g.current_user["user_id"]] = {
            "username": g.current_user["username"],
            "group_id": group_id,
            "last_seen": now,
        }
        for inactive_id, client in list(clients.items()):
            if now - client["last_seen"] > CLIENT_TIMEOUT_SECONDS:
                del clients[inactive_id]
        online_count = sum(
            client["group_id"] == group_id for client in clients.values()
        )
    return {
        "group": group,
        "groups": database.list_groups(),
        "messages": database.recent_messages(group_id),
        "online_count": online_count,
        "user": g.current_user,
    }


@app.post("/api/groups")
def create_group():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 40:
        abort(400, "Group names must be 1 to 40 characters.")
    group = database.create_group(name)
    if group is None:
        abort(409, "A group with that name already exists.")
    return {"group": group}, 201


@app.post("/api/messages")
def send_message():
    data = request.get_json(silent=True) or {}
    username = g.current_user["username"]
    text = str(data.get("text", "")).strip()
    if not text:
        abort(400, "A message cannot be empty.")
    if len(text) > MAX_MESSAGE_LENGTH:
        abort(400, "Messages must be 2000 characters or fewer.")
    group_id = g.current_user["selected_group_id"]
    if database.get_group(group_id) is None:
        abort(404, "Group not found.")
    return {
        "message": database.save_message(
            g.current_user["user_id"], username, text, group_id
        )
    }, 201


@app.delete("/api/messages/<int:message_id>")
def delete_chat_message(message_id):
    group_id = g.current_user["selected_group_id"]

    deleted = database.delete_message(message_id, g.current_user["user_id"], group_id)
    if deleted is None:
        abort(404, "Message not found or it does not belong to this display name.")
    if deleted["file_id"]:
        suffix = Path(deleted["file_name"]).suffix.lower()
        if suffix in ALLOWED_FILE_TYPES:
            file_path = UPLOAD_DIR / (deleted["file_id"] + suffix)
            try:
                if file_path.is_file():
                    file_path.unlink()
            except OSError:
                app.logger.exception("Could not remove uploaded file %s", file_path)
    return {"ok": True}


if __name__ == "__main__":
    if APP_ENV == "production":
        raise RuntimeError("Run production with Waitress; see README.md.")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))