from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user
from datetime import datetime, date
import re
from models import Household, Person, Pregnancy, ANCVisit, ChildProfile, ElderlyProfile, HealthVisit, CaseRecord, Task, AshaProfile
from models import db
# -------------------------------------------------
# Blueprint
# -------------------------------------------------
asha_bp = Blueprint(
    "asha",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/asha"
)

# -------------------------------------------------
# Utils
# -------------------------------------------------
@asha_bp.before_request
def require_asha_role():
    if not getattr(current_user, "is_authenticated", False):
        return
    if current_user.role.lower() != "asha":
        abort(403)

# ---------- INPUT SANITIZATION UTILS ----------
def sanitize_input(text, max_len=1000):
    if not text:
        return ""
    # Basic sanitization: strip and limit length
    cleaned = str(text).strip()
    # Remove potential script tags or basic HTML if any
    cleaned = re.sub(r'<[^>]*?>', '', cleaned)
    return cleaned[:max_len]

def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def get_asha_area_info():
    profile = AshaProfile.query.filter_by(user_id=current_user.id).first()
    if not profile or not profile.area:
        return None, [current_user.id]
    
    # Get all ASHA user IDs in the same area
    other_ashas = AshaProfile.query.filter_by(area=profile.area).all()
    asha_ids = [a.user_id for a in other_ashas]
    if current_user.id not in asha_ids:
        asha_ids.append(current_user.id)
        
    return profile.area, asha_ids

# -------------------------------------------------
# Routes
# -------------------------------------------------
@asha_bp.route("/")
@login_required
def asha_home():
    return render_template("asha_index.html")

# ---------------- HOUSEHOLD MANAGEMENT ----------------
@asha_bp.route("/households", methods=["GET", "POST"])
@login_required
def households():
    area, asha_ids = get_asha_area_info()
    edit_id = request.args.get("edit")
    
    # Check if the household to edit belongs to the area or the current ASHA
    edit = None
    if edit_id:
        if area:
            edit = Household.query.filter((Household.id == edit_id) & ((Household.village == area) | (Household.asha_id.in_(asha_ids)))).first()
        else:
            edit = Household.query.filter_by(id=edit_id, asha_id=current_user.id).first()

    if request.method == "POST":
        eid = request.form.get("edit_id")
        if eid:
            if area:
                h = Household.query.filter((Household.id == eid) & ((Household.village == area) | (Household.asha_id.in_(asha_ids)))).first()
            else:
                h = Household.query.filter_by(id=eid, asha_id=current_user.id).first()
            
            if h:
                h.head_name = sanitize_input(request.form.get("head_name"), max_len=100)
                h.village = sanitize_input(request.form.get("village"), max_len=100)
                h.address = sanitize_input(request.form.get("address"), max_len=200)
                h.mobile = sanitize_input(request.form.get("mobile"), max_len=15)
                h.is_synced = False
                h.last_updated = datetime.utcnow()
        else:
            h = Household(
                asha_id=current_user.id,
                head_name=sanitize_input(request.form.get("head_name"), max_len=100),
                village=sanitize_input(request.form.get("village"), max_len=100) or area,
                address=sanitize_input(request.form.get("address"), max_len=200),
                mobile=sanitize_input(request.form.get("mobile"), max_len=15)
            )
            db.session.add(h)
        db.session.commit()
        return redirect(url_for("asha.households"))

    if area:
        rows = Household.query.filter((Household.village == area) | (Household.asha_id.in_(asha_ids))).order_by(Household.id.desc()).all()
    else:
        rows = Household.query.filter_by(asha_id=current_user.id).order_by(Household.id.desc()).all()
    
    return render_template("households.html", rows=rows, edit=edit)

@asha_bp.route("/household/<int:id>/delete", methods=["POST"])
@login_required
def delete_household(id):
    area, asha_ids = get_asha_area_info()
    if area:
        h = Household.query.filter((Household.id == id) & ((Household.village == area) | (Household.asha_id.in_(asha_ids)))).first_or_404()
    else:
        h = Household.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    db.session.delete(h)
    db.session.commit()
    return redirect(url_for("asha.households"))

