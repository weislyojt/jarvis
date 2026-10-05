"""SQLite storage: conversation, memories, routines, reminders, notifications, approvals, logins."""
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config

_lock = threading.RLock()
_conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,              -- user | assistant
    kind TEXT NOT NULL DEFAULT 'chat',-- chat | system
    text TEXT NOT NULL,
    meta TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    repeat TEXT NOT NULL DEFAULT 'none',
    active INTEGER NOT NULL DEFAULT 1,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,
    input TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    label TEXT,
    created TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS push_subs (
    endpoint TEXT PRIMARY KEY,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    label TEXT,
    created TEXT NOT NULL
);
"""

with _lock:
    _conn.executescript(SCHEMA)
    _conn.commit()


# ---------- settings and time zone ----------
def get_setting(key, default=None):
    with _lock:
        row = _conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with _lock:
        _conn.execute("INSERT INTO settings(key, value) VALUES (?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        _conn.commit()


_tz = {"name": None, "zone": None}


def set_client_timezone(name):
    """Remember the time zone of the user's device (a cloud server runs on UTC)."""
    if config.TIMEZONE or not name or name == _tz["name"]:
        return
    try:
        zone = ZoneInfo(name)
    except Exception:
        return
    _tz.update(name=name, zone=zone)
    set_setting("timezone", name)


def timezone_name():
    return config.TIMEZONE or _tz["name"] or get_setting("timezone") or ""


def _zone():
    if _tz["zone"] is None:
        name = timezone_name()
        if name:
            try:
                _tz.update(name=name, zone=ZoneInfo(name))
            except Exception:
                _tz.update(name=None, zone=None)
    return _tz["zone"]


def now():
    zone = _zone()
    return datetime.now(zone) if zone else datetime.now().astimezone()


def now_iso():
    return now().isoformat(timespec="seconds")


def _q(sql, args=(), one=False, commit=False):
    with _lock:
        cur = _conn.execute(sql, args)
        if commit:
            _conn.commit()
            return cur.lastrowid
        rows = [dict(r) for r in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows


# ---------- conversation ----------
def add_turn(role, text, kind="chat", meta=None):
    return _q("INSERT INTO turns(role, kind, text, meta, ts) VALUES (?,?,?,?,?)",
              (role, kind, text, json.dumps(meta) if meta else None, now_iso()), commit=True)


def recent_turns(limit):
    rows = _q("SELECT * FROM turns WHERE archived=0 ORDER BY id DESC LIMIT ?", (limit,))
    rows.reverse()
    for r in rows:
        r["meta"] = json.loads(r["meta"]) if r["meta"] else None
    return rows


def archive_turns():
    _q("UPDATE turns SET archived=1 WHERE archived=0", commit=True)


# ---------- memories ----------
def add_memory(category, content):
    content = content.strip()
    existing = _q("SELECT id FROM memories WHERE lower(content)=lower(?)", (content,), one=True)
    if existing:
        return existing["id"], False
    t = now_iso()
    mid = _q("INSERT INTO memories(category, content, created, updated) VALUES (?,?,?,?)",
             (category, content, t, t), commit=True)
    return mid, True


def update_memory(mid, content, category=None):
    row = get_memory(mid)
    if not row:
        return False
    _q("UPDATE memories SET content=?, category=?, updated=? WHERE id=?",
       (content.strip(), category or row["category"], now_iso(), mid), commit=True)
    return True


def get_memory(mid):
    return _q("SELECT * FROM memories WHERE id=?", (mid,), one=True)


def delete_memory(mid):
    with _lock:
        cur = _conn.execute("DELETE FROM memories WHERE id=?", (mid,))
        _conn.commit()
        return cur.rowcount > 0


def list_memories(category=None):
    if category:
        return _q("SELECT * FROM memories WHERE category=? ORDER BY id", (category,))
    return _q("SELECT * FROM memories ORDER BY id")


def search_memories(query):
    words = [w for w in query.lower().split() if len(w) > 1][:8] or [query.lower()]
    clause = " OR ".join(["lower(content) LIKE ?"] * len(words))
    return _q(f"SELECT * FROM memories WHERE {clause} ORDER BY updated DESC LIMIT 40",
              tuple(f"%{w}%" for w in words))


# ---------- reminders ----------
def add_reminder(text, due_at, repeat="none"):
    return _q("INSERT INTO reminders(text, due_at, repeat, created) VALUES (?,?,?,?)",
              (text, due_at.isoformat(timespec="seconds"), repeat, now_iso()), commit=True)


def list_reminders(active_only=True):
    sql = "SELECT * FROM reminders" + (" WHERE active=1" if active_only else "") + " ORDER BY due_at"
    return _q(sql)


def cancel_reminder(rid):
    with _lock:
        cur = _conn.execute("UPDATE reminders SET active=0 WHERE id=? AND active=1", (rid,))
        _conn.commit()
        return cur.rowcount > 0


def due_reminders():
    current = now()
    out = []
    for r in list_reminders():
        if datetime.fromisoformat(r["due_at"]) <= current:
            out.append(r)
    return out


def advance_reminder(r):
    """After a reminder fires: deactivate it, or schedule its next repeat."""
    step = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1),
            "hourly": timedelta(hours=1)}.get(r["repeat"])
    if r["repeat"] == "weekdays":
        step = timedelta(days=1)
    if not step:
        _q("UPDATE reminders SET active=0 WHERE id=?", (r["id"],), commit=True)
        return
    due = datetime.fromisoformat(r["due_at"])
    current = now()
    while due <= current or (r["repeat"] == "weekdays" and due.weekday() >= 5):
        due += step
    _q("UPDATE reminders SET due_at=? WHERE id=?", (due.isoformat(timespec="seconds"), r["id"]), commit=True)


