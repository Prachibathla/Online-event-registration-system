import csv
import io
import re
import random
import string
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    Response,
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db, seed_admin

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.context_processor
def inject_now():
    return {"now": datetime.now()}
app.secret_key = "change-this-before-deployment-use-a-long-random-string"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_reg_code(event_id: int) -> str:
    """Return a unique-enough registration code like EVT-2026-A3F9."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"EVT-{event_id}-{suffix}"


def seats_left(event) -> int:
    db = get_db()
    filled = db.execute(
        "SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event["id"],)
    ).fetchone()[0]
    db.close()
    return event["max_seats"] - filled


def registration_open(event):
    """Return (is_open, reason_if_closed)."""
    today = date.today().isoformat()
    if event["deadline"] and today > event["deadline"]:
        return False, "Registration deadline has passed."
    if seats_left(event) <= 0:
        return False, "No seats available for this event."
    return True, ""


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$", email))


def validate_phone(phone: str) -> bool:
    return bool(re.match(r"^\+?[\d\s\-]{7,15}$", phone))


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    events = db.execute(
        "SELECT * FROM events ORDER BY event_date ASC"
    ).fetchall()
    db.close()

    today = date.today().isoformat()
    enriched = []
    for e in events:
        sl = seats_left(e)
        is_open = sl > 0 and (not e["deadline"] or today <= e["deadline"])
        enriched.append({"event": e, "seats_left": sl, "is_open": is_open})

    return render_template("index.html", enriched=enriched, today=today)


@app.route("/event/<int:event_id>")
def event_detail(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    db.close()
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("index"))

    sl = seats_left(event)
    is_open, reason = registration_open(event)
    return render_template(
        "event_detail.html", event=event, seats_left=sl, is_open=is_open, reason=reason
    )


@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("index"))

    is_open, reason = registration_open(event)
    if not is_open:
        flash(reason, "danger")
        return redirect(url_for("event_detail", event_id=event_id))

    errors = []
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        college = request.form.get("college", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("year", "").strip()

        # Server-side validation
        if not name:
            errors.append("Full name is required.")
        if not email or not validate_email(email):
            errors.append("A valid email address is required.")
        if not phone or not validate_phone(phone):
            errors.append("A valid phone number is required.")

        if not errors:
            reg_code = generate_reg_code(event_id)
            try:
                db.execute(
                    "INSERT INTO registrations "
                    "(reg_code, event_id, name, email, phone, college, department, year) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (reg_code, event_id, name, email, phone, college, department, year),
                )
                db.commit()
                db.close()
                return redirect(url_for("success", reg_code=reg_code))
            except Exception as exc:
                db.rollback()
                if "UNIQUE" in str(exc):
                    errors.append(
                        "You are already registered for this event with this email."
                    )
                else:
                    errors.append("An unexpected error occurred. Please try again.")

    db.close()
    return render_template(
        "register.html", event=event, errors=errors, form=request.form
    )


@app.route("/success/<reg_code>")
def success(reg_code):
    db = get_db()
    reg = db.execute(
        "SELECT r.*, e.title AS event_title, e.event_date, e.venue "
        "FROM registrations r JOIN events e ON r.event_id = e.id "
        "WHERE r.reg_code = ?",
        (reg_code,),
    ).fetchone()
    db.close()
    if not reg:
        flash("Registration not found.", "danger")
        return redirect(url_for("index"))
    return render_template("success.html", reg=reg)


@app.route("/my-registration", methods=["GET", "POST"])
def my_registration():
    reg = None
    event = None
    errors = []
    if request.method == "POST":
        action = request.form.get("action")
        reg_code = request.form.get("reg_code", "").strip().upper()
        email = request.form.get("email", "").strip().lower()

        db = get_db()
        reg = db.execute(
            "SELECT r.*, e.title AS event_title, e.event_date, e.venue "
            "FROM registrations r JOIN events e ON r.event_id = e.id "
            "WHERE r.reg_code = ? AND r.email = ?",
            (reg_code, email),
        ).fetchone()

        if not reg:
            errors.append("No registration found with that ID and email.")
        elif action == "update":
            # Re-render the edit form
            pass
        elif action == "save":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            college = request.form.get("college", "").strip()
            department = request.form.get("department", "").strip()
            year = request.form.get("year", "").strip()

            if not name:
                errors.append("Name is required.")
            if not phone or not validate_phone(phone):
                errors.append("Valid phone number required.")

            if not errors:
                db.execute(
                    "UPDATE registrations SET name=?, phone=?, college=?, department=?, year=? "
                    "WHERE reg_code=? AND email=?",
                    (name, phone, college, department, year, reg_code, email),
                )
                db.commit()
                flash("Your registration has been updated.", "success")
                reg = db.execute(
                    "SELECT r.*, e.title AS event_title, e.event_date, e.venue "
                    "FROM registrations r JOIN events e ON r.event_id = e.id "
                    "WHERE r.reg_code = ? AND r.email = ?",
                    (reg_code, email),
                ).fetchone()
        db.close()

    return render_template(
        "lookup.html",
        reg=reg,
        errors=errors,
        form=request.form,
        editing=(request.form.get("action") in ("update", "save") and reg is not None and not errors),
    )


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        admin = db.execute(
            "SELECT * FROM admin WHERE username = ?", (username,)
        ).fetchone()
        db.close()

        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid username or password."

    return render_template("admin/login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    db = get_db()
    total_events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_regs = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    total_seats = db.execute("SELECT SUM(max_seats) FROM events").fetchone()[0] or 0
    recent_regs = db.execute(
        "SELECT r.reg_code, r.name, r.email, e.title AS event_title, r.registered_at "
        "FROM registrations r JOIN events e ON r.event_id = e.id "
        "ORDER BY r.registered_at DESC LIMIT 5"
    ).fetchall()
    upcoming_events = db.execute(
        "SELECT e.*, "
        "(SELECT COUNT(*) FROM registrations WHERE event_id = e.id) AS filled "
        "FROM events e WHERE e.event_date >= ? ORDER BY e.event_date ASC LIMIT 5",
        (date.today().isoformat(),),
    ).fetchall()
    db.close()

    return render_template(
        "admin/dashboard.html",
        total_events=total_events,
        total_regs=total_regs,
        total_seats=total_seats,
        recent_regs=recent_regs,
        upcoming_events=upcoming_events,
    )


@app.route("/admin/events", methods=["GET", "POST"])
@login_required
def admin_events():
    db = get_db()
    errors = []

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            event_date = request.form.get("event_date", "").strip()
            venue = request.form.get("venue", "").strip()
            max_seats = request.form.get("max_seats", "").strip()
            deadline = request.form.get("deadline", "").strip()

            if not title:
                errors.append("Event title is required.")
            if not event_date:
                errors.append("Event date is required.")
            if not max_seats or not max_seats.isdigit() or int(max_seats) < 1:
                errors.append("Max seats must be a positive number.")

            if not errors:
                db.execute(
                    "INSERT INTO events (title, description, event_date, venue, max_seats, deadline) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (title, description, event_date, venue, int(max_seats), deadline or None),
                )
                db.commit()
                flash("Event added successfully.", "success")
                db.close()
                return redirect(url_for("admin_events"))

        elif action == "delete":
            event_id = request.form.get("event_id")
            db.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
            db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            db.commit()
            flash("Event and its registrations have been deleted.", "success")
            db.close()
            return redirect(url_for("admin_events"))

        elif action == "edit_save":
            event_id = request.form.get("event_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            event_date = request.form.get("event_date", "").strip()
            venue = request.form.get("venue", "").strip()
            max_seats = request.form.get("max_seats", "").strip()
            deadline = request.form.get("deadline", "").strip()

            if not title or not event_date or not max_seats.isdigit():
                errors.append("Title, date, and valid max seats are required.")
            else:
                db.execute(
                    "UPDATE events SET title=?, description=?, event_date=?, venue=?, max_seats=?, deadline=? "
                    "WHERE id=?",
                    (title, description, event_date, venue, int(max_seats), deadline or None, event_id),
                )
                db.commit()
                flash("Event updated.", "success")
                db.close()
                return redirect(url_for("admin_events"))

    editing_id = request.args.get("edit")
    editing_event = None
    if editing_id:
        editing_event = db.execute(
            "SELECT * FROM events WHERE id = ?", (editing_id,)
        ).fetchone()

    events = db.execute(
        "SELECT e.*, "
        "(SELECT COUNT(*) FROM registrations WHERE event_id = e.id) AS filled "
        "FROM events e ORDER BY e.event_date DESC"
    ).fetchall()
    db.close()

    return render_template(
        "admin/events.html",
        events=events,
        errors=errors,
        editing_event=editing_event,
        form=request.form,
    )


@app.route("/admin/registrations")
@login_required
def admin_registrations():
    q = request.args.get("q", "").strip()
    event_filter = request.args.get("event_id", "")
    db = get_db()

    base_query = (
        "SELECT r.*, e.title AS event_title "
        "FROM registrations r JOIN events e ON r.event_id = e.id "
    )
    conditions = []
    params = []

    if q:
        conditions.append(
            "(r.name LIKE ? OR r.email LIKE ? OR r.college LIKE ? OR r.reg_code LIKE ?)"
        )
        params.extend([f"%{q}%"] * 4)

    if event_filter:
        conditions.append("r.event_id = ?")
        params.append(event_filter)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    base_query += " ORDER BY r.registered_at DESC"

    rows = db.execute(base_query, params).fetchall()
    all_events = db.execute("SELECT id, title FROM events ORDER BY title").fetchall()
    db.close()

    return render_template(
        "admin/registrations.html",
        rows=rows,
        q=q,
        event_filter=event_filter,
        all_events=all_events,
    )


@app.route("/admin/edit/<int:reg_id>", methods=["GET", "POST"])
@login_required
def admin_edit(reg_id):
    db = get_db()
    reg = db.execute(
        "SELECT r.*, e.title AS event_title FROM registrations r "
        "JOIN events e ON r.event_id = e.id WHERE r.id = ?",
        (reg_id,),
    ).fetchone()

    if not reg:
        flash("Registration not found.", "danger")
        db.close()
        return redirect(url_for("admin_registrations"))

    errors = []
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        college = request.form.get("college", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("year", "").strip()

        if not name:
            errors.append("Name is required.")
        if not phone or not validate_phone(phone):
            errors.append("Valid phone number required.")

        if not errors:
            db.execute(
                "UPDATE registrations SET name=?, phone=?, college=?, department=?, year=? "
                "WHERE id=?",
                (name, phone, college, department, year, reg_id),
            )
            db.commit()
            db.close()
            flash("Registration updated successfully.", "success")
            return redirect(url_for("admin_registrations"))

    db.close()
    return render_template("admin/edit.html", reg=reg, errors=errors, form=request.form)


@app.route("/admin/delete/<int:reg_id>", methods=["POST"])
@login_required
def admin_delete(reg_id):
    db = get_db()
    db.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
    db.commit()
    db.close()
    flash("Registration deleted.", "success")
    return redirect(url_for("admin_registrations"))


@app.route("/admin/export")
@login_required
def admin_export():
    event_filter = request.args.get("event_id", "")
    db = get_db()

    query = (
        "SELECT r.reg_code, r.name, r.email, r.phone, r.college, r.department, r.year, "
        "r.registered_at, e.title AS event_title, e.event_date, e.venue "
        "FROM registrations r JOIN events e ON r.event_id = e.id"
    )
    params = []
    if event_filter:
        query += " WHERE r.event_id = ?"
        params.append(event_filter)
    query += " ORDER BY e.title, r.registered_at"

    rows = db.execute(query, params).fetchall()
    db.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reg Code", "Name", "Email", "Phone", "College",
        "Department", "Year", "Event", "Event Date", "Venue", "Registered At"
    ])
    for row in rows:
        writer.writerow([
            row["reg_code"], row["name"], row["email"], row["phone"],
            row["college"], row["department"], row["year"],
            row["event_title"], row["event_date"], row["venue"], row["registered_at"],
        ])

    filename = f"registrations_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    seed_admin("admin", generate_password_hash("admin123"))
    app.run(debug=True)
