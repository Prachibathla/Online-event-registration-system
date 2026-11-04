"""Run once to populate sample events."""
from database import get_db, init_db
from werkzeug.security import generate_password_hash

init_db()

db = get_db()

# Seed admin
existing = db.execute("SELECT id FROM admin LIMIT 1").fetchone()
if not existing:
    db.execute(
        "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
        ("admin", generate_password_hash("admin123")),
    )

# Seed events
sample_events = [
    ("Tech Fest 2026",
     "Annual college technical festival with competitions and workshops.",
     "2026-11-15", "Main Auditorium", 100, "2026-11-10"),
    ("Hackathon 2026",
     "24-hour coding hackathon. Form teams of 3 to 4.",
     "2026-12-05", "CS Lab Block", 60, "2026-11-30"),
    ("Cultural Night 2026",
     "Music, dance, drama and more – a celebration of talent.",
     "2026-11-20", "Open Air Theatre", 200, None),
]

for ev in sample_events:
    existing = db.execute(
        "SELECT id FROM events WHERE title = ?", (ev[0],)
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO events (title, description, event_date, venue, max_seats, deadline) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ev,
        )

db.commit()

events = db.execute("SELECT id, title, event_date FROM events").fetchall()
for e in events:
    print(f"  Event {e['id']}: {e['title']} ({e['event_date']})")

db.close()
print("Seed complete.")
