import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "events.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db():
    """Open a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables from schema.sql if they don't exist."""
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def seed_admin(username: str, password_hash: str):
    """Insert the default admin account if none exists."""
    conn = get_db()
    existing = conn.execute("SELECT id FROM admin LIMIT 1").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
    conn.close()
