import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("🔧 Fixing clinicians table (making code nullable)...")

# 1. Rename old table
cur.execute("ALTER TABLE clinicians RENAME TO clinicians_old")

# 2. Recreate table with code NULLABLE
cur.execute("""
CREATE TABLE clinicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    code_hash TEXT,
    code_digest TEXT
)
""")

# 3. Copy data across
cur.execute("""
INSERT INTO clinicians (id, name, code, code_hash, code_digest)
SELECT id, name, code, code_hash, code_digest
FROM clinicians_old
""")

# 4. Drop old table
cur.execute("DROP TABLE clinicians_old")

# 5. Recreate index
cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinicians_code_digest
ON clinicians(code_digest)
""")

conn.commit()
conn.close()

print("✅ clinicians table fixed successfully.")
print("👉 Now restart Flask: python backend/app.py")



