import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.execute("SELECT id, name, code FROM users ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()

print("Last 10 users:")
for r in rows:
    print(r)

conn.close()
