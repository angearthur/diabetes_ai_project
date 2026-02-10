import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

print("Using DB:", DB_PATH)
print("Exists:", os.path.exists(DB_PATH))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    SELECT id, name, email, email_verified, code, code_hash
    FROM users
    ORDER BY id DESC
    LIMIT 10
""")

rows = cur.fetchall()

print("\nLast 10 users:")
for r in rows:
    print(r)

conn.close()
