import os
import sqlite3
import hashlib
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Load .env from project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

OLD_NAME = "Dr Admin"
NEW_TITLE = "Dr"
NEW_FIRST = "Arthur"
NEW_SURNAME = "Stanley"
NEW_CODE = "789456"  # must be 6 digits

CODE_PEPPER = os.environ.get("CODE_PEPPER")
if not CODE_PEPPER:
    raise SystemExit("❌ CODE_PEPPER not loaded. Check your .env file.")

def make_code_digest(code_str: str) -> str:
    raw = (CODE_PEPPER + ":" + code_str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

if not (len(NEW_CODE) == 6 and NEW_CODE.isdigit()):
    raise SystemExit("❌ NEW_CODE must be exactly 6 digits.")

new_name = f"{NEW_TITLE} {NEW_FIRST} {NEW_SURNAME}".strip()
new_hash = generate_password_hash(NEW_CODE)
new_digest = make_code_digest(NEW_CODE)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# confirm columns exist
cur.execute("PRAGMA table_info(clinicians)")
cols = [c[1] for c in cur.fetchall()]

need_cols = ["title", "first_name", "surname", "email", "email_verified", "code_hash", "code_digest"]
for col in need_cols:
    if col not in cols:
        if col == "email_verified":
            cur.execute("ALTER TABLE clinicians ADD COLUMN email_verified INTEGER DEFAULT 0")
        else:
            cur.execute(f"ALTER TABLE clinicians ADD COLUMN {col} TEXT")
        print(f"✅ Added column: {col}")

# find existing clinician by old name
cur.execute("SELECT id FROM clinicians WHERE name=?", (OLD_NAME,))
row = cur.fetchone()
if not row:
    conn.close()
    raise SystemExit(f"❌ Could not find clinician with name '{OLD_NAME}' in DB.")

clinician_id = row[0]

# update name + code + hashes
cur.execute("""
    UPDATE clinicians
    SET name=?, title=?, first_name=?, surname=?,
        code=?, code_hash=?, code_digest=?, email_verified=0
    WHERE id=?
""", (new_name, NEW_TITLE, NEW_FIRST, NEW_SURNAME, NEW_CODE, new_hash, new_digest, clinician_id))

conn.commit()
conn.close()

print("✅ Clinician updated successfully.")
print("👉 New login:")
print("   Title:", NEW_TITLE)
print("   First:", NEW_FIRST)
print("   Surname:", NEW_SURNAME)
print("   Code:", NEW_CODE)
