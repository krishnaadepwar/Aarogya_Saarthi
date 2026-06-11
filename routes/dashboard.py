from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import db, PatientProfile, AshaProfile, Complaint, MedicineReminder, SupplyRequest, Message
from datetime import datetime
import re

dashboard_bp = Blueprint('dashboard', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    role = current_user.role.lower()
    if role == "patient": return redirect(url_for("dashboard.patient_dashboard"))
    if role == "asha": return redirect(url_for("dashboard.asha_dashboard"))
    if role == "admin": return redirect(url_for("admin.dashboard"))
    abort(403)

@dashboard_bp.route("/dashboard/patient")
@login_required
def patient_dashboard():
    if current_user.role.lower() != "patient": abort(403)
    patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
    ashas = AshaProfile.query.filter_by(area=patient.area).all() if patient and patient.area else []
    reminders_count = MedicineReminder.query.filter_by(patient_id=current_user.id).count()
    supply_count = SupplyRequest.query.filter_by(patient_id=current_user.id).count()
    return render_template("dashboard_patient.html", patient=patient, ashas=ashas, reminders_count=reminders_count, supply_count=supply_count)

@dashboard_bp.route("/dashboard/asha")
@login_required
def asha_dashboard():
    if current_user.role.lower() != "asha": abort(403)
    asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
    patients = PatientProfile.query.filter_by(area=asha.area).all() if asha and asha.area else []
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    if asha and asha.area:
        asha_ids = [a.user_id for a in AshaProfile.query.filter_by(area=asha.area).all()]
        supply_count = SupplyRequest.query.filter(SupplyRequest.asha_id.in_(asha_ids)).count()
    else:
        supply_count = SupplyRequest.query.filter_by(asha_id=current_user.id).count()
    return render_template("dashboard_asha.html", asha=asha, patients=patients, unread_count=unread_count, supply_count=supply_count)

@dashboard_bp.route("/complete-profile")
@login_required
def complete_profile():
    role = current_user.role.lower()
    if role == "patient": return redirect(url_for("dashboard.patient_profile"))
    elif role == "asha": return redirect(url_for("dashboard.asha_profile"))
    abort(403)

@dashboard_bp.route("/profile/patient", methods=["GET", "POST"])
@login_required
def patient_profile():
    if current_user.role.lower() != "patient": abort(403)
    profile = PatientProfile.query.filter_by(user_id=current_user.id).first()
    if request.method == "POST":
        name = sanitize_input(request.form.get("name", ""), max_len=100)
        age_raw = sanitize_input(request.form.get("age", ""), max_len=3)
        gender = sanitize_input(request.form.get("gender", ""), max_len=10)
        phone = sanitize_input(request.form.get("phone", ""), max_len=15)
        area = sanitize_input(request.form.get("area", ""), max_len=100)
        errors = []
        if not re.fullmatch(r"\d{10}", phone): errors.append("Phone number must be exactly 10 digits.")
        try:
            age = int(age_raw)
            if age < 0 or age > 120: errors.append("Age must be between 0 and 120.")
        except: errors.append("Age must be a number.")
        if errors:
            for e in errors: flash(e)
            if not profile: profile = PatientProfile(user_id=current_user.id)
            profile.name, profile.age, profile.gender, profile.phone, profile.area = name, age_raw, gender, phone, area
            return render_template("patient_profile.html", profile=profile)
        if not profile:
            profile = PatientProfile(user_id=current_user.id)
            db.session.add(profile)
        profile.name, profile.age, profile.gender, profile.phone, profile.area = name, age, gender, phone, area
        current_user.profile_completed = True
        db.session.commit()
        return redirect(url_for("dashboard.dashboard"))
    return render_template("patient_profile.html", profile=profile)

@dashboard_bp.route("/profile/asha", methods=["GET", "POST"])
@login_required
def asha_profile():
    if current_user.role.lower() != "asha": abort(403)
    profile = AshaProfile.query.filter_by(user_id=current_user.id).first()
    if request.method == "POST":
        name = sanitize_input(request.form.get("name", ""), max_len=100)
        phone = sanitize_input(request.form.get("phone", ""), max_len=15)
        area = sanitize_input(request.form.get("area", ""), max_len=100)
        exp_raw = sanitize_input(request.form.get("experience_years", ""), max_len=2)
        errors = []
        if not re.fullmatch(r"\d{10}", phone): errors.append("Phone number must be exactly 10 digits.")
        try:
            exp = int(exp_raw)
            if exp < 0 or exp > 60: errors.append("Experience must be between 0 and 60 years.")
        except: errors.append("Experience must be a number.")
        if errors:
            for e in errors: flash(e)
            if not profile: profile = AshaProfile(user_id=current_user.id)
            profile.name, profile.phone, profile.area, profile.experience_years = name, phone, area, exp_raw
            return render_template("asha_profile.html", profile=profile)
        if not profile:
            profile = AshaProfile(user_id=current_user.id)
            db.session.add(profile)
        profile.name, profile.phone, profile.area, profile.experience_years = name, phone, area, exp
        current_user.profile_completed = True
        db.session.commit()
        return redirect(url_for("dashboard.dashboard"))
    return render_template("asha_profile.html", profile=profile)

@dashboard_bp.route("/complaints", methods=["GET", "POST"])
@login_required
def complaints():
    if current_user.role.lower() not in ["patient", "asha"]: abort(403)
    if request.method == "POST":
        complaint = Complaint(user_id=current_user.id, role=current_user.role, title=sanitize_input(request.form.get("title", ""), max_len=200), description=sanitize_input(request.form.get("description", ""), max_len=2000))
        db.session.add(complaint)
        db.session.commit()
        return redirect(url_for("dashboard.complaints"))
    my_complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return render_template("complaints.html", complaints=my_complaints)
