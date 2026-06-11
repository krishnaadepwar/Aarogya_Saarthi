from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from flask_socketio import emit, join_room
from models import db, User, Message, PatientProfile, AshaProfile
import re

chat_bp = Blueprint('chat', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@chat_bp.route("/messages")
@login_required
def messages():
    role = current_user.role.lower()
    if role not in ["patient", "asha", "admin"]:
        abort(403)

    user_ids = set()

    if role == "patient":
        patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
        if patient and patient.area:
            ashas = AshaProfile.query.filter_by(area=patient.area).all()
            for a in ashas:
                if a.user_id:
                    user_ids.add(a.user_id)
        
        sent_to_admin = db.session.query(Message.receiver_id).join(User, User.id == Message.receiver_id).filter(Message.sender_id == current_user.id, User.role == 'admin').all()
        received_from_admin = db.session.query(Message.sender_id).join(User, User.id == Message.sender_id).filter(Message.receiver_id == current_user.id, User.role == 'admin').all()
        for r in sent_to_admin: user_ids.add(r[0])
        for r in received_from_admin: user_ids.add(r[0])

    elif role == "asha":
        asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
        if asha and asha.area:
            patients = PatientProfile.query.filter_by(area=asha.area).all()
            for p in patients:
                if p.user_id:
                    user_ids.add(p.user_id)
            other_ashas = AshaProfile.query.filter(AshaProfile.area == asha.area, AshaProfile.user_id != current_user.id).all()
            for a in other_ashas:
                if a.user_id:
                    user_ids.add(a.user_id)
        
        sent_to_admin = db.session.query(Message.receiver_id).join(User, User.id == Message.receiver_id).filter(Message.sender_id == current_user.id, User.role == 'admin').all()
        received_from_admin = db.session.query(Message.sender_id).join(User, User.id == Message.sender_id).filter(Message.receiver_id == current_user.id, User.role == 'admin').all()
        for r in sent_to_admin: user_ids.add(r[0])
        for r in received_from_admin: user_ids.add(r[0])
                    
    elif role == "admin":
        sent_to = db.session.query(Message.receiver_id).filter_by(sender_id=current_user.id).all()
        received_from = db.session.query(Message.sender_id).filter_by(receiver_id=current_user.id).all()
        for r in sent_to: user_ids.add(r[0])
        for r in received_from: user_ids.add(r[0])

    users = User.query.filter(User.id.in_(list(user_ids))).all() if user_ids else []
    
    # Pre-fetch profiles for efficient display
    user_profiles = {}
    unread_counts = {}
    if users:
        patient_profiles = PatientProfile.query.filter(PatientProfile.user_id.in_([u.id for u in users if u.role.lower() == 'patient'])).all()
        asha_profiles = AshaProfile.query.filter(AshaProfile.user_id.in_([u.id for u in users if u.role.lower() == 'asha'])).all()
        
        for p in patient_profiles:
            user_profiles[p.user_id] = {'name': p.name, 'area': p.area}
        for a in asha_profiles:
            user_profiles[a.user_id] = {'name': a.name, 'area': a.area}
            
        # Count unread messages for each user
        for u in users:
            count = Message.query.filter_by(sender_id=u.id, receiver_id=current_user.id, is_read=False).count()
            if count > 0:
                unread_counts[u.id] = count

    return render_template("messages_list.html", users=users, user_profiles=user_profiles, unread_counts=unread_counts)

@chat_bp.route("/messages/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat(user_id):
    role = current_user.role.lower()
    if role not in ["patient", "asha", "admin"]:
        abort(403)

    other_user = User.query.get_or_404(user_id)
    other_role = other_user.role.lower()
    
    # Get other user's profile info
    other_profile = None
    if other_role == 'patient':
        other_profile = PatientProfile.query.filter_by(user_id=other_user.id).first()
    elif other_role == 'asha':
        other_profile = AshaProfile.query.filter_by(user_id=other_user.id).first()

    if role != "admin" and other_role != "admin":
        if role == "patient":
            patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
            if not patient or not patient.area:
                abort(403)
            asha = AshaProfile.query.filter_by(user_id=other_user.id, area=patient.area).first()
            if not asha:
                abort(403)
        elif role == "asha":
            asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
            if other_role != "admin":
                if not asha or not asha.area:
                    abort(403)
                patient = PatientProfile.query.filter_by(user_id=other_user.id, area=asha.area).first()
                other_asha = AshaProfile.query.filter_by(user_id=other_user.id, area=asha.area).first()
                if not patient and not other_asha:
                    abort(403)

    room = f"{min(current_user.id, other_user.id)}_{max(current_user.id, other_user.id)}"
    Message.query.filter_by(receiver_id=current_user.id, sender_id=other_user.id, is_read=False).update({"is_read": True})
    db.session.commit()

    if request.method == "POST":
        message_text = sanitize_input(request.form.get("message", ""), max_len=1000)
        msg = Message(sender_id=current_user.id, receiver_id=other_user.id, sender_role=current_user.role, message=message_text)
        db.session.add(msg)
        db.session.commit()
        return redirect(url_for("chat.chat", user_id=user_id))

    chat_messages = Message.query.filter(((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) | ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))).order_by(Message.created_at).all()
    return render_template("chat.html", messages=chat_messages, other_user=other_user, other_profile=other_profile, room=room)

@chat_bp.route("/messages/broadcast", methods=["GET", "POST"])
@login_required
def broadcast_message():
    if current_user.role.lower() != "asha":
        abort(403)
    asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
    if not asha: abort(400)
    patients = PatientProfile.query.filter_by(area=asha.area).all() if asha.area else []
    patient_user_ids = [p.user_id for p in patients]
    patient_users = User.query.filter(User.id.in_(patient_user_ids)).all() if patient_user_ids else []

    if request.method == "POST":
        message_text = sanitize_input(request.form.get("message", ""), max_len=1000)
        if not message_text:
            flash("Message cannot be empty.", "danger")
            return render_template("broadcast.html", patients=patient_users)
        selected_ids = request.form.getlist("patients") or [str(u.id) for u in patient_users]
        for uid in selected_ids:
            msg = Message(sender_id=current_user.id, receiver_id=int(uid), sender_role="asha", message=message_text)
            db.session.add(msg)
        db.session.commit()
        return redirect(url_for("chat.messages"))
    return render_template("broadcast.html", patients=patient_users)
