from flask import Blueprint, render_template, redirect, url_for, abort, request, flash
from flask_login import login_required, current_user
from models import db, User, PatientProfile, AshaProfile, Complaint
from datetime import datetime
import re

admin_bp = Blueprint('admin', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@admin_bp.route("/dashboard/admin")
@login_required
def dashboard():
    if current_user.role.lower() != "admin":
        abort(403)
    total_patients = PatientProfile.query.count()
    total_ashas = AshaProfile.query.count()
    total_complaints = Complaint.query.count()
    return render_template("dashboard_admin.html", total_patients=total_patients, total_ashas=total_ashas, total_complaints=total_complaints)

@admin_bp.route("/admin/patients")
@login_required
def patients():
    if current_user.role.lower() != "admin": abort(403)
    patients = PatientProfile.query.all()
    return render_template("admin_patients.html", patients=patients)

@admin_bp.route("/admin/patient/<int:id>")
@login_required
def view_patient(id):
    if current_user.role.lower() != "admin": abort(403)
    profile = PatientProfile.query.get_or_404(id)
    return render_template("admin_view_patient.html", profile=profile)

@admin_bp.route("/admin/ashas")
@login_required
def ashas():
    if current_user.role.lower() != "admin": abort(403)
    ashas = AshaProfile.query.all()
    return render_template("admin_ashas.html", ashas=ashas)

@admin_bp.route("/admin/asha/<int:id>")
@login_required
def view_asha(id):
    if current_user.role.lower() != "admin": abort(403)
    profile = AshaProfile.query.get_or_404(id)
    return render_template("admin_view_asha.html", profile=profile)

@admin_bp.route("/admin/complaints")
@login_required
def complaints():
    if current_user.role.lower() != "admin": abort(403)
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    if complaints:
        p_ids = [c.user_id for c in complaints if c.role == "patient"]
        a_ids = [c.user_id for c in complaints if c.role == "asha"]
        p_profiles = PatientProfile.query.filter(PatientProfile.user_id.in_(p_ids)).all() if p_ids else []
        a_profiles = AshaProfile.query.filter(AshaProfile.user_id.in_(a_ids)).all() if a_ids else []
        p_map = {p.user_id: p.name for p in p_profiles}
        a_map = {a.user_id: a.name for a in a_profiles}
        for c in complaints:
            c.user_name = p_map.get(c.user_id) if c.role == "patient" else a_map.get(c.user_id)
    return render_template("admin_complaints.html", complaints=complaints)

@admin_bp.route("/admin/view/complaint/<int:id>", methods=["GET", "POST"])
@login_required
def view_complaint(id):
    if current_user.role.lower() != "admin": abort(403)
    complaint = Complaint.query.get_or_404(id)
    if complaint.role == "patient":
        prof = PatientProfile.query.filter_by(user_id=complaint.user_id).first()
        complaint.user_name = prof.name if prof else None
    elif complaint.role == "asha":
        prof = AshaProfile.query.filter_by(user_id=complaint.user_id).first()
        complaint.user_name = prof.name if prof else None
    if request.method == "POST":
        complaint.admin_reply = sanitize_input(request.form.get("admin_reply", ""), max_len=2000)
        complaint.replied_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for("admin.complaints"))
    return render_template("admin_view_complaint.html", complaint=complaint)
