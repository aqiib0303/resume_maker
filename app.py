from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from weasyprint import HTML
from datetime import datetime
import uuid   # ✅ for tokens

# ==================
# CONFIG
# ==================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB upload limit

# ==================
# DATABASE HELPER
# ==================
def get_db():
    conn = sqlite3.connect("instance/users.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================
# IN-MEMORY STORAGE FOR TOKENS
# ==================
resume_tokens = {}
cover_letter_tokens = {}

# ==================
# MAIN ROUTE
# ==================
@app.route("/")
def index():
    return render_template("index.html")

# ==================
# AUTH ROUTES
# ==================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        if cur.fetchone():
            flash("Email already registered!", "error")
            return redirect(url_for("signup"))

        hashed_pw = generate_password_hash(password)
        cur.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                    (name, email, hashed_pw))
        conn.commit()
        conn.close()

        flash("Signup successful! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Welcome back, " + user["name"], "success")
            return redirect(url_for("builder"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ==================
# RESUME ROUTES
# ==================
TEMPLATES = {
    "modern": {"name": "Modern Resume", "premium": False},
    "minimal": {"name": "Minimal Resume", "premium": False},
    "creative": {"name": "Creative Resume", "premium": True},
    "ats_friendly": {"name": "ATS Friendly Resume", "premium": False},
    "ats_modern": {"name": "ATS Modern Resume", "premium": False},
    "premium_modern_pro": {"name": "Premium Modern Pro Resume", "premium": False},
}

def build_payload(form):
    name = form.get("name", "").strip()
    role = form.get("role", "").strip()
    summary = form.get("summary", "").strip()
    skills = [s.strip() for s in form.getlist("skills[]") if s.strip()]

    experiences = []
    for company, role, dates, desc in zip(
        form.getlist("exp_company[]"),
        form.getlist("exp_role[]"),
        form.getlist("exp_dates[]"),
        form.getlist("exp_desc[]")
    ):
        if company.strip() or role.strip() or dates.strip() or desc.strip():
            experiences.append({"company": company, "role": role, "dates": dates, "desc": desc})

    education = []
    for school, degree, dates in zip(
        form.getlist("edu_school[]"),
        form.getlist("edu_degree[]"),
        form.getlist("edu_dates[]")
    ):
        if school.strip() or degree.strip() or dates.strip():
            education.append({"school": school, "degree": degree, "dates": dates})

    if not name:
        abort(400, "Name is required")

    return {"name": name, "role": role, "summary": summary,
            "skills": skills, "experiences": experiences, "education": education}

@app.route("/resume/builder")
def builder():
    return render_template("resume/builder.html")

@app.route("/form")
def form():
    return redirect(url_for("builder"))

@app.route("/resume/preview/<style>", methods=["POST"])
def preview(style):
    if style not in TEMPLATES:
        abort(404, "Template not found")
    data = build_payload(request.form)

    # ✅ Generate token and save data
    token = str(uuid.uuid4())
    resume_tokens[token] = {"data": data, "style": style}

    # Pass token so preview template can build proper GET link
    return render_template(f"resume_templates/{style}.html", data=data, token=token, is_pdf=False)

@app.route("/resume/download/<token>")
def download(token):
    entry = resume_tokens.get(token)
    if not entry:
        abort(404, "Invalid or expired token")
    data = entry["data"]
    style = entry["style"]

    html = render_template(f"resume_templates/{style}.html", data=data, is_pdf=True)
    pdf = HTML(string=html, base_url=app.static_folder).write_pdf()

    filename = f"{data['name'].replace(' ', '_')}_{style}_resume.pdf"
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

@app.route("/resume/preview_templates")
def preview_templates():
    return render_template("resume/preview_templates.html", templates=TEMPLATES)

# ==================
# COVER LETTER ROUTES
# ==================
COVER_LETTER_TEMPLATES = {
    "classic": {"name": "Classic Cover Letter"},
    "modern": {"name": "Modern Cover Letter"},
    "creative": {"name": "Creative Cover Letter"},
}

@app.route("/cover_letter", methods=["GET", "POST"])
def cover_letter():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "company": request.form.get("company", "").strip(),
            "hiring_manager": request.form.get("hiring_manager", "Hiring Manager").strip(),
            "position": request.form.get("position", "").strip(),
            "intro": request.form.get("intro", "").strip(),
            "skills": request.form.get("skills", "").strip(),
            "closing": request.form.get("closing", "").strip(),
            "style": request.form.get("style", "classic"),
            "date": datetime.now().strftime("%B %d, %Y"),
        }

        if not data["name"] or not data["company"] or not data["position"]:
            flash("Name, company, and position are required.", "error")
            return redirect(url_for("cover_letter"))

        token = str(uuid.uuid4())
        cover_letter_tokens[token] = {"data": data, "style": data["style"]}

        return render_template(f"cover_letter/{data['style']}.html", data=data, token=token, is_pdf=False)

    return render_template("cover_letter/form.html", templates=COVER_LETTER_TEMPLATES)

@app.route("/cover_letter/download/<token>", methods=["POST"])
def cover_letter_download(token):
    data = request.form.to_dict()
    html = render_template(f"cover_letter/{data['style']}.html", data=data, is_pdf=True)

    pdf = HTML(string=html, base_url=app.static_folder).write_pdf()

    filename = f"{data.get('name','cover_letter')}_cover_letter.pdf"
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


# ==================
# ERROR HANDLER
# ==================
@app.errorhandler(413)
def too_large(e):
    return ("Payload too large", 413)

# ==================
# RUN
# ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
