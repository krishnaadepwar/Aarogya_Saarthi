import os
import base64
import requests
from io import BytesIO
from flask import (
    Blueprint, request, render_template, redirect,
    url_for, flash, jsonify, send_file, after_this_request, abort
)
from flask_login import login_required, current_user
from PIL import Image
import pytesseract
import cv2
import numpy as np
from dotenv import load_dotenv
import re
import calendar
import datetime
from dateutil import parser as dateutil_parser
import tempfile

load_dotenv()

# -------------------------------------------------
# Blueprint
# -------------------------------------------------
medicine_bp = Blueprint(
    "medicine",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/medicine"
)

# -------------------------------------------------
# Config
# -------------------------------------------------
OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    "Enter the API key here"  # move to .env in prod
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def ocr_image(pil_image: Image.Image) -> str:
    """
    Improved OCR with rescaling and safer preprocessing.
    Avoids aggressive thresholding which can degrade quality on some images.
    """
    # 1. Convert to OpenCV format
    pil_image = pil_image.convert("RGB")
    img = np.array(pil_image)
    img = img[:, :, ::-1].copy()  # RGB to BGR

    # 2. Rescaling (Upscaling)
    # Tesseract works best with higher resolution images (approx 300 DPI).
    # We upscale by 2x using cubic interpolation for better text clarity.
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # 3. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 4. Denoise
    # Use a median blur which is good for removing salt-and-pepper noise 
    # while preserving edges (text).
    denoised = cv2.medianBlur(gray, 3)

    # 5. Contrast Enhancement (CLAHE)
    # Contrast Limited Adaptive Histogram Equalization
    # Helps if the lighting is uneven but not as destructive as adaptive thresholding.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # 6. OCR Execution with different configurations
    # We try a few configurations and pick the one with the most text.
    
    # Config 1: Default (Automatic Page Segmentation)
    config_default = r'--oem 3 --psm 3'
    text_default = pytesseract.image_to_string(enhanced, config=config_default)

    # Config 2: Assume a single block of text (good for cropped labels)
    config_block = r'--oem 3 --psm 6'
    text_block = pytesseract.image_to_string(enhanced, config=config_block)

    # Return the result that is longer (likely captured more info)
    if len(text_block.strip()) > len(text_default.strip()):
        return text_block.strip()
    return text_default.strip()

def call_openrouter(prompt_text: str, image_b64: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    user_content_str = f"""
---OCR---
{prompt_text if prompt_text.strip() else "NO READABLE TEXT FOUND"}
---END---

Your task:
- Give the most likely medicine name
- Provide uses
- Provide general dosage
- Side effects & warnings
- Expiry date if available
"""

    messages = [
        {"role": "system", "content": "You are a safe medicine assistant."},
    ]

    if image_b64:
        # If we have an image, send it in the payload for vision models
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_content_str
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }
                }
            ]
        })
    else:
        # Fallback to text-only if no image provided (though analyze route always provides it)
        messages.append({
            "role": "user",
            "content": user_content_str
        })

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "reasoning": {"enabled": True}
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

# -------------------------------------------------
# Routes
# -------------------------------------------------
@medicine_bp.before_request
def require_patient_role():
    if not getattr(current_user, "is_authenticated", False):
        return
    if current_user.role != "patient":
        abort(403)
@medicine_bp.route("/", methods=["GET"])
@login_required
def medicine_home():
    return render_template("medicine_index.html")

@medicine_bp.route("/analyze", methods=["POST"])
@login_required
def analyze():
    if "image" not in request.files:
        flash("No file uploaded")
        return redirect(url_for("medicine.medicine_home"))

    file = request.files["image"]
    if file.filename == "":
        flash("No selected file")
        return redirect(url_for("medicine.medicine_home"))

    try:
        img = Image.open(file.stream)
    except Exception as e:
        flash(f"Unable to open image: {e}")
        return redirect(url_for("medicine.medicine_home"))

    ocr_text = ocr_image(img)

    buffered = BytesIO()
    preview = img.copy()
    preview.thumbnail((800, 800))
    preview = preview.convert("RGB")
    preview.save(buffered, format="JPEG", quality=70)
    img_b64 = base64.b64encode(buffered.getvalue()).decode()
    img_data_url = f"data:image/jpeg;base64,{img_b64}"

    try:
        router_resp = call_openrouter(ocr_text, img_b64)
        assistant_content = router_resp["choices"][0]["message"].get("content", "")
    except Exception as e:
        flash(str(e))
        assistant_content = None

    return render_template(
        "medicine_index.html",
        ocr_text=ocr_text,
        image_data=img_data_url,
        assistant_content=assistant_content
    )

@medicine_bp.route("/tts", methods=["POST"])
@login_required
def tts():
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text"}), 400

    import pyttsx3
    engine = pyttsx3.init()
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    engine.save_to_file(text, path)
    engine.runAndWait()

    @after_this_request
    def cleanup(response):
        os.remove(path)
        return response

    return send_file(path, mimetype="audio/wav")

@medicine_bp.route("/check_manual", methods=["POST"])
@login_required
def check_manual():
    date_str = request.form.get("date", "").strip()
    if not date_str:
        return jsonify({"ok": False}), 400

    parsed = dateutil_parser.parse(date_str, fuzzy=True).date()
    today = datetime.date.today()
    days_left = (parsed - today).days

    return jsonify({
        "ok": True,
        "expiry_date": parsed.isoformat(),
        "days_left": days_left,
        "status": "expired" if days_left < 0 else "valid"
    })
