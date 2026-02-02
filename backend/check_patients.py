import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    SELECT id, name, code
    FROM users
    WHERE code IS NOT NULL
    ORDER BY id DESC
""")

print("Registered patients:")
for row in cur.fetchall():
    print(row)

conn.close()
