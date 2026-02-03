from flask import Flask, request, jsonify, send_from_directory, session, Response
from flask_cors import CORS
import sqlite3
import os
from io import BytesIO
import time
from datetime import timedelta
import hashlib

from werkzeug.security import generate_password_hash, check_password_hash
from recommender import generate_adaptive_recommendations

from dotenv import load_dotenv

load_dotenv()
print("SECRET_KEY loaded:", bool(os.environ.get("SECRET_KEY")))
print("CODE_PEPPER loaded:", bool(os.environ.get("CODE_PEPPER")))

# -------------------------
# App setup
# -------------------------
app = Flask(__name__, static_folder="../frontend", static_url_path="")

# ✅ secret key from env (fallback keeps app working)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-later")

CORS(app, supports_credentials=True)

# ✅ Session timeout (auto logout after inactivity)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=20)

# -------------------------
# Database path (IMPORTANT)
# -------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
print("✅ USING DB:", DB_PATH)

# -------------------------
# DB helpers
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------
# ✅ Hashing helpers
# -------------------------
CODE_PEPPER = os.environ.get("CODE_PEPPER", "dev-pepper-change-me")

def make_code_digest(code: str) -> str:
    raw = (CODE_PEPPER + ":" + code).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def make_code_hash(code: str) -> str:
    return generate_password_hash(code) # salted

def ensure_schema():
    """Create tables if missing + safely add missing columns/indexes."""
    conn = get_conn()
    cur = conn.cursor()

    # USERS table (patients)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            weight REAL,
            height REAL,
            activity TEXT,
            diet TEXT
        )
    """)

    # Add legacy code column if missing (kept for backwards compatibility)
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "code" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code TEXT")

    # ✅ new secure columns
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "code_hash" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code_hash TEXT")
    if "code_digest" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code_digest TEXT")

    # Keep old unique index (safe; multiple NULLs allowed in SQLite)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code ON users(code)")
    # ✅ uniqueness using digest going forward
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code_digest ON users(code_digest)")

    # RECOMMENDATIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bmi REAL,
            diet TEXT,
            exercise TEXT,
            general TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # FEEDBACK
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            score INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # CLINICIANS (NOTE: code is NOT NULL in your DB, we keep it to avoid breaking)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE
        )
    """)

    # ✅ add hashed columns for clinicians too
    cur.execute("PRAGMA table_info(clinicians)")
    ccols = [r["name"] for r in cur.fetchall()]
    if "code_hash" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN code_hash TEXT")
    if "code_digest" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN code_digest TEXT")

    # ✅ uniqueness using digest going forward
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicians_code_digest ON clinicians(code_digest)")

    conn.commit()
    conn.close()

ensure_schema()

# -------------------------
# ✅ Security helpers (login lock + inactivity)
# -------------------------
MAX_FAILS = 5
LOCK_SECONDS = 30

def _lock_key(role: str) -> str:
    return f"lock_{role}"

def _fail_key(role: str) -> str:
    return f"fails_{role}"

def is_locked(role: str) -> bool:
    until = session.get(_lock_key(role))
    if not until:
        return False
    return time.time() < float(until)

def register_fail(role: str):
    fails = int(session.get(_fail_key(role), 0)) + 1
    session[_fail_key(role)] = fails
    if fails >= MAX_FAILS:
        session[_lock_key(role)] = time.time() + LOCK_SECONDS

def clear_fails(role: str):
    session.pop(_fail_key(role), None)
    session.pop(_lock_key(role), None)

def touch_session():
    session["last_activity"] = time.time()

def logged_in() -> bool:
    return session.get("role") in ("patient", "clinician")

@app.before_request
def inactivity_timeout():
    if logged_in():
        now = time.time()
        last = session.get("last_activity", now)
        if now - float(last) > app.permanent_session_lifetime.total_seconds():
            session.clear()
        else:
            touch_session()

@app.after_request
def add_security_headers(resp):
    sensitive_paths = ("/index.html", "/dashboard.html")
    if request.path in sensitive_paths:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp

# -------------------------
# Serve frontend (static)
# -------------------------
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "login.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)

