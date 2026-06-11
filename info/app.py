from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from .content import categories, articles, videos
from models import InfoVideo

# -------------------------------------------------
# Blueprint instead of Flask app
# -------------------------------------------------
info_bp = Blueprint(
    "info",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/info"
)

# -------------------------------------------------
# Context processor
# -------------------------------------------------
@info_bp.context_processor
def inject_categories():
    return {
        "categories": categories,
        "videos": videos
    }

# -------------------------------------------------
# Routes
# -------------------------------------------------
@info_bp.before_request
def info_role_guard():
    if not getattr(current_user, "is_authenticated", False):
        return
    ep = request.endpoint or ""
    ep_name = ep.split(".")[-1] if ep else ""
    if ep_name == "upload_video":
        if current_user.role != "asha":
            abort(403)
    else:
        # Allow both patients and ASHA workers to view content
        if current_user.role not in ["patient", "asha"]:
            abort(403)
@info_bp.route("/")
@login_required
def info_home():
    return render_template("info_index.html", categories=categories)

@info_bp.route("/category/<name>")
@login_required
def category(name):
    normalized = name.lower().replace(" ", "-").replace("&", "and")

    if normalized == "video":
        video_list_static = [
            {"slug": slug, **v}
            for slug, v in videos.items()
            if v["category"].lower().replace(" ", "-").replace("&", "and") == normalized
        ]
        video_list_db = [
            {
                "id": v.id,
                "title": v.title,
                "summary": v.summary,
                "created_by": v.created_by
            }
            for v in InfoVideo.query.order_by(InfoVideo.created_at.desc()).all()
        ]
        return render_template(
            "videos.html",
            videos_static=video_list_static,
            videos_db=video_list_db,
            category=normalized
        )

    filtered = [
        a for a in articles.values()
        if a["category"].lower().replace(" ", "-").replace("&", "and") == normalized
    ]

    return render_template(
        "category.html",
        articles=filtered,
        category=normalized
    )

@info_bp.route("/article/<slug>")
@login_required
def article(slug):
    article = articles.get(slug)
    if not article:
        abort(404)
    return render_template("article.html", article=article)

# -------------------------------------------------
# Utils
# -------------------------------------------------
def to_embed_url(url: str) -> str:
    u = url.strip().strip("`").strip()
    if "youtube.com/watch" in u and "v=" in u:
        vid = u.split("v=")[1].split("&")[0]
        return f"https://www.youtube.com/embed/{vid}"
    if "youtu.be/" in u:
        vid = u.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/embed/{vid}"
    return u

@info_bp.route("/video/<slug>")
@login_required
def video(slug):
    v = videos.get(slug)
    if not v:
        abort(404)
    embed = to_embed_url(v.get("video_url", ""))
    return render_template(
        "video.html",
        video=v,
        embed_url=embed
    )

@info_bp.route("/video-db/<int:id>")
@login_required
def video_db(id):
    v = InfoVideo.query.get_or_404(id)
    embed = to_embed_url(v.video_url or "")
    return render_template(
        "video.html",
        video={"title": v.title, "summary": v.summary},
        embed_url=embed
    )

@info_bp.route("/upload-video", methods=["GET", "POST"])
@login_required
def upload_video():
    if current_user.role != "asha":
        abort(403)
    if request.method == "POST":
        title = request.form.get("title", "")[:200]
        summary = request.form.get("summary", "")[:1000]
        video_url = request.form.get("video_url", "")[:500]
        if not title:
            abort(400)
        v = InfoVideo(
            title=title,
            summary=summary,
            video_url=video_url,
            created_by=current_user.id
        )
        from models import db
        db.session.add(v)
        db.session.commit()
        flash("Video uploaded successfully!", "success")
        return redirect(url_for("info.my_videos"))
    return render_template("video_upload.html")

@info_bp.route("/my-videos")
@login_required
def my_videos():
    if current_user.role != "asha":
        abort(403)
    
    videos = InfoVideo.query.filter_by(created_by=current_user.id).order_by(InfoVideo.created_at.desc()).all()
    
    video_list_db = [
        {
            "id": v.id,
            "title": v.title,
            "summary": v.summary,
            "created_by": v.created_by
        }
        for v in videos
    ]
    
    return render_template(
        "videos.html",
        videos_static=[],
        videos_db=video_list_db,
        category="my uploaded"
    )

@info_bp.route("/delete-video/<int:id>", methods=["POST"])
@login_required
def delete_video(id):
    if current_user.role != "asha":
        abort(403)
    
    v = InfoVideo.query.get_or_404(id)
    if v.created_by != current_user.id:
        abort(403)
        
    from models import db
    db.session.delete(v)
    db.session.commit()
    flash("Video deleted successfully!", "success")
    return redirect(url_for("info.category", name="video"))
