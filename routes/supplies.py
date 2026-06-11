from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_required, current_user
from models import db, SupplyRequest, PatientProfile, AshaProfile, Message
import re

supplies_bp = Blueprint('supplies', __name__)

def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

@supplies_bp.route("/supplies", methods=["GET", "POST"])
@login_required
def supplies():
    if current_user.role.lower() != "patient":
        from flask import abort
        abort(403)
    patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
    if not patient: return redirect(url_for('dashboard.patient_profile'))
    ashas = AshaProfile.query.filter_by(area=patient.area).order_by(AshaProfile.id.asc()).all() if patient.area else []
    if not ashas:
        flash("No ASHA worker assigned to your area yet.", "warning")
        return render_template("supplies.html", supplies=[], cart=[], ashas=[])

    cart = session.get("supply_cart", [])
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "add":
            item = sanitize_input(request.form.get("item", ""), max_len=100)
            try: qty = int(sanitize_input(request.form.get("quantity", "1"), max_len=5))
            except: qty = 1
            qty = max(1, qty)
            if not item:
                flash("Invalid item.", "danger")
                return redirect(url_for("supplies.supplies"))
            merged = False
            for entry in cart:
                if entry.get("name") == item:
                    entry["quantity"] = int(entry.get("quantity", 1)) + qty
                    merged = True
                    break
            if not merged: cart.append({"name": item, "quantity": qty})
            session["supply_cart"] = cart
            return redirect(url_for("supplies.supplies"))
        elif action == "remove":
            try: idx = int(request.form.get("index", "-1"))
            except: idx = -1
            if 0 <= idx < len(cart):
                cart.pop(idx)
                session["supply_cart"] = cart
            return redirect(url_for("supplies.supplies"))
        elif action == "clear":
            session["supply_cart"] = []
            return redirect(url_for("supplies.supplies"))
        elif action == "checkout":
            asha_id = request.form.get("asha_id")
            if not asha_id:
                flash("Please select an ASHA worker.", "danger")
                return redirect(url_for("supplies.supplies"))
            target_asha_id = int(asha_id)
            if cart:
                for entry in cart:
                    req = SupplyRequest(patient_id=current_user.id, asha_id=target_asha_id, item_name=entry.get("name"), quantity=int(entry.get("quantity", 1)))
                    db.session.add(req)
                summary = ", ".join([f"{e.get('name')} x{int(e.get('quantity', 1))}" for e in cart])
                if summary:
                    msg = Message(sender_id=current_user.id, receiver_id=target_asha_id, sender_role="patient", message=f"Supply request submitted: {summary}")
                    db.session.add(msg)
                db.session.commit()
                session["supply_cart"] = []
                flash("Supply request submitted successfully!", "success")
            return redirect(url_for("supplies.supplies"))

    supplies_list = [
        {"name": "Paracetamol", "image": "paracetamol.jpeg"}, {"name": "Ibuprofen", "image": "ibuprofen.jpeg"},
        {"name": "Cough Syrup", "image": "cough_syrup.jpeg"}, {"name": "ORS Packets", "image": "ors_packets.jpeg"},
        {"name": "Bandages", "image": "bandages.jpeg"}, {"name": "Gauze", "image": "gauze.jpeg"},
        {"name": "Cotton Rolls", "image": "cotton_rolls.jpeg"}, {"name": "Sanitary Pads", "image": "sanitary_pads.jpeg"},
        {"name": "Dettol", "image": "dettol.jpeg"}, {"name": "Hand Sanitizer", "image": "hand_sanitizer.jpeg"},
        {"name": "Betadine Ointment", "image": "betadine_ointment.jpeg"}, {"name": "Burn Ointment", "image": "burn_ointment.jpeg"},
        {"name": "Calcium Tablets", "image": "calcium_tablets.jpeg"}, {"name": "Iron Folic Acid Tablets", "image": "iron_folic_acid_tablets.jpeg"},
        {"name": "Tinidazole", "image": "tinidazole.jpeg"}, {"name": "Water Purification Tablets", "image": "water_purification_tablets.jpeg"},
        {"name": "Vitamin B", "image": "vitamin_B.jpeg"}, {"name": "Vitamin D", "image": "vitamin_D.jpeg"},
        {"name": "Antacid Syrup", "image": "antacid_syrup.jpeg"}, {"name": "Iron Syrup", "image": "iron_syrup.jpeg"},
        {"name": "Diclofenac Gel", "image": "diclofenac_gel.jpeg"}
    ]
    return render_template("supplies.html", supplies=supplies_list, cart=session.get("supply_cart", []), ashas=ashas)

@supplies_bp.route("/asha/requests")
@login_required
def asha_requests():
    if current_user.role.lower() != "asha":
        from flask import abort
        abort(403)
    asha = AshaProfile.query.filter_by(user_id=current_user.id).first()
    if asha and asha.area:
        asha_ids = [a.user_id for a in AshaProfile.query.filter_by(area=asha.area).all()]
        requests = SupplyRequest.query.filter(SupplyRequest.asha_id.in_(asha_ids)).order_by(SupplyRequest.created_at.desc()).all()
    else:
        requests = SupplyRequest.query.filter_by(asha_id=current_user.id).order_by(SupplyRequest.created_at.desc()).all()
    if requests:
        ids = [r.patient_id for r in requests]
        profiles = PatientProfile.query.filter(PatientProfile.user_id.in_(ids)).all()
        name_map = {p.user_id: p.name for p in profiles}
        for r in requests: r.patient_name = name_map.get(r.patient_id)
    return render_template("asha_requests.html", requests=requests)
