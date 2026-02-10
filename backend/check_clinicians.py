import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT id, name, code FROM clinicians")
rows = cur.fetchall()

print("Clinicians:")
for r in rows:
    print(r)

conn.close()
