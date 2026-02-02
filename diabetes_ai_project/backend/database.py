import sqlite3

# Connect to (or create) the database
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# -------------------------
# Users table
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    age INTEGER,
    weight REAL,
    height REAL,
    activity TEXT,
    diet TEXT
)
""")

# -------------------------
# Recommendations table
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bmi REAL,
    diet TEXT,
    exercise TEXT,
    general TEXT
)
""")

# -------------------------
# Feedback table
# -------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    score INTEGER
)
""")

# Commit changes and close
conn.commit()
conn.close()

print("✅ Database created/reset successfully!")
