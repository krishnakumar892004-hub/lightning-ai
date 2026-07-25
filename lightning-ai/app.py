"""
Lightning AI - Full Stack AI Chat Web Application
Backend: Flask (Python)
Database: MySQL (SQLAlchemy)
Auth: Google OAuth (Gmail Login)
AI: Google Gemini API (Chat + Image Generation + Vision/Image understanding)
"""

import os
import base64
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from google import genai
from google.genai import types

load_dotenv()

# ---------------------------------------------------------------------------
# App config
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

db_user = os.environ.get("DB_USER", "root")
db_pass = os.environ.get("DB_PASSWORD", "")
db_host = os.environ.get("DB_HOST", "localhost")
db_port = os.environ.get("DB_PORT", "3306")
db_name = os.environ.get("DB_NAME", "lightning_ai")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

oauth = OAuth(app)
google_oauth = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

GEMINI_TEXT_MODEL = "gemini-2.0-flash"
GEMINI_VISION_MODEL = "gemini-2.0-flash"
GEMINI_IMAGE_GEN_MODEL = "gemini-2.0-flash-preview-image-generation"

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255))
    profile_pic = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    chats = db.relationship("ChatHistory", backref="user", lazy=True)


class ChatHistory(db.Model):
    __tablename__ = "chat_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message_type = db.Column(db.String(20), default="chat")  # chat | image_gen | image_qa
    question = db.Column(db.Text)
    answer = db.Column(db.Text)
    image_path = db.Column(db.String(500))  # uploaded or generated image path
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/login/google")
def login_google():
    redirect_uri = url_for("auth_callback", _external=True)
    return google_oauth.authorize_redirect(redirect_uri)


@app.route("/auth/callback")
def auth_callback():
    token = google_oauth.authorize_access_token()
    user_info = token.get("userinfo")
    if not user_info:
        user_info = google_oauth.get("https://openidconnect.googleapis.com/v1/userinfo").json()

    google_id = user_info["sub"]
    email = user_info["email"]
    name = user_info.get("name", email.split("@")[0])
    picture = user_info.get("picture", "")

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User(google_id=google_id, email=email, name=name, profile_pic=picture)
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for("index"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Main pages
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)


# ---------------------------------------------------------------------------
# API: Chat (text question -> AI answer) — Gemini text generation
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json()
    message = (data or {}).get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is empty"}), 400

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_TEXT_MODEL,
            contents=message,
            config=types.GenerateContentConfig(
                system_instruction="You are Lightning AI, a helpful, friendly assistant.",
            ),
        )
        answer = response.text
    except Exception as exc:
        return jsonify({"error": f"AI request failed: {exc}"}), 500

    entry = ChatHistory(
        user_id=current_user.id,
        message_type="chat",
        question=message,
        answer=answer,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"answer": answer, "id": entry.id})


# ---------------------------------------------------------------------------
# API: Image generation (prompt -> image) — Gemini image generation
# ---------------------------------------------------------------------------
@app.route("/api/generate-image", methods=["POST"])
@login_required
def api_generate_image():
    data = request.get_json()
    prompt = (data or {}).get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is empty"}), 400

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_IMAGE_GEN_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        image_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
                break

        if not image_bytes:
            return jsonify({"error": "Gemini did not return an image. Try a different prompt."}), 500

        filename = f"gen_{current_user.id}_{int(datetime.utcnow().timestamp())}.png"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        image_url = url_for("static", filename=f"uploads/{filename}")
    except Exception as exc:
        return jsonify({"error": f"Image generation failed: {exc}"}), 500

    entry = ChatHistory(
        user_id=current_user.id,
        message_type="image_gen",
        question=prompt,
        answer="Image generated successfully.",
        image_path=image_url,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"image_url": image_url, "id": entry.id})


# ---------------------------------------------------------------------------
# API: Upload image + ask question about it — Gemini vision
# ---------------------------------------------------------------------------
@app.route("/api/upload-image", methods=["POST"])
@login_required
def api_upload_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    question = request.form.get("question", "Describe this image in detail.")

    filename = secure_filename(file.filename)
    unique_name = f"upload_{current_user.id}_{int(datetime.utcnow().timestamp())}_{filename}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(filepath)

    with open(filepath, "rb") as f:
        image_bytes = f.read()

    mime_type = file.mimetype or "image/jpeg"
    image_url = url_for("static", filename=f"uploads/{unique_name}")

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                question,
            ],
        )
        answer = response.text
    except Exception as exc:
        return jsonify({"error": f"Image analysis failed: {exc}"}), 500

    entry = ChatHistory(
        user_id=current_user.id,
        message_type="image_qa",
        question=question,
        answer=answer,
        image_path=image_url,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"answer": answer, "image_url": image_url, "id": entry.id})


# ---------------------------------------------------------------------------
# API: Chat history for logged in user
# ---------------------------------------------------------------------------
@app.route("/api/history", methods=["GET"])
@login_required
def api_history():
    chats = (
        ChatHistory.query.filter_by(user_id=current_user.id)
        .order_by(ChatHistory.created_at.asc())
        .all()
    )
    return jsonify(
        [
            {
                "id": c.id,
                "type": c.message_type,
                "question": c.question,
                "answer": c.answer,
                "image_path": c.image_path,
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for c in chats
        ]
    )


@app.route("/api/history/<int:chat_id>", methods=["DELETE"])
@login_required
def api_delete_history(chat_id):
    entry = ChatHistory.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not entry:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
