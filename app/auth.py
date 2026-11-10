import random

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError
from .db import get_db

auth = Blueprint("auth", __name__)

# ---------------------------------------------------------------------------
# Game settings (tweak these to tune the game)
# ---------------------------------------------------------------------------
TOTAL_WEEKS = 16
ACTIONS_PER_WEEK = 3
BASE_EVENT_CHANCE = 15   # percent chance of an event after the first action of a week
EVENT_CHANCE_STEP = 10   # chance goes up by this much after every action with no event

STAT_KEYS = ("energy", "money", "stress", "homework", "attendance")
STAT_LABELS = {
    "energy": "Energy",
    "money": "Money",
    "stress": "Stress",
    "homework": "Homework",
    "attendance": "Attendance",
}

# What each action does to the player's stats
ACTIONS = {
    "study": {"energy": -15, "stress": 5, "homework": 20},
    "work": {"energy": -20, "money": 60, "stress": 10},
    "sleep": {"energy": 25, "stress": -10},
    "skip_class": {"energy": 5, "stress": 5, "attendance": -15},
}

MESSAGES = {
    "study": "You studied for 2 hours. Your homework improved!",
    "work": "You completed a work shift and earned $60!",
    "sleep": "You got some rest. Your energy recovered!",
    "skip_class": "You skipped class. Your attendance suffered!",
}

# Game over screens, keyed by the reason the game ended
GAME_OVER_SCREENS = {
    "stress": {
        "title": "💥 Burnout!",
        "text": "Your stress hit 100%. You couldn't take any more and had to take a leave of absence.",
    },
    "attendance": {
        "title": "📉 Failed Out!",
        "text": "Your attendance hit 0%. The university has dropped you from your classes.",
    },
}

