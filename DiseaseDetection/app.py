from flask import Blueprint, render_template, request, session, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from models import db, Message, PatientProfile, AshaProfile
import pickle
import pandas as pd
import numpy as np
from collections import Counter
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import RegexpTokenizer
import os


disease_bp = Blueprint(
    "disease",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/disease"
)

lemmatizer = WordNetLemmatizer()
splitter = RegexpTokenizer(r'\w+')

BASE_DIR = os.path.dirname(__file__)

# ---------------- Load Data ----------------
lr = pickle.load(open(os.path.join(BASE_DIR, "lr_model_saved.pkl"), "rb"))

df_norm = pd.read_csv(os.path.join(BASE_DIR, "disease-symptoms.csv"), encoding="latin1")
dataset_symptoms = list(df_norm.columns[1:])

description_df = pd.read_csv(os.path.join(BASE_DIR, "disease_description.csv"), encoding="latin1")
do_df = pd.read_csv(os.path.join(BASE_DIR, "disease_dos.csv"), encoding="latin1")
dont_df = pd.read_csv(os.path.join(BASE_DIR, "disease_donts.csv"), encoding="latin1")

# ---------------- Utils ----------------
def preprocess(sym):
    sym = sym.lower().replace('-', ' ').replace("'", '')
    return ' '.join(lemmatizer.lemmatize(w) for w in splitter.tokenize(sym))

def get_visuals(symptoms_list):
    static_dir = os.path.join(BASE_DIR, "static", "images")
    visuals = []
    for s in symptoms_list:
        slug = s.replace(" ", "_")
        for ext in [".png", ".jpg", ".jpeg", ".gif"]:
            candidate = os.path.join(static_dir, slug + ext)
            if os.path.exists(candidate):
                visuals.append({"sym": s, "image": f"images/{slug}{ext}"})
                break
    return visuals

def match_symptoms(user_syms, threshold=0.5):
    matched = set()
    for data_sym in dataset_symptoms:
        tokens = data_sym.split()
        for u in user_syms:
            if sum(t in u.split() for t in tokens) / len(tokens) > threshold:
                matched.add(data_sym)
    return list(matched)

def cooccurring(symptoms, top_n=10):
    disease_set = set()
    counter = Counter()

    for s in symptoms:
        disease_set.update(df_norm[df_norm[s] == 1]["Disease"])

    for d in disease_set:
        row = df_norm[df_norm["Disease"] == d].iloc[0, 1:]
        for i, val in enumerate(row):
            sym_name = dataset_symptoms[i]
            if val == 1 and sym_name not in symptoms:
                counter[sym_name] += 1

    return [sym for sym, _ in counter.most_common(top_n)]

def predict(symptoms, top_k=5):
    x = [0] * len(dataset_symptoms)
    for s in symptoms:
        if s in dataset_symptoms:
            x[dataset_symptoms.index(s)] = 1

    probs = lr.predict_proba([x])[0]
    top_indices = np.argsort(probs)[-top_k:][::-1]

    final_preds = []
    for i in top_indices:
        disease = lr.classes_[i]
        disease_row = df_norm.loc[df_norm["Disease"] == disease].iloc[0, 1:]
        disease_syms = {
            dataset_symptoms[j] for j, val in enumerate(disease_row) if val == 1
        }
        overlap_prob = (len(disease_syms & set(symptoms)) + 1) / (len(set(symptoms)) + 1)
        final_preds.append((disease, round(overlap_prob * 100, 2)))

    return sorted(final_preds, key=lambda x: x[1], reverse=True)

# ---------------- Guards ----------------
@disease_bp.before_request
def require_patient_role():
    if not getattr(current_user, "is_authenticated", False):
        return
    if current_user.role != "patient":
        abort(403)

# ---------------- Routes ----------------
@disease_bp.route("/", methods=["GET", "POST"])
@login_required
def disease_home():
    if request.method == "POST":
        choice = request.form.get("input_choice")
        if choice == "manual":
            return redirect(url_for("disease.manual_input"))
        elif choice == "visual":
            return redirect(url_for("disease.visual_input"))
    return render_template("disease_home.html")

@disease_bp.route("/manual_input", methods=["GET", "POST"])
@login_required
def manual_input():
    if request.method == "POST":
        user_input = request.form.get("symptoms", "")[:1000]
        user_syms = [preprocess(s.strip()) for s in user_input.split(",")]
        matched = match_symptoms(user_syms)
        session["symptoms"] = matched
        session["co_symptoms"] = cooccurring(matched)
        return redirect(url_for("disease.manual_refine"))
    return render_template("manual_input.html")


