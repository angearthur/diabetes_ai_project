import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS patient_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    code TEXT NOT NULL,
    UNIQUE(full_name, code)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS clinicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    UNIQUE(name, code)
)
""")

conn.commit()
conn.close()
print("✅ Auth tables ready!")
