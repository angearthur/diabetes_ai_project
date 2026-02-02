import sqlite3

DB_NAME = "database.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# -------------------------
# Users table (Patients + Clinicians)
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('patient', 'clinician')),
    age INTEGER,
    weight REAL,
    height REAL,
    activity TEXT,
    diet TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# -------------------------
# Recommendations table
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    bmi REAL,
    diet TEXT,
    exercise TEXT,
    general TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")

# -------------------------
# Feedback table
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    recommendation_id INTEGER,
    score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
)
""")

conn.commit()
conn.close()

print("✅ database.db created/updated successfully!")
print("➡️ Next: create clinician accounts inside app.py (see comments) or insert manually.")
