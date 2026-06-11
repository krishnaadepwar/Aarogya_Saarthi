from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, time


db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # patient, asha, admin
    profile_completed = db.Column(db.Boolean, default=False)

class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)

    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(15))
    family_members = db.Column(db.Integer)
    area = db.Column(db.String(100), index=True)

class AshaProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    area = db.Column(db.String(100), index=True)
    experience_years = db.Column(db.Integer)

class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    role = db.Column(db.String(20), index=True)   # patient / asha

    title = db.Column(db.String(200))
    description = db.Column(db.Text)

    admin_reply = db.Column(db.Text, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)

    sender_role = db.Column(db.String(20))  # patient / asha
    message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False, index=True)

class SupplyRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)

    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MedicineReminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    created_by = db.Column(db.String(20))  # patient / asha

    medicine_name = db.Column(db.String(100))
    dosage = db.Column(db.String(50))
    reminder_time = db.Column(db.Time)
    frequency = db.Column(db.String(50))  # Daily / Twice a day etc.
    status = db.Column(db.String(20), default="pending")  # pending, taken, missed
    last_taken_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= PROFESSIONAL ASHA MANAGEMENT STRUCTURE =================

class Household(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    head_name = db.Column(db.String(120))
    village = db.Column(db.String(120))
    address = db.Column(db.Text)
    mobile = db.Column(db.String(20))
    is_synced = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to members
    members = db.relationship('Person', backref='household', lazy=True, cascade="all, delete-orphan")

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    sex = db.Column(db.String(10))
    household_id = db.Column(db.Integer, db.ForeignKey('household.id'), index=True)
    category = db.Column(db.String(20), index=True)  # pregnant, child, elderly, general
    is_synced = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    pregnancies = db.relationship('Pregnancy', backref='person', lazy=True, cascade="all, delete-orphan")
    child_profile = db.relationship('ChildProfile', backref='person', uselist=False, lazy=True, cascade="all, delete-orphan")
    elderly_profile = db.relationship('ElderlyProfile', backref='person', uselist=False, lazy=True, cascade="all, delete-orphan")
    health_visits = db.relationship('HealthVisit', backref='person', lazy=True, cascade="all, delete-orphan")
    case_records = db.relationship('CaseRecord', backref='person', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship('Task', backref='person', lazy=True, cascade="all, delete-orphan")

class Pregnancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), index=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    lmp_date = db.Column(db.Date)
    edd_date = db.Column(db.Date)
    gravida = db.Column(db.Integer)
    para = db.Column(db.Integer)
    high_risk = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), index=True)  # ongoing/delivered

    anc_visits = db.relationship('ANCVisit', backref='pregnancy', lazy=True, cascade="all, delete-orphan")

class ANCVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pregnancy_id = db.Column(db.Integer, db.ForeignKey('pregnancy.id'), index=True)
    visit_date = db.Column(db.Date)
    bp = db.Column(db.String(20))
    weight = db.Column(db.Float)
    hb = db.Column(db.Float)
    tt_dose = db.Column(db.String(10))  # None, TT-1, TT-2, Booster
    notes = db.Column(db.Text)

class ChildProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), index=True)
    birth_date = db.Column(db.Date)
    birth_weight = db.Column(db.Float)

class ElderlyProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), index=True)
    chronic_conditions = db.Column(db.Text)

class HealthVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), index=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    visit_date = db.Column(db.Date)
    bp = db.Column(db.String(20))
    sugar = db.Column(db.Float)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    notes = db.Column(db.Text)

class CaseRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), index=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    problem = db.Column(db.Text)
    referral_facility = db.Column(db.String(120))
    referral_date = db.Column(db.Date)
    outcome = db.Column(db.Text)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=True, index=True)
    asha_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=True)
    task_type = db.Column(db.String(50))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), index=True)  # pending/completed
    notes = db.Column(db.Text)

# ===========================================================================


class InfoVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    video_url = db.Column(db.String(500))
    category = db.Column(db.String(50), default="Video")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
