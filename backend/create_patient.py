import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

name = "John Smith"
code = "654321"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Ensure code column exists (safe)
cur.execute("PRAGMA table_info(users)")
cols = [c[1] for c in cur.fetchall()]
if "code" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN code TEXT")

# Insert patient
cur.execute("""
    INSERT INTO users (name, code)
    VALUES (?, ?)
""", (name, code))

conn.commit()
conn.close()

print("✅ Patient created:", (name, code))