# Random events. Each action has its own pool, and every event gives the
# player an A/B choice where each option trades one stat for another.
EVENTS = {
    "study": [
        {
            "title": "Pop quiz!",
            "text": "Your professor announces a surprise quiz on the material you just reviewed.",
            "a": {
                "label": "Give it your full focus",
                "effects": {"energy": -10, "homework": 10},
                "result": "You aced the quiz, but it wore you out.",
            },
            "b": {
                "label": "Wing it and save your energy",
                "effects": {"stress": 10, "homework": 5},
                "result": "You scraped by, but the uncertainty has you on edge.",
            },
        },
        {
            "title": "Laptop crash",
            "text": "Your laptop freezes right before you saved your assignment.",
            "a": {
                "label": "Redo it from scratch",
                "effects": {"energy": -15, "homework": 10},
                "result": "You rebuilt it from memory. Exhausting, but it's done.",
            },
            "b": {
                "label": "Email the professor for an extension",
                "effects": {"stress": 10},
                "result": "The professor said maybe. Now you wait, anxiously.",
            },
        },
    ],
    "work": [
        {
            "title": "Regular customer",
            "text": "A regular offers a big tip if you stay late and help them out.",
            "a": {
                "label": "Stay late",
                "effects": {"money": 30, "energy": -15, "stress": 5},
                "result": "The tip was great, but you're dragging.",
            },
            "b": {
                "label": "Clock out on time",
                "effects": {"energy": 5, "stress": -5},
                "result": "You went home on time and felt a little better.",
            },
        },
        {
            "title": "Cover a shift?",
            "text": "A coworker begs you to cover their shift this weekend.",
            "a": {
                "label": "Cover it",
                "effects": {"money": 40, "energy": -20, "stress": 5},
                "result": "Extra cash in your pocket, but you're beat.",
            },
            "b": {
                "label": "Politely decline",
                "effects": {"energy": 5, "stress": 5},
                "result": "You got some rest, but you feel a little guilty.",
            },
        },
    ],
    "sleep": [
        {
            "title": "Roommate party!",
            "text": "Your roommate is having a party while you're trying to sleep.",
            "a": {
                "label": "Ignore it and try to sleep",
                "effects": {"energy": -10, "stress": 5},
                "result": "You barely slept through the noise.",
            },
            "b": {
                "label": "Tell your roommate to turn it down",
                "effects": {"energy": -5, "stress": 10},
                "result": "They turned it down, but the argument stressed you out.",
            },
        },
        {
            "title": "Overslept!",
            "text": "You wake up and realize you're about to be late for class.",
            "a": {
                "label": "Rush to class",
                "effects": {"energy": -10, "stress": 10},
                "result": "You made it just in time, heart pounding.",
            },
            "b": {
                "label": "Skip it and keep sleeping",
                "effects": {"energy": 10, "attendance": -10},
                "result": "Sleep was great. Your attendance record wasn't.",
            },
        },
    ],
    "skip_class": [
        {
            "title": "Attendance was taken",
            "text": "A friend texts you: the professor took attendance today.",
            "a": {
                "label": "Email the professor with an excuse",
                "effects": {"stress": 10, "attendance": 5},
                "result": "The professor bought it, but lying was stressful.",
            },
            "b": {
                "label": "Accept the consequences",
                "effects": {"attendance": -10},
                "result": "You took the hit to your attendance.",
            },
        },
        {
            "title": "Lunch invite",
            "text": "Since you're free, your friends invite you out to lunch.",
            "a": {
                "label": "Go out with them",
                "effects": {"money": -20, "stress": -10},
                "result": "Lunch was fun and you feel a lot lighter.",
            },
            "b": {
                "label": "Stay in and catch up on homework",
                "effects": {"energy": -10, "homework": 10},
                "result": "You made the most of your free time.",
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def describe_effects(effects):
    """Turn {'energy': -10, 'stress': 5} into 'Energy -10 | Stress +5'."""
    parts = []
    for key in STAT_KEYS:
        value = effects.get(key, 0)
        if value == 0:
            continue
        if key == "money":
            sign = "+" if value > 0 else "-"
            parts.append(f"Money {sign}${abs(value)}")
        else:
            parts.append(f"{STAT_LABELS[key]} {value:+d}")
    return " | ".join(parts)


def get_game_over_reason(stress, attendance):
    """Return 'stress' or 'attendance' if the game is lost, otherwise None."""
    if stress >= 100:
        return "stress"
    if attendance <= 0:
        return "attendance"
    return None


def get_pending_event(pending):
    """Look up the event stored in the session. Returns None if invalid."""
    if not pending:
        return None
    try:
        return EVENTS[pending["action"]][pending["index"]]
    except (KeyError, IndexError, TypeError):
        return None


def apply_stat_changes(cur, player_id, effects):
    """Apply stat changes to a player, keeping every stat within its limits."""
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
            effects.get("energy", 0),
            effects.get("money", 0),
            effects.get("stress", 0),
            effects.get("homework", 0),
            effects.get("attendance", 0),
            player_id,
        ),
    )


def advance_week_if_done(cur, player_id):
    """
    If the player is out of actions and it isn't the final week, move to the
    next week and refill their actions. Returns True if the week advanced.
    Safe to call at any time: it does nothing if the conditions aren't met,
    and it never advances a game that is already over (stress 100 or
    attendance 0).
    """
    cur.execute(
        """
        UPDATE players
        SET semester_week = semester_week + 1,
            actions_left = %s,
            event_chance = %s
        WHERE player_id = %s
          AND actions_left = 0
          AND semester_week < %s
          AND stress < 100
          AND attendance > 0
        """,
        (ACTIONS_PER_WEEK, BASE_EVENT_CHANCE, player_id, TOTAL_WEEKS),
    )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
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

    # Is the player in the middle of a random event?
    event = get_pending_event(session.get("pending_event"))
    if event is None:
        session.pop("pending_event", None)

    db = get_db()
    cur = db.cursor(dictionary=True)

    try:
        # Safety net: if a player is out of actions with no event pending
        # (for example, they logged out mid-event), move them to the next week.
        # (This does nothing if the game is already over.)
        if event is None and advance_week_if_done(cur, session["player_id"]):
            db.commit()
            flash("A new week begins!", "info")

        cur.execute(
            """
            SELECT username, energy, money, stress, homework,
                   attendance, semester_week, actions_left
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

    # Has the player lost? (stress at 100 or attendance at 0)
    game_over = None
    reason = get_game_over_reason(player["stress"], player["attendance"])
    if reason is not None:
        game_over = GAME_OVER_SCREENS[reason]
        # Nothing left to respond to once the game is over
        session.pop("pending_event", None)
        event = None

    # Build what the template needs to show the event card
    event_view = None
    if event is not None:
        event_view = {
            "title": event["title"],
            "text": event["text"],
            "options": [
                (key, event[key]["label"], describe_effects(event[key]["effects"]))
                for key in ("a", "b")
            ],
        }

    # The semester is complete once the final week has no actions left
    semester_complete = (
        game_over is None
        and event is None
        and player["semester_week"] >= TOTAL_WEEKS
        and player["actions_left"] <= 0
    )

    return render_template(
        "dashboard.html",
        player=player,
        event=event_view,
        game_over=game_over,
        semester_complete=semester_complete,
        actions_per_week=ACTIONS_PER_WEEK,
    )

@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth.route("/next-week", methods=["POST"])
def next_week():
    """End the current week early: forfeit any unused actions and move on."""
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    # Players must answer a pending event before doing anything else
    if get_pending_event(session.get("pending_event")) is not None:
        flash("Respond to the event first!", "warning")
        return redirect(url_for("auth.dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)
    message = None
    category = "info"

    try:
        cur.execute(
            "SELECT actions_left, stress, attendance FROM players WHERE player_id = %s",
            (session["player_id"],),
        )
        state = cur.fetchone()

        if state is None:
            session.clear()
            flash("Please sign in again.", "warning")
            return redirect(url_for("auth.login"))

        if get_game_over_reason(state["stress"], state["attendance"]) is not None:
            message = "Your game is over. Reset the game to try again."
            category = "danger"
        elif state["actions_left"] <= 0:
            message = "There are no actions left to skip this week."
            category = "warning"
        else:
            # Forfeit the remaining actions, then roll over to the next week
            cur.execute(
                "UPDATE players SET actions_left = 0 WHERE player_id = %s",
                (session["player_id"],),
            )
            advanced = advance_week_if_done(cur, session["player_id"])
            db.commit()

            if advanced:
                message = "You ended the week early. A new week begins!"
            else:
                # Week 16 has no next week, so ending it finishes the semester
                message = "You ended the final week early. The semester is over!"
    finally:
        cur.close()
        db.close()

    flash(message, category)
    return redirect(url_for("auth.dashboard"))


@auth.route("/action/<action_name>", methods=["POST"])
def game_action(action_name):
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    # Players must answer a pending event before doing anything else
    if get_pending_event(session.get("pending_event")) is not None:
        flash("Respond to the event first!", "warning")
        return redirect(url_for("auth.dashboard"))

    if action_name not in ACTIONS:
        flash("Invalid game action.", "danger")
        return redirect(url_for("auth.dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)
    new_event_index = None
    week_advanced = False

    try:
        cur.execute(
            """
            SELECT actions_left, event_chance, stress, attendance
            FROM players
            WHERE player_id = %s
            """,
            (session["player_id"],),
        )
        state = cur.fetchone()

        if state is None:
            session.clear()
            flash("Please sign in again.", "warning")
            return redirect(url_for("auth.login"))

        # No more moves once the game is lost
        if get_game_over_reason(state["stress"], state["attendance"]) is not None:
            flash("Your game is over. Reset the game to try again.", "danger")
            return redirect(url_for("auth.dashboard"))

        if state["actions_left"] <= 0:
            flash("You have no actions left. The semester is over!", "warning")
            return redirect(url_for("auth.dashboard"))

        # 1. Apply the action's stat changes
        apply_stat_changes(cur, session["player_id"], ACTIONS[action_name])

        # 2. Did that action end the game?
        cur.execute(
            "SELECT stress, attendance FROM players WHERE player_id = %s",
            (session["player_id"],),
        )
        after = cur.fetchone()
        game_lost = get_game_over_reason(after["stress"], after["attendance"]) is not None

        # 3. Roll for a random event (skipped if the game just ended)
        event_fired = False
        if game_lost:
            new_chance = state["event_chance"]
        else:
            event_fired = random.randint(1, 100) <= state["event_chance"]
            if event_fired:
                new_chance = BASE_EVENT_CHANCE
                new_event_index = random.randrange(len(EVENTS[action_name]))
            else:
                new_chance = min(100, state["event_chance"] + EVENT_CHANCE_STEP)

        # 4. Use up one action point and save the new event chance
        cur.execute(
            """
            UPDATE players
            SET actions_left = actions_left - 1,
                event_chance = %s
            WHERE player_id = %s
            """,
            (new_chance, session["player_id"]),
        )

        # 5. If that was the last action and no event fired, the week ends now.
        # (If an event fired, the week ends after the player responds to it.
        # A lost game never advances.)
        if not event_fired:
            week_advanced = advance_week_if_done(cur, session["player_id"])

        db.commit()
    finally:
        cur.close()
        db.close()

    flash(MESSAGES[action_name], "success")

    if new_event_index is not None:
        session["pending_event"] = {"action": action_name, "index": new_event_index}
    elif week_advanced:
        flash("The week is over. A new week begins!", "info")

    return redirect(url_for("auth.dashboard"))


@auth.route("/event/<choice>", methods=["POST"])
def resolve_event(choice):
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    event = get_pending_event(session.get("pending_event"))
    if event is None:
        session.pop("pending_event", None)
        flash("There's no event to respond to.", "warning")
        return redirect(url_for("auth.dashboard"))

    if choice not in ("a", "b"):
        flash("Invalid choice.", "danger")
        return redirect(url_for("auth.dashboard"))

    option = event[choice]

    db = get_db()
    cur = db.cursor()

    try:
        apply_stat_changes(cur, session["player_id"], option["effects"])
        # The action that triggered this event may have been the week's last one
        # (this does nothing if the event just ended the game)
        week_advanced = advance_week_if_done(cur, session["player_id"])
        db.commit()
    finally:
        cur.close()
        db.close()

    session.pop("pending_event", None)
    flash(option["result"], "info")
    if week_advanced:
        flash("The week is over. A new week begins!", "info")

    return redirect(url_for("auth.dashboard"))


@auth.route("/reset", methods=["POST"])
def reset_game():
    if "player_id" not in session:
        return redirect(url_for("auth.login"))

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute(
            """
            UPDATE players
            SET energy = 100,
                money = 500.00,
                stress = 0,
                homework = 0,
                attendance = 100,
                semester_week = 1,
                actions_left = %s,
                event_chance = %s
            WHERE player_id = %s
            """,
            (ACTIONS_PER_WEEK, BASE_EVENT_CHANCE, session["player_id"]),
        )
        db.commit()
    finally:
        cur.close()
        db.close()

    session.pop("pending_event", None)
    flash("Your game has been reset. Good luck!", "info")
    return redirect(url_for("auth.dashboard"))