# ---------- notifications ----------
def add_notification(kind, text):
    return _q("INSERT INTO notifications(kind, text, created) VALUES (?,?,?)",
              (kind, text, now_iso()), commit=True)


def notifications_after(after_id):
    return _q("SELECT * FROM notifications WHERE id>? ORDER BY id LIMIT 50", (after_id,))


def last_notification_id():
    row = _q("SELECT MAX(id) AS m FROM notifications", one=True)
    return (row or {}).get("m") or 0


# ---------- approvals ----------
def add_action(tool, tool_input, summary):
    return _q("INSERT INTO actions(tool, input, summary, created) VALUES (?,?,?,?)",
              (tool, json.dumps(tool_input), summary, now_iso()), commit=True)


def get_action(aid):
    row = _q("SELECT * FROM actions WHERE id=?", (aid,), one=True)
    if row:
        row["input"] = json.loads(row["input"])
    return row


def pending_actions():
    rows = _q("SELECT * FROM actions WHERE status='pending' ORDER BY id")
    for r in rows:
        r["input"] = json.loads(r["input"])
    return rows


def expire_actions(minutes=30):
    """Approvals nobody answered within `minutes` lapse, so stale requests can't be approved later."""
    for r in pending_actions():
        if (now() - datetime.fromisoformat(r["created"])).total_seconds() > minutes * 60:
            set_action(r["id"], "expired")


def set_action(aid, status, result=None):
    with _lock:
        cur = _conn.execute("UPDATE actions SET status=?, result=? WHERE id=? AND status='pending'",
                            (status, result, aid))
        _conn.commit()
        return cur.rowcount > 0


# ---------- logins ----------
def new_session(label):
    token = secrets.token_urlsafe(32)
    t = now_iso()
    _q("INSERT INTO sessions(token, label, created, last_seen) VALUES (?,?,?,?)", (token, label, t, t), commit=True)
    return token


def check_session(token):
    if not token:
        return False
    row = _q("SELECT token FROM sessions WHERE token=?", (token,), one=True)
    if row:
        _q("UPDATE sessions SET last_seen=? WHERE token=?", (now_iso(), token), commit=True)
        return True
    return False


def end_session(token):
    _q("DELETE FROM sessions WHERE token=?", (token,), commit=True)


def end_all_sessions():
    _q("DELETE FROM sessions", commit=True)


# ---------- phone push subscriptions ----------
def add_push_sub(endpoint, p256dh, auth, label=""):
    with _lock:
        _conn.execute("INSERT INTO push_subs(endpoint, p256dh, auth, label, created) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, "
                      "label=excluded.label", (endpoint, p256dh, auth, label, now_iso()))
        _conn.commit()


def push_subs():
    return _q("SELECT * FROM push_subs")


def delete_push_sub(endpoint):
    _q("DELETE FROM push_subs WHERE endpoint=?", (endpoint,), commit=True)
