from flask import Flask, request, jsonify
import sqlite3, datetime, uuid
from collections import defaultdict

app = Flask(__name__)

DB = "habits.db"

# -----------------------------------
# DATABASE HELPERS
# -----------------------------------
def get_db():
    # small timeout to reduce 'database is locked' errors under concurrency
    conn = sqlite3.connect(DB, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    return conn

def get_db_conn():
    # For writing operations / concurrent access
    conn = sqlite3.connect(DB, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    return conn


def row_get(row, key):
    """Safely get a value from a DB row or a dict-like row.
    sqlite3.Row does not implement .get(), so handle both types.
    """
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return None


# -----------------------------------
# INITIAL TABLES
# -----------------------------------
def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    # ensure unique index on habit name to prevent duplicates
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_habits_name_unique ON habits(name)")
    conn.commit()
    # Ensure new optional columns exist: description, active
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(habits)")
    existing = [r[1] if isinstance(r, tuple) else r["name"] for r in cur.fetchall()]
    if "description" not in existing:
        conn.execute("ALTER TABLE habits ADD COLUMN description TEXT DEFAULT ''")
    if "active" not in existing:
        conn.execute("ALTER TABLE habits ADD COLUMN active INTEGER DEFAULT 1")
    if "archived_at" not in existing:
        conn.execute("ALTER TABLE habits ADD COLUMN archived_at TEXT DEFAULT NULL")
    conn.commit()

def ensure_tables():
    conn = get_db_conn()
    cur = conn.cursor()

    # Log table for ALL events (completion, skip, notifications sent, etc.)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_uuid TEXT,
            habit_id INTEGER,
            event_type TEXT,
            timestamp TEXT,
            source TEXT
        )
    """)

    # Daily aggregation table for fast stats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_agg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER,
            day TEXT,
            completions INTEGER DEFAULT 0,
            skips INTEGER DEFAULT 0,
            UNIQUE(habit_id, day)
        )
    """)

    conn.commit()
    conn.close()


init_db()
ensure_tables()


# -----------------------------------
# ROUTES
# -----------------------------------

# Create a habit
@app.route("/habits", methods=["POST"])
def create_habit():
    data = request.get_json() or {}
    # accept both "habit_name" (old client) and "name" (current Android new flow)
    name = (data.get("habit_name") or data.get("name") or "").strip()
    description = data.get("description", "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # check for duplicate names (case-insensitive)
    cur.execute("SELECT id FROM habits WHERE lower(name)=?", (name.lower(),))
    existing = cur.fetchone()
    
    if existing:
        return jsonify({
            "error": "A habit with this name already exists",
            "existing_id": existing["id"]
        }), 409

    cur.execute("INSERT INTO habits (name, description) VALUES (?, ?)", (name, description))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return jsonify({
        "id": new_id,
        "name": name,
        "description": description,
        "message": "Habit added successfully!"
    }), 201



# Get all habits
@app.route("/habits", methods=["GET"])
def get_habits():
    conn = get_db()
    # Return all habits with their active field - client will filter
    rows = conn.execute("SELECT * FROM habits ORDER BY created_at DESC").fetchall()
    habits = [{
        "id": row["id"],
        "name": row["name"],
        "description": row_get(row, "description"),
        "active": row_get(row, "active"),
        "archived_at": row_get(row, "archived_at"),
        "created_at": row["created_at"]
    } for row in rows]

    return jsonify({"habits": habits})


@app.route("/habits/<int:habit_id>", methods=["GET"])
def get_habit(habit_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    
    if not row:
        return jsonify({"error": "Habit not found"}), 404

    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "description": row_get(row, "description"),
        "active": row_get(row, "active"),
        "archived_at": row_get(row, "archived_at"),
        "created_at": row["created_at"]
    }), 200