@asha_bp.route("/household/<int:id>/members", methods=["GET", "POST"])
@login_required
def household_members(id):
    area, asha_ids = get_asha_area_info()
    if area:
        h = Household.query.filter((Household.id == id) & ((Household.village == area) | (Household.asha_id.in_(asha_ids)))).first_or_404()
    else:
        h = Household.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    if request.method == "POST":
        p = Person(
            name=sanitize_input(request.form.get("name"), max_len=100),
            age=int(sanitize_input(request.form.get("age"), max_len=3)) if request.form.get("age") else None,
            sex=sanitize_input(request.form.get("sex"), max_len=10),
            category=sanitize_input(request.form.get("category"), max_len=20),
            household_id=id
        )
        db.session.add(p)
        db.session.commit()
        
        # Initialize category-specific profiles
        if p.category == "pregnant":
            lmp = parse_date(sanitize_input(request.form.get("lmp_date"), max_len=10))
            # Calculate EDD automatically (LMP + 280 days)
            edd = None
            if lmp:
                from datetime import timedelta
                edd = lmp + timedelta(days=280)
            
            preg = Pregnancy(
                person_id=p.id, 
                asha_id=current_user.id,
                status="ongoing",
                lmp_date=lmp,
                edd_date=edd
            )
            db.session.add(preg)
        elif p.category == "child":
            cp = ChildProfile(
                person_id=p.id,
                birth_date=parse_date(sanitize_input(request.form.get("birth_date"), max_len=10)),
                birth_weight=float(sanitize_input(request.form.get("birth_weight"), max_len=5)) if request.form.get("birth_weight") else None
            )
            db.session.add(cp)
        elif p.category == "elderly":
            ep = ElderlyProfile(
                person_id=p.id,
                chronic_conditions=sanitize_input(request.form.get("chronic_conditions"), max_len=500)
            )
            db.session.add(ep)
        
        db.session.commit()
        return redirect(url_for("asha.household_members", id=id))

    return render_template("household_members.html", household=h)