# -------------------------
# Auth helpers
# -------------------------
def is_patient():
    return session.get("role") == "patient" and session.get("user_id") is not None

def is_clinician():
    return session.get("role") == "clinician" and session.get("clinician_id") is not None

@app.route("/whoami", methods=["GET"])
def whoami():
    return jsonify({
        "role": session.get("role"),
        "user_id": session.get("user_id"),
        "clinician_id": session.get("clinician_id"),
        "name": session.get("name"),
    })

@app.route("/me", methods=["GET"])
def me():
    return whoami()

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

# -------------------------
# PATIENT REGISTER (hashed)
# -------------------------
@app.route("/patient-register", methods=["POST"])
def patient_register():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    if not name or not code or len(code) != 6 or not code.isdigit():
        return jsonify({"error": "Please enter full name + 6-digit code"}), 400

    code_digest = make_code_digest(code)
    code_hash = make_code_hash(code)

    conn = get_conn()
    cur = conn.cursor()

    # prevent code reuse (via digest)
    cur.execute("SELECT id FROM users WHERE code_digest = ?", (code_digest,))
    exists = cur.fetchone()
    if exists:
        conn.close()
        return jsonify({"error": "This code is already used. Choose another 6-digit code."}), 409

    # store hashed code (do NOT store plaintext)
    cur.execute(
        "INSERT INTO users (name, code, code_hash, code_digest) VALUES (?, NULL, ?, ?)",
        (name, code_hash, code_digest)
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    session.clear()
    session.permanent = True
    session["role"] = "patient"
    session["user_id"] = user_id
    session["name"] = name
    touch_session()
    clear_fails("patient")

    return jsonify({"message": "Registered & logged in", "user_id": user_id, "name": name})

# -------------------------
# PATIENT LOGIN (SAFE against digest duplicates)
# -------------------------
@app.route("/patient-login", methods=["POST"])
def patient_login():
    if is_locked("patient"):
        return jsonify({"error": f"Too many attempts. Try again in {LOCK_SECONDS} seconds."}), 429

    data = request.json or {}
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    if not name or not code or len(code) != 6 or not code.isdigit():
        register_fail("patient")
        return jsonify({"error": "Invalid login details"}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, name, code_hash, code, code_digest FROM users WHERE name=?", (name,))
    rows = cur.fetchall()

    if not rows:
        conn.close()
        register_fail("patient")
        return jsonify({"error": "Login failed (name/code not found)"}), 401

    matched = None
    for row in rows:
        if row["code_hash"] and check_password_hash(row["code_hash"], code):
            matched = row
            break
        if row["code"] and str(row["code"]).strip() == code:
            matched = row
            break

    if not matched:
        conn.close()
        register_fail("patient")
        return jsonify({"error": "Login failed (name/code not found)"}), 401

    # ✅ SAFE migration (no crash if digest duplicates exist)
    new_hash = make_code_hash(code)
    new_digest = make_code_digest(code)

    try:
        cur.execute(
            "UPDATE users SET code_hash=?, code_digest=?, code=NULL WHERE id=?",
            (new_hash, new_digest, matched["id"])
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # digest conflict -> keep login working, store hash only
        cur.execute(
            "UPDATE users SET code_hash=?, code=NULL WHERE id=?",
            (new_hash, matched["id"])
        )
        conn.commit()

    conn.close()

    session.clear()
    session.permanent = True
    session["role"] = "patient"
    session["user_id"] = matched["id"]
    session["name"] = matched["name"]
    touch_session()
    clear_fails("patient")

    return jsonify({"message": "Patient login successful", "user_id": matched["id"], "name": matched["name"]})

# -------------------------
# CLINICIAN LOGIN (SAFE for NOT NULL code column)
# -------------------------
@app.route("/clinician-login", methods=["POST"])
def clinician_login():
    if is_locked("clinician"):
        return jsonify({"error": f"Too many attempts. Try again in {LOCK_SECONDS} seconds."}), 429

    data = request.json or {}
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    if not name or not code or len(code) != 6 or not code.isdigit():
        register_fail("clinician")
        return jsonify({"error": "Invalid login"}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, name, code_hash, code, code_digest FROM clinicians WHERE name=?", (name,))
    rows = cur.fetchall()

    if not rows:
        conn.close()
        register_fail("clinician")
        return jsonify({"error": "Clinician login failed"}), 401

    matched = None
    for row in rows:
        if row["code_hash"] and check_password_hash(row["code_hash"], code):
            matched = row
            break
        if row["code"] and str(row["code"]).strip() == code:
            matched = row
            break

    if not matched:
        conn.close()
        register_fail("clinician")
        return jsonify({"error": "Clinician login failed"}), 401

    # ✅ IMPORTANT: clinicians.code is NOT NULL in your DB -> DO NOT set code=NULL
    new_hash = make_code_hash(code)
    new_digest = make_code_digest(code)

    try:
        cur.execute(
            "UPDATE clinicians SET code_hash=?, code_digest=? WHERE id=?",
            (new_hash, new_digest, matched["id"])
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # digest conflict unlikely for clinicians, but keep safe
        cur.execute(
            "UPDATE clinicians SET code_hash=? WHERE id=?",
            (new_hash, matched["id"])
        )
        conn.commit()

    conn.close()

    session.clear()
    session.permanent = True
    session["role"] = "clinician"
    session["clinician_id"] = matched["id"]
    session["name"] = matched["name"]
    touch_session()
    clear_fails("clinician")

    return jsonify({"message": "Clinician login successful", "clinician_id": matched["id"], "name": matched["name"]})

# -------------------------
# Recommendation (PATIENT)
# -------------------------
@app.route("/recommend", methods=["POST"])
def recommend():
    if not is_patient():
        return jsonify({"error": "Not logged in as patient"}), 401

    try:
        data = request.json or {}
        user_id = int(session["user_id"])

        age = int(data.get("age"))
        weight = float(data.get("weight"))
        height = float(data.get("height"))
        activity = data.get("activity_level")
        diet = data.get("diet_preference")

        if activity not in ["Low", "High"]:
            return jsonify({"error": "Invalid activity level"}), 400
        if diet not in ["Vegetarian", "Non-Vegetarian"]:
            return jsonify({"error": "Invalid diet preference"}), 400

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET age=?, weight=?, height=?, activity=?, diet=?
            WHERE id=?
        """, (age, weight, height, activity, diet, user_id))

        rec = generate_adaptive_recommendations(
            user_id,
            {
                "age": age,
                "weight": weight,
                "height": height,
                "activity_level": activity,
                "diet_preference": diet
            },
            cur
        )

        cur.execute("""
            INSERT INTO recommendations (user_id, bmi, diet, exercise, general)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            rec["bmi"],
            ", ".join(rec["diet"]),
            ", ".join(rec["exercise"]),
            ", ".join(rec["general"])
        ))

        conn.commit()
        conn.close()

        return jsonify({"user_id": user_id, **rec})

    except Exception as e:
        print("❌ /recommend error:", e)
        return jsonify({"error": "Failed to get recommendation"}), 500

# -------------------------
# USER CHARTS (OWN DATA ONLY)
# -------------------------
@app.route("/user-charts/<int:user_id>")
def user_charts(user_id):
    if not is_patient():
        return jsonify({"error": "Not logged in"}), 401

    if int(session["user_id"]) != int(user_id):
        return jsonify({"error": "Forbidden"}), 403

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT bmi, diet, exercise, general
        FROM recommendations
        WHERE user_id = ?
        ORDER BY id
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    return jsonify({
        "bmi": [r["bmi"] for r in rows],
        "diet": sum([(r["diet"] or "").split(", ") for r in rows], []),
        "exercise": sum([(r["exercise"] or "").split(", ") for r in rows], []),
        "general": sum([(r["general"] or "").split(", ") for r in rows], []),
    })

# -------------------------
# FEEDBACK (PATIENT)
# -------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    if not is_patient():
        return jsonify({"error": "Not logged in as patient"}), 401

    data = request.json or {}
    score = data.get("score")
    try:
        score = int(score)
    except Exception:
        return jsonify({"error": "Invalid feedback"}), 400

    if score not in [1, 2, 3, 4, 5]:
        return jsonify({"error": "Invalid feedback"}), 400

    user_id = int(session["user_id"])

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (user_id, score) VALUES (?, ?)", (user_id, score))
    conn.commit()
    conn.close()

    return jsonify({"message": "Feedback saved"})

# -------------------------
# CLINICIAN DATA (Last 3)
# -------------------------
@app.route("/clinician-data")
def clinician_data():
    if not is_clinician():
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.name,
               r.bmi,
               r.diet,
               r.exercise,
               r.general,
               IFNULL((
                   SELECT AVG(score)
                   FROM feedback f
                   WHERE f.user_id = u.id
               ), 3) AS feedback
        FROM recommendations r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
        LIMIT 3
    """)
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        bmi = float(r["bmi"]) if r["bmi"] is not None else None
        fb = float(r["feedback"]) if r["feedback"] is not None else 3.0

        risks = []
        if bmi is not None:
            if bmi >= 30:
                risks.append("🔴 High BMI (High Risk)")
            elif bmi >= 25:
                risks.append("🟡 Needs Monitoring (Moderate Risk)")

        if fb <= 2:
            risks.append("⚠️ Low Feedback")

        explanation = (
            "Patient shows elevated risk indicators. Close monitoring advised."
            if risks else
            "Patient is stable with acceptable indicators. Continue current plan."
        )

        result.append({
            "name": r["name"],
            "bmi": bmi,
            "diet": (r["diet"] or "").split(", ") if r["diet"] else [],
            "exercise": (r["exercise"] or "").split(", ") if r["exercise"] else [],
            "general": (r["general"] or "").split(", ") if r["general"] else [],
            "feedback": round(fb, 1),
            "risks": risks,
            "ai_explanation": explanation
        })

    return jsonify(result)

# -------------------------
# EXPORT PDF (unchanged)
# -------------------------
@app.route("/export-pdf")
def export_pdf():
    if not is_clinician():
        return jsonify({"error": "Unauthorized"}), 401

    bmi_filter = request.args.get("bmi", "all")
    fb_filter = request.args.get("feedback", "all")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.name,
               r.bmi,
               IFNULL((
                   SELECT AVG(score)
                   FROM feedback f
                   WHERE f.user_id = u.id
               ), 3) AS feedback
        FROM recommendations r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
        LIMIT 3
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    def pass_bmi(b):
        b = float(b) if b is not None else 0
        if bmi_filter == "low": return b < 25
        if bmi_filter == "medium": return 25 <= b < 30
        if bmi_filter == "high": return b >= 30
        return True

    def pass_fb(f):
        f = float(f) if f is not None else 0
        if fb_filter == "low": return f < 3
        if fb_filter == "high": return f >= 4
        return True

    filtered = [r for r in rows if pass_bmi(r["bmi"]) and pass_fb(r["feedback"])]

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        return jsonify({"error": "reportlab not installed. Run: pip install reportlab"}), 500

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Clinician Report (Filtered - Last 3)")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"BMI Filter: {bmi_filter} | Feedback Filter: {fb_filter}")
    y -= 20

    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "Patient")
    c.drawString(210, y, "BMI")
    c.drawString(280, y, "Avg Feedback")
    c.drawString(390, y, "Risk")
    y -= 10
    c.line(50, y, width - 50, y)
    y -= 16

    c.setFont("Helvetica", 9)

    if not filtered:
        c.drawString(50, y, "No patients matched the selected filters.")
    else:
        for r in filtered:
            name = (r.get("name") or "Unknown").strip()
            bmi = float(r["bmi"]) if r.get("bmi") is not None else 0.0
            fb = float(r["feedback"]) if r.get("feedback") is not None else 0.0

            risks = []
            if bmi >= 30:
                risks.append("High BMI (High Risk)")
            elif bmi >= 25:
                risks.append("Needs Monitoring (Moderate Risk)")
            if fb <= 2:
                risks.append("Low Feedback")

            risk_text = " | ".join(risks) if risks else "None"

            c.drawString(50, y, name[:30])
            c.drawString(210, y, f"{bmi:.2f}")
            c.drawString(280, y, f"{fb:.1f}/5")
            c.drawString(390, y, risk_text[:35])

            y -= 18
            if y < 80:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica", 9)

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()

    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=clinician_report_last3.pdf"}
    )

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)