@disease_bp.route("/visual_input", methods=["GET", "POST"])
@login_required
def visual_input():
    available_visuals = get_visuals(dataset_symptoms)
    if request.method == "POST":
        selected_syms = request.form.getlist("visual_symptoms")
        session["symptoms"] = [s for s in selected_syms if s in dataset_symptoms]
        session["co_symptoms"] = cooccurring(session["symptoms"])
        return redirect(url_for("disease.visual_refine"))
    return render_template("visual_input.html", visuals=available_visuals)



@disease_bp.route("/manual_refine", methods=["GET", "POST"])
@login_required
def manual_refine():
    matched = session.get("symptoms", [])
    co_symptoms = session.get("co_symptoms", [])

    if request.method == "POST":
        extra = request.form.getlist("extra_symptoms")
        session["final"] = list(set(matched + extra))
        return redirect(url_for("disease.result"))

    return render_template("manual_refine.html", matched=matched, co_symptoms=co_symptoms)


@disease_bp.route("/visual_refine", methods=["GET", "POST"])
@login_required
def visual_refine():
    matched = session.get("symptoms", [])
    co_symptoms = session.get("co_symptoms", [])

    if request.method == "POST":
        extra = request.form.getlist("extra_symptoms")
        session["final"] = list(set(matched + extra))
        return redirect(url_for("disease.result"))

    return render_template(
        "visual_refine.html",
        matched=get_visuals(matched),
        co_symptoms=get_visuals(co_symptoms)
    )

@disease_bp.route("/result")
@login_required
def result():
    final = session.get("final", [])
    predictions = predict(final)
    return render_template("result.html", final=final, predictions=predictions)


@disease_bp.route("/disease_info/<disease>")
@login_required
def disease_info(disease):
    desc = description_df.loc[
        description_df["Disease"] == disease, "Description"
    ].values
    description = desc[0] if len(desc) > 0 else "No description available."

    do_row = do_df.loc[do_df["Disease"] == disease]
    do_list = (
        [str(do_row.iloc[0][c]) for c in do_df.columns if c.startswith("Do") and str(do_row.iloc[0][c]) != "nan"]
        if not do_row.empty else ["No information available."]
    )

    dont_row = dont_df.loc[dont_df["Disease"] == disease]
    dont_list = (
        [str(dont_row.iloc[0][c]) for c in dont_df.columns if c.startswith("Dont") and str(dont_row.iloc[0][c]) != "nan"]
        if not dont_row.empty else ["No information available."]
    )

    return render_template(
        "disease_info.html",
        disease=disease,
        description=description,
        do_list=do_list,
        dont_list=dont_list
    )


@disease_bp.route("/send_to_asha", methods=["POST"])
@login_required
def send_to_asha():
    final = session.get("final", [])
    if not final:
        flash("No symptoms to send.", "warning")
        return redirect(url_for("disease.disease_home"))

    predictions = predict(final)
    if not predictions:
        flash("No predictions to send.", "warning")
        return redirect(url_for("disease.result"))

    # Get current patient's profile to find their area
    patient = PatientProfile.query.filter_by(user_id=current_user.id).first()
    if not patient or not patient.area:
        flash("Please complete your profile with area info first.", "warning")
        return redirect(url_for("dashboard.patient_profile"))

    # Find ASHAs in the same area
    ashas = AshaProfile.query.filter_by(area=patient.area).all()
    if not ashas:
        flash("No ASHA workers found in your area.", "info")
        return redirect(url_for("disease.result"))

    # Format the message
    symptoms_str = ", ".join(final)
    preds_str = "\n".join([f"- {d} ({p}%)" for d, p in predictions[:3]])
    
    msg_text = (
        f"Hello, I have used the disease detection tool.\n\n"
        f"Symptoms: {symptoms_str}\n\n"
        f"Predicted Conditions:\n{preds_str}\n\n"
        f"Please provide guidance."
    )

    # Send message to all ASHAs in the area
    sent_count = 0
    for asha in ashas:
        if asha.user_id:
            msg = Message(
                sender_id=current_user.id,
                receiver_id=asha.user_id,
                sender_role="patient",
                message=msg_text
            )
            db.session.add(msg)
            sent_count += 1
    
    if sent_count > 0:
        db.session.commit()
        flash(f"Results sent to {sent_count} ASHA worker(s) in your area.", "success")
    else:
        flash("Could not find ASHA workers to send to.", "warning")

    return redirect(url_for("disease.result"))