@asha_bp.route("/member/<int:id>/edit", methods=["POST"])
@login_required
def edit_member(id):
    area, asha_ids = get_asha_area_info()
    if area:
        p = Person.query.join(Household).filter(Person.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        p = Person.query.join(Household).filter(Person.id == id, Household.asha_id == current_user.id).first_or_404()
    
    p.name = sanitize_input(request.form.get("name"), max_len=100)
    p.age = int(sanitize_input(request.form.get("age"), max_len=3)) if request.form.get("age") else p.age
    p.sex = sanitize_input(request.form.get("sex"), max_len=10)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/member/<int:id>/delete", methods=["POST"])
@login_required
def delete_member(id):
    area, asha_ids = get_asha_area_info()
    if area:
        p = Person.query.join(Household).filter(Person.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        p = Person.query.join(Household).filter(Person.id == id, Household.asha_id == current_user.id).first_or_404()
    
    db.session.delete(p)
    db.session.commit()
    return redirect(request.referrer)

# ---------------- PREGNANT WOMEN (NEW) ----------------
@asha_bp.route("/pregnancy-track", methods=["GET"])
@login_required
def pregnancy_track():
    area, asha_ids = get_asha_area_info()
    if area:
        pregnancies = Pregnancy.query.join(Person).join(Household).filter((Household.village == area) | (Household.asha_id.in_(asha_ids)), Pregnancy.status == "ongoing").all()
    else:
        pregnancies = Pregnancy.query.filter_by(asha_id=current_user.id, status="ongoing").all()
    return render_template("pregnancy_track.html", pregnancies=pregnancies)

@asha_bp.route("/pregnancy/<int:id>/edit", methods=["POST"])
@login_required
def edit_pregnancy(id):
    area, asha_ids = get_asha_area_info()
    if area:
        p = Pregnancy.query.join(Person).join(Household).filter(Pregnancy.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        p = Pregnancy.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    p.lmp_date = parse_date(sanitize_input(request.form.get("lmp_date"), max_len=10))
    p.edd_date = parse_date(sanitize_input(request.form.get("edd_date"), max_len=10))
    p.status = sanitize_input(request.form.get("status"), max_len=20)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/pregnancy/<int:id>/visit", methods=["POST"])
@login_required
def add_anc_visit(id):
    area, asha_ids = get_asha_area_info()
    # Ensure this pregnancy belongs to this ASHA's area
    if area:
        Pregnancy.query.join(Person).join(Household).filter(Pregnancy.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        Pregnancy.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    v = ANCVisit(
        pregnancy_id=id,
        visit_date=parse_date(sanitize_input(request.form.get("visit_date"), max_len=10)),
        bp=sanitize_input(request.form.get("bp"), max_len=20),
        weight=float(sanitize_input(request.form.get("weight"), max_len=5)) if request.form.get("weight") else None,
        hb=float(sanitize_input(request.form.get("hb"), max_len=5)) if request.form.get("hb") else None,
        tt_dose=sanitize_input(request.form.get("tt_dose"), max_len=20),
        notes=sanitize_input(request.form.get("notes"), max_len=500)
    )
    db.session.add(v)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/anc-visit/<int:id>/edit", methods=["POST"])
@login_required
def edit_anc_visit(id):
    area, asha_ids = get_asha_area_info()
    if area:
        v = ANCVisit.query.join(Pregnancy).join(Person).join(Household).filter(ANCVisit.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        v = ANCVisit.query.join(Pregnancy).filter(ANCVisit.id == id, Pregnancy.asha_id == current_user.id).first_or_404()
    
    v.visit_date = parse_date(sanitize_input(request.form.get("visit_date"), max_len=10))
    v.bp = sanitize_input(request.form.get("bp"), max_len=20)
    v.weight = float(sanitize_input(request.form.get("weight"), max_len=5)) if request.form.get("weight") else None
    v.hb = float(sanitize_input(request.form.get("hb"), max_len=5)) if request.form.get("hb") else None
    v.tt_dose = sanitize_input(request.form.get("tt_dose"), max_len=20)
    v.notes = sanitize_input(request.form.get("notes"), max_len=500)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/anc-visit/<int:id>/delete", methods=["POST"])
@login_required
def delete_anc_visit(id):
    area, asha_ids = get_asha_area_info()
    if area:
        v = ANCVisit.query.join(Pregnancy).join(Person).join(Household).filter(ANCVisit.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        v = ANCVisit.query.join(Pregnancy).filter(ANCVisit.id == id, Pregnancy.asha_id == current_user.id).first_or_404()
    
    db.session.delete(v)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/case-record/<int:id>/edit", methods=["POST"])
@login_required
def edit_case_record(id):
    area, asha_ids = get_asha_area_info()
    if area:
        cr = CaseRecord.query.join(Person).join(Household).filter(CaseRecord.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        cr = CaseRecord.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    cr.problem = sanitize_input(request.form.get("problem"), max_len=500)
    cr.referral_facility = sanitize_input(request.form.get("referral_facility"), max_len=100)
    cr.referral_date = parse_date(sanitize_input(request.form.get("referral_date"), max_len=10))
    cr.outcome = sanitize_input(request.form.get("outcome"), max_len=500)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/case-record/<int:id>/delete", methods=["POST"])
@login_required
def delete_case_record(id):
    area, asha_ids = get_asha_area_info()
    if area:
        cr = CaseRecord.query.join(Person).join(Household).filter(CaseRecord.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        cr = CaseRecord.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    db.session.delete(cr)
    db.session.commit()
    return redirect(request.referrer)

# ---------------- CHILD TRACK (NEW) ----------------
@asha_bp.route("/child-track", methods=["GET"])
@login_required
def child_track():
    area, asha_ids = get_asha_area_info()
    if area:
        children = ChildProfile.query.join(Person).join(Household).filter((Household.village == area) | (Household.asha_id.in_(asha_ids))).all()
    else:
        children = ChildProfile.query.join(Person).join(Household).filter(Household.asha_id == current_user.id).all()
    return render_template("child_track.html", children=children)

@asha_bp.route("/child-profile/<int:id>/edit", methods=["POST"])
@login_required
def edit_child_profile(id):
    area, asha_ids = get_asha_area_info()
    if area:
        cp = ChildProfile.query.join(Person).join(Household).filter(ChildProfile.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        cp = ChildProfile.query.join(Person).join(Household).filter(ChildProfile.id == id, Household.asha_id == current_user.id).first_or_404()
    
    cp.birth_date = parse_date(sanitize_input(request.form.get("birth_date"), max_len=10))
    cp.birth_weight = float(sanitize_input(request.form.get("birth_weight"), max_len=5)) if request.form.get("birth_weight") else None
    db.session.commit()
    return redirect(request.referrer)

# ---------------- ELDERLY TRACK (NEW) ----------------
@asha_bp.route("/elderly-track", methods=["GET"])
@login_required
def elderly_track():
    area, asha_ids = get_asha_area_info()
    if area:
        elderly = ElderlyProfile.query.join(Person).join(Household).filter((Household.village == area) | (Household.asha_id.in_(asha_ids))).all()
    else:
        elderly = ElderlyProfile.query.join(Person).join(Household).filter(Household.asha_id == current_user.id).all()
    return render_template("elderly_track.html", elderly=elderly)

@asha_bp.route("/elderly-profile/<int:id>/edit", methods=["POST"])
@login_required
def edit_elderly_profile(id):
    area, asha_ids = get_asha_area_info()
    if area:
        ep = ElderlyProfile.query.join(Person).join(Household).filter(ElderlyProfile.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        ep = ElderlyProfile.query.join(Person).join(Household).filter(ElderlyProfile.id == id, Household.asha_id == current_user.id).first_or_404()
    
    ep.chronic_conditions = sanitize_input(request.form.get("chronic_conditions"), max_len=500)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/person/<int:id>/health-visit", methods=["POST"])
@login_required
def add_health_visit(id):
    area, asha_ids = get_asha_area_info()
    # Ensure this person belongs to this ASHA's area
    if area:
        Person.query.join(Household).filter(Person.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        Person.query.join(Household).filter(Person.id == id, Household.asha_id == current_user.id).first_or_404()
    
    hv = HealthVisit(
        person_id=id,
        asha_id=current_user.id,
        visit_date=parse_date(sanitize_input(request.form.get("visit_date"), max_len=10)),
        bp=sanitize_input(request.form.get("bp"), max_len=20),
        sugar=float(sanitize_input(request.form.get("sugar"), max_len=5)) if request.form.get("sugar") else None,
        weight=float(sanitize_input(request.form.get("weight"), max_len=5)) if request.form.get("weight") else None,
        height=float(sanitize_input(request.form.get("height"), max_len=5)) if request.form.get("height") else None,
        notes=sanitize_input(request.form.get("notes"), max_len=500)
    )
    db.session.add(hv)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/health-visit/<int:id>/edit", methods=["POST"])
@login_required
def edit_health_visit(id):
    area, asha_ids = get_asha_area_info()
    if area:
        hv = HealthVisit.query.join(Person).join(Household).filter(HealthVisit.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        hv = HealthVisit.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    hv.visit_date = parse_date(sanitize_input(request.form.get("visit_date"), max_len=10))
    hv.bp = sanitize_input(request.form.get("bp"), max_len=20)
    hv.sugar = float(sanitize_input(request.form.get("sugar"), max_len=5)) if request.form.get("sugar") else None
    hv.weight = float(sanitize_input(request.form.get("weight"), max_len=5)) if request.form.get("weight") else None
    hv.height = float(sanitize_input(request.form.get("height"), max_len=5)) if request.form.get("height") else None
    hv.notes = sanitize_input(request.form.get("notes"), max_len=500)
    db.session.commit()
    return redirect(request.referrer)

@asha_bp.route("/health-visit/<int:id>/delete", methods=["POST"])
@login_required
def delete_health_visit(id):
    area, asha_ids = get_asha_area_info()
    if area:
        hv = HealthVisit.query.join(Person).join(Household).filter(HealthVisit.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        hv = HealthVisit.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    db.session.delete(hv)
    db.session.commit()
    return redirect(request.referrer)

# ---------------- GENERAL PATIENT TRACK (NEW) ----------------
@asha_bp.route("/general-track", methods=["GET"])
@login_required
def general_track():
    area, asha_ids = get_asha_area_info()
    # Show all persons in 'general' category in the area
    if area:
        persons = Person.query.join(Household).filter((Household.village == area) | (Household.asha_id.in_(asha_ids)), Person.category == "general").all()
    else:
        persons = Person.query.join(Household).filter(Household.asha_id == current_user.id, Person.category == "general").all()
    return render_template("general_track.html", persons=persons)

@asha_bp.route("/person/<int:id>/case-record", methods=["POST"])
@login_required
def add_case_record(id):
    area, asha_ids = get_asha_area_info()
    # Ensure this person belongs to this ASHA's area
    if area:
        Person.query.join(Household).filter(Person.id == id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
    else:
        Person.query.join(Household).filter(Person.id == id, Household.asha_id == current_user.id).first_or_404()
    
    cr = CaseRecord(
        person_id=id,
        asha_id=current_user.id,
        problem=sanitize_input(request.form.get("problem"), max_len=500),
        referral_facility=sanitize_input(request.form.get("referral_facility"), max_len=100),
        referral_date=parse_date(sanitize_input(request.form.get("referral_date"), max_len=10)),
        outcome=sanitize_input(request.form.get("outcome"), max_len=500)
    )
    db.session.add(cr)
    db.session.commit()
    return redirect(request.referrer)

# ---------------- TASKS (NEW) ----------------
@asha_bp.route("/tasks-manage", methods=["GET", "POST"])
@login_required
def tasks_manage():
    area, asha_ids = get_asha_area_info()
    if request.method == "POST":
        person_id_raw = sanitize_input(request.form.get("person_id"), max_len=10)
        person_id = int(person_id_raw) if person_id_raw else None
        if person_id:
            # Ensure person belongs to this ASHA's area
            if area:
                Person.query.join(Household).filter(Person.id == person_id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
            else:
                Person.query.join(Household).filter(Person.id == person_id, Household.asha_id == current_user.id).first_or_404()
        
        t = Task(
            person_id=person_id,
            asha_id=current_user.id,
            task_type=sanitize_input(request.form.get("task_type"), max_len=100),
            due_date=parse_date(sanitize_input(request.form.get("due_date"), max_len=10)),
            status="pending",
            notes=sanitize_input(request.form.get("notes"), max_len=500)
        )
        db.session.add(t)
        db.session.commit()
        return redirect(url_for("asha.tasks_manage"))

    if area:
        tasks = Task.query.filter(Task.asha_id.in_(asha_ids)).order_by(Task.due_date.asc()).all()
        persons = Person.query.join(Household).filter((Household.village == area) | (Household.asha_id.in_(asha_ids))).all()
    else:
        tasks = Task.query.filter_by(asha_id=current_user.id).order_by(Task.due_date.asc()).all()
        persons = Person.query.join(Household).filter(Household.asha_id == current_user.id).all()
    
    return render_template("tasks_manage.html", tasks=tasks, persons=persons, today=date.today())

@asha_bp.route("/task/<int:id>/status", methods=["POST"])
@login_required
def update_task_status(id):
    area, asha_ids = get_asha_area_info()
    if area:
        t = Task.query.filter((Task.id == id) & (Task.asha_id.in_(asha_ids))).first_or_404()
    else:
        t = Task.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    t.status = "completed" if t.status == "pending" else "pending"
    db.session.commit()
    return redirect(url_for("asha.tasks_manage"))

@asha_bp.route("/task/<int:id>/edit", methods=["POST"])
@login_required
def edit_task(id):
    area, asha_ids = get_asha_area_info()
    if area:
        t = Task.query.filter((Task.id == id) & (Task.asha_id.in_(asha_ids))).first_or_404()
    else:
        t = Task.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    t.task_type = sanitize_input(request.form.get("task_type"), max_len=100)
    t.due_date = parse_date(sanitize_input(request.form.get("due_date"), max_len=10))
    t.notes = sanitize_input(request.form.get("notes"), max_len=500)
    
    person_id_raw = sanitize_input(request.form.get("person_id"), max_len=10)
    person_id = int(person_id_raw) if person_id_raw else None
    if person_id:
        # Ensure person belongs to this ASHA's area
        if area:
            Person.query.join(Household).filter(Person.id == person_id, (Household.village == area) | (Household.asha_id.in_(asha_ids))).first_or_404()
        else:
            Person.query.join(Household).filter(Person.id == person_id, Household.asha_id == current_user.id).first_or_404()
    
    t.person_id = person_id
    db.session.commit()
    return redirect(url_for("asha.tasks_manage"))

@asha_bp.route("/task/<int:id>/delete", methods=["POST"])
@login_required
def delete_task(id):
    area, asha_ids = get_asha_area_info()
    if area:
        t = Task.query.filter((Task.id == id) & (Task.asha_id.in_(asha_ids))).first_or_404()
    else:
        t = Task.query.filter_by(id=id, asha_id=current_user.id).first_or_404()
    
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for("asha.tasks_manage"))