# Log an event (in-memory example)
@app.route("/events", methods=["POST"])
def log_event():
    data = request.get_json()

    habit_id = data.get("habit_id")
    event_type = data.get("event_type")
    source = data.get("source", "unknown")

    if not habit_id or not event_type:
        return jsonify({"error": "Missing habit_id or event_type"}), 400

    timestamp = datetime.datetime.utcnow().isoformat()

    # In-memory example (replace with DB later)
    if "events" not in app.config:
        app.config["events"] = []

    event_record = {
        "habit_id": habit_id,
        "event_type": event_type,
        "source": source,
        "timestamp": timestamp
    }

    app.config["events"].append(event_record)

    # Also persist to DB so undo and status endpoints work
    try:
        user_uuid = data.get("user_uuid") or str(uuid.uuid4())
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO habit_logs (user_uuid, habit_id, event_type, timestamp, source) VALUES (?,?,?,?,?)",
            (user_uuid, habit_id, event_type, timestamp, source)
        )
        # update daily_agg
        day = timestamp.split("T")[0]
        cur.execute("INSERT OR IGNORE INTO daily_agg (habit_id, day, completions, skips) VALUES (?,?,0,0)", (habit_id, day))
        if event_type == "complete":
            cur.execute("UPDATE daily_agg SET completions = completions + 1 WHERE habit_id = ? AND day = ?", (habit_id, day))
        elif event_type == "skip":
            cur.execute("UPDATE daily_agg SET skips = skips + 1 WHERE habit_id = ? AND day = ?", (habit_id, day))
        conn.commit()
        conn.close()
    except Exception:
        app.logger.exception("failed to persist event to DB")

    return jsonify({"status": "event_logged", "event": event_record}), 201


@app.route("/events/undo", methods=["POST"])
def undo_last_event():
    data = request.get_json() or {}
    habit_id = data.get("habit_id")
    window_seconds = int(data.get("window_seconds", 60))

    if not habit_id:
        return jsonify({"error":"habit_id required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(seconds=window_seconds)).isoformat()
    # find last event for habit after cutoff
    cur.execute("""SELECT id, event_type, timestamp FROM habit_logs
                   WHERE habit_id = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 1""",
                (habit_id, cutoff))
    row = cur.fetchone()
    if not row:
        return jsonify({"status":"no_recent_event"}), 404

    # delete it, and decrement daily_agg counters if needed
    event_id = row["id"]
    event_type = row["event_type"]
    ts = row["timestamp"]
    day = ts.split("T")[0]

    cur.execute("DELETE FROM habit_logs WHERE id = ?", (event_id,))
    if event_type == "complete":
        cur.execute("""
            UPDATE daily_agg
            SET completions = CASE WHEN completions > 0 THEN completions - 1 ELSE 0 END
            WHERE habit_id = ? AND day = ?
        """, (habit_id, day))
    elif event_type == "skip":
        cur.execute("""
            UPDATE daily_agg
            SET skips = CASE WHEN skips > 0 THEN skips - 1 ELSE 0 END
            WHERE habit_id = ? AND day = ?
        """, (habit_id, day))

    conn.commit()
    conn.close()
    return jsonify({"status":"undone"}), 200


# Get today's status for a habit
@app.route("/habit_status_today/<int:habit_id>", methods=["GET"])
def get_habit_status_today(habit_id):
    today = datetime.date.today().isoformat()
    conn = get_db()

    # Check if any event logged for this habit today
    row = conn.execute("""
        SELECT event_type FROM habit_logs
        WHERE habit_id = ? AND timestamp LIKE ?
        ORDER BY timestamp DESC LIMIT 1
    """, (habit_id, today + "%")).fetchone()

    if not row:
        return jsonify({"status": "none"}), 200
    
    return jsonify({"status": row["event_type"]}), 200


@app.route("/habits/<int:habit_id>", methods=["PUT"])
def update_habit(habit_id):
    data = request.get_json() or {}

    conn = get_db()
    cur = conn.cursor()

    # ensure habit exists
    existing = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Habit not found"}), 404

    # build update dynamically based on provided keys
    fields = []
    params = []

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        fields.append("name = ?")
        params.append(name)

    if "description" in data:
        fields.append("description = ?")
        params.append(data.get("description") or "")

    if "active" in data:
        # coerce to 0/1
        try:
            active_val = 1 if int(data.get("active")) else 0
        except Exception:
            return jsonify({"error": "Invalid active value"}), 400
        fields.append("active = ?")
        params.append(active_val)

        # set archived_at when archiving, clear when unarchiving
        if active_val == 0:
            fields.append("archived_at = ?")
            params.append(datetime.datetime.utcnow().isoformat())
        else:
            fields.append("archived_at = ?")
            params.append(None)

    if not fields:
        return jsonify({"error": "No updatable fields provided"}), 400

    params.append(habit_id)
    sql = "UPDATE habits SET " + ", ".join(fields) + " WHERE id = ?"
    cur.execute(sql, params)
    conn.commit()
    conn.close()

    return jsonify({"message": "Habit updated"}), 200


@app.route("/habits/<int:habit_id>/archive", methods=["POST"])
def archive_habit(habit_id):
    conn = get_db()
    cur = conn.cursor()
    # set active = 0 and archived_at
    archived_at = datetime.datetime.utcnow().isoformat()
    cur.execute("UPDATE habits SET active = 0, archived_at = ? WHERE id = ?", (archived_at, habit_id))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "Habit not found"}), 404
    conn.close()
    return jsonify({"message": "Habit archived", "archived_at": archived_at}), 200


