from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, PatientProfile, AshaProfile
import re

auth_bp = Blueprint('auth', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    role = request.args.get("role")
    if role not in ["patient", "asha", "admin"]:
        role = None

    if request.method == "POST":
        if not role:
            flash("Role is required for registration.")
            return render_template("register.html", role=role)
            
        username = sanitize_input(request.form.get("username", ""), max_len=80)
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Username and password are required.")
            return render_template("register.html", role=role)

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("auth.login", role=role))

    return render_template("register.html", role=role)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role")
    if role not in ["patient", "asha", "admin"]:
        role = None

    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        # Clear lockout for current session to allow immediate retry
        session["login_attempts"] = 0
        attempts = 0
        
        username = sanitize_input(request.form.get("username", ""), max_len=80)
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            if role and user.role != role:
                flash(f"User is not registered as {role}.", "danger")
                return redirect(url_for("auth.login", role=role))

            login_user(user)
            session["login_attempts"] = 0

            if user.role == "admin":
                return redirect(url_for("admin.dashboard"))

            if not user.profile_completed:
                return redirect(url_for("dashboard.complete_profile"))

            return redirect(url_for("dashboard.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html", role=role)

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))
