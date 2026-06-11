from flask import Flask, render_template, redirect, url_for, request, abort, session, flash
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime, date, timedelta
import re
import os
from DiseaseDetection.app import disease_bp
from info.app import info_bp
from medicine.app import medicine_bp
from ashamanage.app import asha_bp
from RAG.app import rag_bp


from flask_socketio import emit, join_room
from extensions import socketio, login_manager, csrf, migrate
from models import db, User, Message

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-placeholder")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # Limit request size to 2MB

csrf.init_app(app)

# ---------- INPUT SANITIZATION UTILS ----------
def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    # Basic sanitization: strip and limit length
    cleaned = str(text).strip()
    # Remove potential script tags or basic HTML if any
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@app.context_processor
def inject_now():
    return {'datetime': datetime, 'date': date, 'timedelta': timedelta}

db.init_app(app)
migrate.init_app(app, db)
socketio.init_app(app)

login_manager.login_view = "auth.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.admin import admin_bp
from routes.analytics import analytics_bp
from routes.supplies import supplies_bp
from routes.reminders import reminders_bp
from routes.dashboard import dashboard_bp
from routes.emergency import emergency_bp

app.register_blueprint(disease_bp)
app.register_blueprint(info_bp)
app.register_blueprint(medicine_bp)
app.register_blueprint(asha_bp)
app.register_blueprint(rag_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(supplies_bp)
app.register_blueprint(reminders_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(emergency_bp)




@app.after_request
def add_header(response):
    if request.path.startswith("/static"):
        return response
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def home():
    if current_user.is_authenticated:
        if current_user.role.lower() == 'admin':
            return redirect(url_for("admin.dashboard"))
        elif current_user.role.lower() == 'asha':
            return redirect(url_for("asha.asha_home"))
        return redirect(url_for("dashboard.dashboard"))
    return render_template("home.html")




@socketio.on("join")
def handle_join(data):
    if not current_user.is_authenticated:
        return

    room = data.get("room")
    if room:
        # Chat room validation: format is "minID_maxID"
        if "_" in room:
            try:
                id1, id2 = map(int, room.split("_"))
                # 🚨 SECURITY FIX: Only allow users who belong to the chat to join its room
                if current_user.id == id1 or current_user.id == id2:
                    join_room(room)
                else:
                    # Log unauthorized attempt if needed
                    pass
            except ValueError:
                # Not a chat room (maybe a general area room)
                # For area-based broadcast rooms, you could add similar validation
                join_room(room)
        else:
            # Join non-chat rooms (like area notification rooms)
            join_room(room)

    # Join personal notification room
    join_room(f"user_{current_user.id}")


@socketio.on("send_message")
def handle_send_message(data):
    if not current_user.is_authenticated:
        return

    msg_text = sanitize_input(data.get("message", ""), max_len=1000)
    if not msg_text:
        return

    # 🚨 SECURITY FIX: Never trust client-sent sender_id or role
    sender_id = current_user.id
    sender_role = current_user.role
    receiver_id = data.get("receiver_id")
    room = data.get("room")

    if not receiver_id or not room:
        return

    msg = Message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        sender_role=sender_role,
        message=msg_text
    )
    db.session.add(msg)
    db.session.commit()

    emit(
        "receive_message",
        {
            "sender_id": sender_id,
            "message": msg_text
        },
        room=room
    )

@app.context_processor
def unread_messages():
    if current_user.is_authenticated:
        # Show unread count for all roles that use messaging (patient, asha, admin)
        count = Message.query.filter_by(
            receiver_id=current_user.id,
            is_read=False
        ).count()
        return dict(unread_count=count)
    return dict(unread_count=0)


if __name__ == "__main__":
    print("Server running at http://127.0.0.1:5000/")
    socketio.run(app, host="127.0.0.1", debug=False, use_reloader=False)
    # socketio.run(app, debug=True)

