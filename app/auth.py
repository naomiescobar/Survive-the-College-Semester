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
    return render_template("dashboard.html")

@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))