import sqlite3

# Where we want the database to live (alongside your app.py)
db_path = 'leaderboard.db'

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    score INTEGER,
    timestamp DATETIME
)
""")
conn.commit()
conn.close()

print(f"✅ SQLite leaderboard database created at: {db_path}")
