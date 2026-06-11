from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, PatientProfile, AshaProfile, Message
from extensions import socketio

emergency_bp = Blueprint('emergency', __name__)

@emergency_bp.route("/emergency-alert", methods=["POST"])
@login_required
def emergency_alert():
    if current_user.role.lower() != "patient":
        from flask import abort
        abort(403)

    patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
    if not patient or not patient.area:
        flash("Profile not complete. Cannot send alert.", "danger")
        return redirect(url_for("dashboard.dashboard"))

    ashas = AshaProfile.query.filter_by(area=patient.area).all()
    if not ashas:
        flash("No ASHA worker assigned to your area.", "warning")
        return redirect(url_for("dashboard.dashboard"))

    for asha in ashas:
        if not asha.user_id: continue
        msg = Message(sender_id=current_user.id, receiver_id=asha.user_id, sender_role="patient", message="🚨 EMERGENCY ALERT: I need urgent medical assistance!")
        db.session.add(msg)
        socketio.emit("emergency_received", {"patient_name": patient.name, "patient_id": current_user.id, "message": "🚨 EMERGENCY ALERT: I need urgent medical assistance!"}, room=f"user_{asha.user_id}")

    db.session.commit()
    flash("Emergency alert sent to all ASHA workers in your area!", "danger")
    return redirect(url_for("dashboard.dashboard"))
