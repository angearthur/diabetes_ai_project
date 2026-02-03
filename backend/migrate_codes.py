import os
import sqlite3
import hashlib
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# -------------------------
# Load .env
# -------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(ROOT, ".env")
load_dotenv(ENV_PATH)

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

CODE_PEPPER = os.environ.get("CODE_PEPPER")
if not CODE_PEPPER:
    raise SystemExit("❌ CODE_PEPPER not loaded. Check your .env file.")

def make_code_digest(code: str) -> str:
    raw = (CODE_PEPPER + ":" + code).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def looks_like_hash(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("scrypt:") or s.startswith("pbkdf2:")

def ensure_cols(cur, table_name: str):
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = [r[1] for r in cur.fetchall()]

    if "code_hash" not in cols:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN code_hash TEXT")
        print(f"✅ Added code_hash to {table_name}")

    if "code_digest" not in cols:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN code_digest TEXT")
        print(f"✅ Added code_digest to {table_name}")

def migrate_table(table_name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ensure_cols(cur, table_name)

    cur.execute(f"SELECT id, code, code_hash FROM {table_name}")
    rows = cur.fetchall()

    migrated = 0
    repaired = 0
    skipped = 0
    digest_conflicts = 0

    for row_id, code, code_hash in rows:
        code_str = ("" if code is None else str(code)).strip()
        code_hash_str = ("" if code_hash is None else str(code_hash)).strip()

        # CASE A: hash mistakenly stored in code column
        if code_hash_str == "" and looks_like_hash(code_str):
            try:
                cur.execute(
                    f"UPDATE {table_name} SET code_hash=?, code=NULL WHERE id=?",
                    (code_str, row_id)
                )
                repaired += 1
            except sqlite3.IntegrityError:
                skipped += 1
            continue

        # CASE B: plaintext 6-digit code → hash + digest
        if code_hash_str == "" and len(code_str) == 6 and code_str.isdigit():
            new_hash = generate_password_hash(code_str)
            new_digest = make_code_digest(code_str)

            try:
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET code_hash=?, code_digest=?, code=NULL
                    WHERE id=?
                    """,
                    (new_hash, new_digest, row_id)
                )
                migrated += 1

            except sqlite3.IntegrityError:
                # Digest conflict → keep hash only
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET code_hash=?, code=NULL
                    WHERE id=?
                    """,
                    (new_hash, row_id)
                )
                digest_conflicts += 1

            continue

        # CASE C: already OK
        if code_hash_str:
            continue

        skipped += 1

    conn.commit()
    conn.close()

    print(f"✅ {table_name}: migrated {migrated} row(s)")
    print(f"🔧 {table_name}: repaired {repaired} row(s)")
    if digest_conflicts:
        print(f"⚠️ {table_name}: {digest_conflicts} digest conflict(s) (hash-only)")
    if skipped:
        print(f"⚠️ {table_name}: skipped {skipped} row(s)")

if __name__ == "__main__":
    print("✅ ENV PATH:", ENV_PATH)
    print("✅ CODE_PEPPER loaded:", bool(CODE_PEPPER))
    print("✅ USING DB:", DB_PATH)

    migrate_table("users")
    migrate_table("clinicians")

    print("\n✅ Migration done.")
    print("👉 Restart Flask: python backend/app.py")