@app.route("/habits/<int:habit_id>/unarchive", methods=["POST"])
def unarchive_habit(habit_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE habits SET active = 1, archived_at = NULL WHERE id = ?", (habit_id,))
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "Habit not found"}), 404
    conn.close()
    return jsonify({"message": "Habit unarchived"}), 200


@app.route("/habits/archived", methods=["GET"])
def get_archived_habits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM habits WHERE active = 0 ORDER BY archived_at DESC").fetchall()
    habits = [{
        "id": row["id"],
        "name": row["name"],
        "description": row_get(row, "description"),
        "archived_at": row_get(row, "archived_at"),
        "created_at": row["created_at"]
    } for row in rows]
    return jsonify({"habits": habits})


@app.route("/habits/<int:habit_id>", methods=["DELETE"])
def delete_habit(habit_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    conn.commit()

    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "Habit not found"}), 404

    conn.close()
    return jsonify({"message": "Habit deleted"}), 200


@app.route("/today_status_all", methods=["GET"])
def today_status_all():
    conn = get_db()
    cur = conn.cursor()

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # Fetch latest event PER habit for today
    cur.execute("""
        SELECT habit_id, event_type, MAX(timestamp) AS ts
        FROM habit_logs
        WHERE timestamp LIKE ?
        GROUP BY habit_id
    """, (today + "%",))

    rows = cur.fetchall()

    result = {}

    for row in rows:
        # row is sqlite3.Row
        result[row["habit_id"]] = {
            "status": row["event_type"],
            "last_time": row["ts"],
            "can_edit": True  # editable until 23:59:59
        }

    # If a habit has no log today → set default
    # Fetch all habit IDs
    hrows = conn.execute("SELECT id FROM habits").fetchall()
    for h in hrows:
        hid = h["id"]
        if hid not in result:
            result[hid] = {
                "status": "none",
                "last_time": None,
                "can_edit": True
            }

    return jsonify({"statuses": result})


