from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError
from .db import get_db

auth = Blueprint("auth", __name__)

@auth.route("/")
def home():
    return redirect(url_for("auth.login"))

@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO players (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, generate_password_hash(password)),
            )
            db.commit()
        except IntegrityError:
            flash("That username or email is already taken.", "danger")
            return render_template("signup.html")
        finally:
            cur.close()
            db.close()

        flash("Account created. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("signup.html")

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT player_id, username, password_hash FROM players WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
        cur.close()
        db.close()

        if row and check_password_hash(row[2], password):
            session["player_id"] = row[0]
            session["username"] = row[1]
            return redirect(url_for("auth.dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")

@auth.route("/dashboard")
def dashboard():
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    cur = db.cursor(dictionary=True)

    try:
        cur.execute(
            """
            SELECT username, energy, money, stress, homework,
                   attendance, semester_week
            FROM players
            WHERE player_id = %s
            """,
            (session["player_id"],),
        )
        player = cur.fetchone()
    finally:
        cur.close()
        db.close()

    if player is None:
        session.clear()
        flash("Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    return render_template("dashboard.html", player=player)

@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth.route("/next-week", methods=["POST"])
def next_week():
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute(
            """
            UPDATE players
            SET semester_week = semester_week + 1
            WHERE player_id = %s
              AND semester_week < 16
            """,
            (session["player_id"],),
        )
        db.commit()

        if cur.rowcount == 1:
            flash("A new week begins! Good luck surviving college! 🎉", "success")
        else:
            flash("You survived all 16 weeks! You completed the semester! 🎓", "success")

    finally:
        cur.close()
        db.close()

    return redirect(url_for("auth.dashboard"))


@auth.route("/action/<action_name>", methods=["POST"])
def game_action(action_name):
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    actions = {
        "study": (-15, 0, 5, 20, 0),
        "work": (-20, 60, 10, 0, 0),
        "sleep": (25, 0, -10, 0, 0),
        "skip_class": (5, 0, 5, 0, -15),
    }

    messages = {
        "study": "You studied for 2 hours. Your homework improved!",
        "work": "You completed a work shift and earned $60!",
        "sleep": "You got some rest. Your energy recovered!",
        "skip_class": "You skipped class. Your attendance suffered!",
    }

    if action_name not in actions:
        flash("Invalid game action.", "danger")
        return redirect(url_for("auth.dashboard"))

    energy, money, stress, homework, attendance = actions[action_name]

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute(
            """
            UPDATE players
            SET
                energy = GREATEST(0, LEAST(100, energy + %s)),
                money = GREATEST(0, money + %s),
                stress = GREATEST(0, LEAST(100, stress + %s)),
                homework = GREATEST(0, LEAST(100, homework + %s)),
                attendance = GREATEST(0, LEAST(100, attendance + %s))
            WHERE player_id = %s
            """,
            (
                energy,
                money,
                stress,
                homework,
                attendance,
                session["player_id"],
            ),
        )
        db.commit()
    finally:
        cur.close()
        db.close()

    flash(messages[action_name], "success")
    return redirect(url_for("auth.dashboard"))
