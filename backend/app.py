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
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# -------------------------
# Load env early
# -------------------------
load_dotenv()
print("SECRET_KEY loaded:", bool(os.environ.get("SECRET_KEY")))
print("CODE_PEPPER loaded:", bool(os.environ.get("CODE_PEPPER")))

# -------------------------
# App setup
# -------------------------
app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-later")

CORS(app, supports_credentials=True)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=20)

# -------------------------
# Email verification token signer
# -------------------------
serializer = URLSafeTimedSerializer(app.secret_key)
EMAIL_TOKEN_MAX_AGE_SECONDS = 15 * 60  # 15 minutes

# -------------------------
# Pre-auth expiry (NEW)
# -------------------------
PREAUTH_MAX_AGE_SECONDS = 10 * 60  # 10 minutes

# -------------------------
# Database path
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
# Code hashing helpers
# -------------------------
CODE_PEPPER = os.environ.get("CODE_PEPPER", "dev-pepper-change-me")

def make_code_digest(code: str) -> str:
    raw = (CODE_PEPPER + ":" + code).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def make_code_hash(code: str) -> str:
    return generate_password_hash(code)

# -------------------------
# Schema
# -------------------------
def ensure_schema():
    conn = get_conn()
    cur = conn.cursor()

    # USERS
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
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]

    if "code" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code TEXT")
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "code_hash" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code_hash TEXT")
    if "code_digest" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN code_digest TEXT")

    # patient identity + email verification
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "title" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN title TEXT")
    if "first_name" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    if "surname" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN surname TEXT")
    if "email" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "email_verified" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")

    # indexes
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code ON users(code)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code_digest ON users(code_digest)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

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

    # CLINICIANS (keep code NOT NULL)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE
        )
    """)

    # clinician hashed code columns
    cur.execute("PRAGMA table_info(clinicians)")
    ccols = [r["name"] for r in cur.fetchall()]
    if "code_hash" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN code_hash TEXT")
    if "code_digest" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN code_digest TEXT")

    # clinician identity + email verification
    cur.execute("PRAGMA table_info(clinicians)")
    ccols = [r["name"] for r in cur.fetchall()]
    if "title" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN title TEXT")
    if "first_name" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN first_name TEXT")
    if "surname" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN surname TEXT")
    if "email" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN email TEXT")
    if "email_verified" not in ccols:
        cur.execute("ALTER TABLE clinicians ADD COLUMN email_verified INTEGER DEFAULT 0")

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicians_code_digest ON clinicians(code_digest)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicians_email ON clinicians(email)")

    conn.commit()
    conn.close()

ensure_schema()

# -------------------------
# Security helpers
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
# Pre-auth (email verified gate)
# -------------------------
def set_preauth(role: str, target_id: int):
    session["preauth_role"] = role
    session["preauth_id"] = int(target_id)
    session["preauth_at"] = time.time()

def clear_preauth():
    session.pop("preauth_role", None)
    session.pop("preauth_id", None)
    session.pop("preauth_at", None)

# ✅ UPDATED: expires preauth after PREAUTH_MAX_AGE_SECONDS
def preauth_ok(role: str, target_id: int) -> bool:
    if session.get("preauth_role") != role:
        return False
    if int(session.get("preauth_id") or 0) != int(target_id):
        return False

    at = float(session.get("preauth_at") or 0)
    if at <= 0:
        return False

    if time.time() - at > PREAUTH_MAX_AGE_SECONDS:
        clear_preauth()
        return False

    return True

@app.route("/preauth-status", methods=["GET"])
def preauth_status():
    return jsonify({
        "preauth_role": session.get("preauth_role"),
        "preauth_id": session.get("preauth_id"),
    })

# -------------------------
# Serve frontend
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

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

# ==========================================================
# PATIENT EMAIL VERIFICATION (terminal link)
# ==========================================================
@app.route("/patient-start-verify", methods=["POST"])
def patient_start_verify():
    data = request.json or {}
    title = (data.get("title") or "").strip()
    first = (data.get("first_name") or "").strip()
    surname = (data.get("surname") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not title or not first or not surname or not email or "@" not in email:
        return jsonify({"error": "Enter title, first name, surname, and a valid email."}), 400

    full_name = f"{title} {first} {surname}".strip()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    row = cur.fetchone()

    if row:
        user_id = int(row["id"])
        cur.execute(
            "UPDATE users SET title=?, first_name=?, surname=?, name=?, email_verified=0 WHERE id=?",
            (title, first, surname, full_name, user_id)
        )
    else:
        # link old record with same name and no email
        cur.execute("""
            SELECT id FROM users
            WHERE (email IS NULL OR TRIM(email)='')
              AND name=?
            ORDER BY id DESC
            LIMIT 1
        """, (full_name,))
        legacy = cur.fetchone()

        if legacy:
            user_id = int(legacy["id"])
            cur.execute(
                "UPDATE users SET title=?, first_name=?, surname=?, email=?, email_verified=0 WHERE id=?",
                (title, first, surname, email, user_id)
            )
        else:
            try:
                cur.execute(
                    "INSERT INTO users (title, first_name, surname, name, email, email_verified) VALUES (?, ?, ?, ?, ?, 0)",
                    (title, first, surname, full_name, email)
                )
                user_id = cur.lastrowid
            except sqlite3.IntegrityError:
                conn.close()
                return jsonify({"error": "Email already registered."}), 409

    conn.commit()
    conn.close()

    token = serializer.dumps({"user_id": int(user_id), "email": email}, salt="patient-email-verify")
    link = f"http://127.0.0.1:5000/patient-verify?token={token}"

    print("\n✅ PATIENT VERIFICATION LINK (open on SAME PC browser):")
    print(link)
    print()

    return jsonify({"message": "Verification link generated. Check terminal and open it."})

@app.route("/patient-verify", methods=["GET"])
def patient_verify():
    token = (request.args.get("token") or "").strip()
    if not token:
        return "Missing token", 400

    try:
        payload = serializer.loads(token, salt="patient-email-verify", max_age=EMAIL_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return "Link expired. Generate a new one.", 400
    except BadSignature:
        return "Invalid link.", 400

    user_id = int(payload.get("user_id"))
    email = (payload.get("email") or "").strip().lower()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id=? AND email=?", (user_id, email))
    row = cur.fetchone()
    if not row:
        conn.close()
        return "User not found.", 404

    cur.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    # preauth only (not full login yet)
    set_preauth("patient", user_id)
    return send_from_directory(app.static_folder, "login.html")

# ==========================================================
# CLINICIAN EMAIL VERIFICATION (terminal link)
# (requires clinician exists + code matches)
# ==========================================================
@app.route("/clinician-start-verify", methods=["POST"])
def clinician_start_verify():
    data = request.json or {}
    title = (data.get("title") or "").strip()
    first = (data.get("first_name") or "").strip()
    surname = (data.get("surname") or "").strip()
    code = (data.get("code") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not title or not first or not surname:
        return jsonify({"error": "Enter title, first name, and surname."}), 400
    if not code or not (len(code) == 6 and code.isdigit()):
        return jsonify({"error": "Enter a valid 6-digit clinician code."}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Enter a valid email."}), 400

    full_name = f"{title} {first} {surname}".strip()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, name, code, code_hash FROM clinicians WHERE name=?", (full_name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Clinician not found. Create them first in DB."}), 404

    # verify code matches (supports plaintext or hashed)
    ok = False
    if row["code_hash"]:
        ok = check_password_hash(row["code_hash"], code)
    else:
        ok = str(row["code"]).strip() == code

    if not ok:
        conn.close()
        return jsonify({"error": "Clinician code incorrect."}), 401

    clinician_id = int(row["id"])

    # store identity + email, reset verified=0
    try:
        cur.execute("""
            UPDATE clinicians
            SET title=?, first_name=?, surname=?, email=?, email_verified=0
            WHERE id=?
        """, (title, first, surname, email, clinician_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "That email is already used by another clinician."}), 409

    conn.close()

    token = serializer.dumps({"clinician_id": clinician_id, "email": email}, salt="clinician-email-verify")
    link = f"http://127.0.0.1:5000/clinician-verify?token={token}"

    print("\n✅ CLINICIAN VERIFICATION LINK (open on SAME PC browser):")
    print(link)
    print()

    return jsonify({"message": "Verification link generated. Check terminal and open it."})

@app.route("/clinician-verify", methods=["GET"])
def clinician_verify():
    token = (request.args.get("token") or "").strip()
    if not token:
        return "Missing token", 400

    try:
        payload = serializer.loads(token, salt="clinician-email-verify", max_age=EMAIL_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return "Link expired. Generate a new one.", 400
    except BadSignature:
        return "Invalid link.", 400

    clinician_id = int(payload.get("clinician_id"))
    email = (payload.get("email") or "").strip().lower()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM clinicians WHERE id=? AND email=?", (clinician_id, email))
    row = cur.fetchone()
    if not row:
        conn.close()
        return "Clinician not found.", 404

    cur.execute("UPDATE clinicians SET email_verified=1 WHERE id=?", (clinician_id,))
    conn.commit()
    conn.close()

    set_preauth("clinician", clinician_id)
    return send_from_directory(app.static_folder, "clinician_login.html")

# ==========================================================
# PATIENT REGISTER (code) - REQUIRES patient verified link first
# ==========================================================
@app.route("/patient-register", methods=["POST"])
def patient_register():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    if not name or not code or len(code) != 6 or not code.isdigit():
        return jsonify({"error": "Please enter full name + 6-digit code"}), 400

    pre_id = int(session.get("preauth_id") or 0)
    if session.get("preauth_role") != "patient" or pre_id <= 0:
        return jsonify({"error": "Please verify your email first (generate link + open it)."}), 403

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, name, email_verified FROM users WHERE id=?", (pre_id,))
    u = cur.fetchone()
    if not u:
        conn.close()
        return jsonify({"error": "Verified user not found. Verify again."}), 403
    if int(u["email_verified"] or 0) != 1:
        conn.close()
        return jsonify({"error": "Email not verified. Verify again."}), 403

    if str(u["name"] or "").strip() != name:
        conn.close()
        return jsonify({"error": "Name does not match the verified user. Verify again."}), 403

    code_digest = make_code_digest(code)

    cur.execute("SELECT id FROM users WHERE code_digest=? AND id<>?", (code_digest, pre_id))
    exists = cur.fetchone()
    if exists:
        conn.close()
        return jsonify({"error": "This code is already used. Choose another 6-digit code."}), 409

    code_hash = make_code_hash(code)

    try:
        cur.execute(
            "UPDATE users SET code=NULL, code_hash=?, code_digest=? WHERE id=?",
            (code_hash, code_digest, pre_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Could not save code. Try another code."}), 409

    conn.close()

    session.clear()
    session.permanent = True
    session["role"] = "patient"
    session["user_id"] = pre_id
    session["name"] = name
    touch_session()
    clear_fails("patient")
    clear_preauth()

    return jsonify({"message": "Registered & logged in", "user_id": pre_id, "name": name})

# ==========================================================
# PATIENT LOGIN (code) - REQUIRES patient verified link first
# ==========================================================
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

    cur.execute("SELECT id, name, code_hash, code, code_digest, email_verified FROM users WHERE name=?", (name,))
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

    if int(matched["email_verified"] or 0) != 1:
        conn.close()
        return jsonify({"error": "Email not verified. Generate link and verify first."}), 403

    if not preauth_ok("patient", int(matched["id"])):
        conn.close()
        return jsonify({"error": "Please verify your email first (generate link + open it)."}), 403

    # safe upgrade
    new_hash = make_code_hash(code)
    new_digest = make_code_digest(code)
    try:
        cur.execute(
            "UPDATE users SET code_hash=?, code_digest=?, code=NULL WHERE id=?",
            (new_hash, new_digest, matched["id"])
        )
        conn.commit()
    except sqlite3.IntegrityError:
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
    clear_preauth()

    return jsonify({"message": "Patient login successful", "user_id": matched["id"], "name": matched["name"]})

# ==========================================================
# CLINICIAN LOGIN (code) - REQUIRES clinician verified link first
# ==========================================================
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

    cur.execute("SELECT id, name, code_hash, code, email_verified FROM clinicians WHERE name=?", (name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        register_fail("clinician")
        return jsonify({"error": "Clinician login failed"}), 401

    ok = False
    if row["code_hash"]:
        ok = check_password_hash(row["code_hash"], code)
    else:
        ok = str(row["code"]).strip() == code

    if not ok:
        conn.close()
        register_fail("clinician")
        return jsonify({"error": "Clinician login failed"}), 401

    if int(row["email_verified"] or 0) != 1:
        conn.close()
        return jsonify({"error": "Email not verified. Generate link and verify first."}), 403

    if not preauth_ok("clinician", int(row["id"])):
        conn.close()
        return jsonify({"error": "Please verify your email first (generate link + open it)."}), 403

    # upgrade hash/digest, but do NOT null code (NOT NULL)
    new_hash = make_code_hash(code)
    new_digest = make_code_digest(code)
    try:
        cur.execute(
            "UPDATE clinicians SET code_hash=?, code_digest=? WHERE id=?",
            (new_hash, new_digest, row["id"])
        )
        conn.commit()
    except sqlite3.IntegrityError:
        cur.execute(
            "UPDATE clinicians SET code_hash=? WHERE id=?",
            (new_hash, row["id"])
        )
        conn.commit()

    conn.close()

    session.clear()
    session.permanent = True
    session["role"] = "clinician"
    session["clinician_id"] = row["id"]
    session["name"] = row["name"]
    touch_session()
    clear_fails("clinician")
    clear_preauth()

    return jsonify({"message": "Clinician login successful", "clinician_id": row["id"], "name": row["name"]})

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
# USER CHARTS
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
# FEEDBACK
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
# EXPORT PDF
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
