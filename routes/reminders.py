from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import db, User, PatientProfile, AshaProfile, MedicineReminder
from datetime import datetime
import re

reminders_bp = Blueprint('reminders', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@reminders_bp.route("/reminders", methods=["GET", "POST"])
@login_required
def patient_reminders():
    if current_user.role.lower() != "patient":
        from flask import abort
        abort(403)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            time_str = sanitize_input(request.form.get("time", ""), max_len=5)
            try: rt = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                flash("Invalid time format. Use HH:MM.")
                return redirect(url_for("reminders.patient_reminders"))
            reminder = MedicineReminder(
                patient_id=current_user.id, created_by="patient",
                medicine_name=sanitize_input(request.form.get("medicine", ""), max_len=100),
                dosage=sanitize_input(request.form.get("dosage", ""), max_len=50),
                reminder_time=rt,
                frequency=sanitize_input(request.form.get("frequency", ""), max_len=50),
                status="pending"
            )
            db.session.add(reminder)
            db.session.commit()
            flash("Reminder set successfully!", "success")
        elif action == "delete":
            r_id = request.form.get("reminder_id")
            rem = db.session.get(MedicineReminder, r_id)
            if rem and rem.patient_id == current_user.id:
                db.session.delete(rem)
                db.session.commit()
                flash("Reminder deleted.", "success")
        elif action == "taken":
            r_id = request.form.get("reminder_id")
            rem = db.session.get(MedicineReminder, r_id)
            if rem and rem.patient_id == current_user.id:
                rem.status = "taken"
                rem.last_taken_date = datetime.now().date()
                db.session.commit()
                flash("Medicine marked as taken.", "success")
        return redirect(url_for("reminders.patient_reminders"))

    reminders = MedicineReminder.query.filter_by(patient_id=current_user.id).order_by(MedicineReminder.reminder_time).all()
    now = datetime.now()
    today, current_time = now.date(), now.time()
    changed = False
    for r in reminders:
        if r.last_taken_date != today:
            if r.status != 'pending':
                r.status = 'pending'
                changed = True
        if r.status == 'pending' and r.last_taken_date != today and r.reminder_time < current_time:
            r.status = 'missed'
            changed = True
    if changed: db.session.commit()
    return render_template("patient_reminders.html", reminders=reminders)

@reminders_bp.route("/asha/reminder", methods=["GET", "POST"])
@login_required
def asha_set_reminder():
    if current_user.role.lower() != "asha":
        from flask import abort
        abort(403)
    asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
    patient_users = []
    if asha and asha.area:
        patients = PatientProfile.query.filter_by(area=asha.area).all()
        patient_user_ids = [p.user_id for p in patients]
        patient_users = User.query.filter(User.id.in_(patient_user_ids)).all() if patient_user_ids else []

    selected_patient_id = request.args.get("patient_id", type=int)
    patient_reminders_list = []
    if selected_patient_id and selected_patient_id in [u.id for u in patient_users]:
        patient_reminders_list = MedicineReminder.query.filter_by(patient_id=selected_patient_id).order_by(MedicineReminder.reminder_time).all()

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            p_id_raw = sanitize_input(request.form.get("patient_id", ""), max_len=10)
            if not p_id_raw:
                flash("Invalid patient.")
                return redirect(url_for("reminders.asha_set_reminder"))
            p_id = int(p_id_raw)
            if p_id not in [u.id for u in patient_users]:
                flash("Invalid patient selected.")
                return redirect(url_for("reminders.asha_set_reminder"))
            time_str = sanitize_input(request.form.get("time", ""), max_len=5)
            try: rt = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                flash("Invalid time format. Use HH:MM.")
                return redirect(url_for("reminders.asha_set_reminder"))
            reminder = MedicineReminder(
                patient_id=p_id, created_by="asha",
                medicine_name=sanitize_input(request.form.get("medicine", ""), max_len=100),
                dosage=sanitize_input(request.form.get("dosage", ""), max_len=50),
                reminder_time=rt,
                frequency=sanitize_input(request.form.get("frequency", ""), max_len=50),
                status="pending"
            )
            db.session.add(reminder)
            db.session.commit()
            flash("Reminder assigned to patient.", "success")
        elif action == "delete":
            r_id = request.form.get("reminder_id")
            rem = db.session.get(MedicineReminder, r_id)
            if rem and rem.created_by == "asha" and rem.patient_id in [u.id for u in patient_users]:
                db.session.delete(rem)
                db.session.commit()
                flash("Reminder deleted.", "success")
        return redirect(url_for("reminders.asha_set_reminder", patient_id=request.form.get("patient_id")))

    return render_template(
        "asha_set_reminder.html",
        patients=patient_users,
        reminders=patient_reminders_list,
        selected_patient_id=selected_patient_id,
    )
