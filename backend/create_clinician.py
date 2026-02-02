import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

name = "Dr Admin"
code = "123456"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS clinicians (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  code TEXT UNIQUE NOT NULL
)
""")

try:
  cur.execute("INSERT INTO clinicians (name, code) VALUES (?, ?)", (name, code))
  conn.commit()
  print("✅ Clinician created:", (name, code))
except sqlite3.IntegrityError:
  print("⚠️ Clinician already exists or code already used.")

conn.close()
