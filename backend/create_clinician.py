import os
import sqlite3
import hashlib
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Load .env from project root (../.env)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

# ---- clinician details to create/update ----
name = "Dr Admin"
code = "123456"  # must be 6 digits

# ---- same pepper logic as app.py ----
CODE_PEPPER = os.environ.get("CODE_PEPPER")
if not CODE_PEPPER:
    raise SystemExit("❌ CODE_PEPPER not loaded. Check your .env file.")

def make_code_digest(code_str: str) -> str:
    raw = (CODE_PEPPER + ":" + code_str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

if not (len(code) == 6 and code.isdigit()):
    raise SystemExit("❌ Clinician code must be exactly 6 digits.")

code_hash = generate_password_hash(code)
code_digest = make_code_digest(code)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Ensure clinicians table exists (keep old structure if already there)
cur.execute("""
CREATE TABLE IF NOT EXISTS clinicians (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  code TEXT
)
""")

# Ensure required columns exist
cur.execute("PRAGMA table_info(clinicians)")
cols = [c[1] for c in cur.fetchall()]

if "code" not in cols:
    cur.execute("ALTER TABLE clinicians ADD COLUMN code TEXT")
    print("✅ Added code column")

if "code_hash" not in cols:
    cur.execute("ALTER TABLE clinicians ADD COLUMN code_hash TEXT")
    print("✅ Added code_hash column")

if "code_digest" not in cols:
    cur.execute("ALTER TABLE clinicians ADD COLUMN code_digest TEXT")
    print("✅ Added code_digest column")

# Create unique index on digest (safe even if duplicates already exist)
cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicians_code_digest
ON clinicians(code_digest)
""")

# Check existing clinician by name
cur.execute("SELECT id FROM clinicians WHERE name = ?", (name,))
row = cur.fetchone()

if row:
    clinician_id = row[0]
    # Update existing clinician
    cur.execute("""
        UPDATE clinicians
        SET code=?, code_hash=?, code_digest=?
        WHERE id=?
    """, (code, code_hash, code_digest, clinician_id))
    conn.commit()
    print(f"✅ Updated existing clinician: {name}")
else:
    # Insert new clinician
    cur.execute("""
        INSERT INTO clinicians (name, code, code_hash, code_digest)
        VALUES (?, ?, ?, ?)
    """, (name, code, code_hash, code_digest))
    conn.commit()
    print(f"✅ Created clinician: {name}")

conn.close()

print("👉 Now restart Flask:  python backend/app.py")
print("👉 Login with:", name, "/", code)