# GET /analytics/summary (also available as /analytics)
@app.route("/analytics/summary", methods=["GET"])
@app.route("/analytics", methods=["GET"])
def analytics_summary():
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        today = datetime.date.today()
        
        # Basic counts
        total_habits = cur.execute("SELECT COUNT(*) as c FROM habits WHERE active=1").fetchone()[0]
        archived_habits = cur.execute("SELECT COUNT(*) as c FROM habits WHERE active=0").fetchone()[0]

        # Completions over time periods
        seven_days_ago = (today - datetime.timedelta(days=6)).isoformat()
        thirty_days_ago = (today - datetime.timedelta(days=29)).isoformat()

        cur.execute("""
            SELECT COUNT(*) as c
            FROM habit_logs
            WHERE event_type='complete' AND date(timestamp) >= ?
        """, (seven_days_ago,))
        completions_7d = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) as c
            FROM habit_logs
            WHERE event_type='complete' AND date(timestamp) = ?
        """, (today.isoformat(),))
        completions_today = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) as c
            FROM habit_logs
            WHERE event_type='complete' AND date(timestamp) >= ?
        """, (thirty_days_ago,))
        completions_30d = cur.fetchone()[0]

        # Completion rate (complete vs skip)
        cur.execute("""
            SELECT 
                SUM(CASE WHEN event_type='complete' THEN 1 ELSE 0 END) as completes,
                SUM(CASE WHEN event_type='skip' THEN 1 ELSE 0 END) as skips
            FROM habit_logs
            WHERE date(timestamp) >= ?
        """, (thirty_days_ago,))
        row = cur.fetchone()
        completes = row[0] or 0
        skips = row[1] or 0
        total_events = completes + skips
        completion_rate = round((completes / total_events * 100), 1) if total_events > 0 else 0

        # Daily breakdown (last 7 days)
        cur.execute("""
            SELECT date(timestamp) as day, COUNT(*) as cnt
            FROM habit_logs
            WHERE event_type='complete' AND date(timestamp) >= ?
            GROUP BY date(timestamp)
            ORDER BY day
        """, (seven_days_ago,))
        daily_breakdown = [{"day": r[0], "completions": r[1]} for r in cur.fetchall()]

        # Top 5 habits by completions (30 days)
        cur.execute("""
            SELECT h.id, h.name, COUNT(l.id) as cnt
            FROM habits h
            LEFT JOIN habit_logs l ON l.habit_id = h.id AND l.event_type='complete' AND date(l.timestamp) >= ?
            WHERE h.active = 1
            GROUP BY h.id
            ORDER BY cnt DESC
            LIMIT 5
        """, (thirty_days_ago,))
        top_habits = [{"id": r[0], "name": r[1], "completions": r[2]} for r in cur.fetchall()]

        # Current streaks per habit
        cur.execute("SELECT habit_id, day, completions FROM daily_agg ORDER BY habit_id, day")
        rows = cur.fetchall()
        
        days_by_habit = defaultdict(list)
        for r in rows:
            if r["completions"] > 0:
                days_by_habit[r["habit_id"]].append(r["day"])
        
        def calculate_current_streak(date_list):
            """Calculate current streak ending today"""
            if not date_list:
                return 0
            date_set = set(date_list)
            current = today
            streak = 0
            while current.isoformat() in date_set:
                streak += 1
                current = current - datetime.timedelta(days=1)
            return streak
        
        def longest_consecutive(date_list):
            if not date_list:
                return 0
            s = set(date_list)
            longest = 0
            for d in date_list:
                curd = datetime.date.fromisoformat(d)
                length = 1
                nxt = curd + datetime.timedelta(days=1)
                while nxt.isoformat() in s:
                    length += 1
                    nxt = nxt + datetime.timedelta(days=1)
                if length > longest:
                    longest = length
            return longest
        
        current_streaks = []
        longest_streaks = []
        for hid, ds in days_by_habit.items():
            current_streaks.append(calculate_current_streak(ds))
            longest_streaks.append(longest_consecutive(ds))
        
        avg_current_streak = round(sum(current_streaks) / len(current_streaks), 1) if current_streaks else 0
        avg_longest_streak = int(sum(longest_streaks) / len(longest_streaks)) if longest_streaks else 0
        max_current_streak = max(current_streaks) if current_streaks else 0

        conn.close()
        
        return jsonify({
            "status": "success",
            "data": {
                "overview": {
                    "total_habits": total_habits,
                    "archived_habits": archived_habits,
                    "completions_today": completions_today,
                    "completions_7d": completions_7d,
                    "completions_30d": completions_30d,
                    "completion_rate_30d": completion_rate
                },
                "streaks": {
                    "avg_current_streak": avg_current_streak,
                    "avg_longest_streak": avg_longest_streak,
                    "max_current_streak": max_current_streak
                },
                "daily_breakdown_7d": daily_breakdown,
                "top_habits_30d": top_habits,
                "model_versions": {},
                "metadata": {
                    "generated_at": datetime.datetime.utcnow().isoformat(),
                    "timezone": "UTC"
                }
            }
        }), 200

    except Exception as e:
        app.logger.exception("Analytics error")
        return jsonify({
            "status": "error",
            "message": "Failed to generate analytics",
            "error": str(e)
        }), 500

# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
