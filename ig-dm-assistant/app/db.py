"""SQLite storage. Single-writer, low volume — a module-level lock is enough."""

import json
import os
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    sender_id            TEXT PRIMARY KEY,
    name                 TEXT,
    profile_pic          TEXT,
    last_customer_msg_at REAL,
    created_at           REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id  TEXT NOT NULL,
    direction  TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    text       TEXT NOT NULL,
    mid        TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages (sender_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_mid ON messages (mid) WHERE mid IS NOT NULL;

CREATE TABLE IF NOT EXISTS drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id    TEXT NOT NULL,
    message_id   INTEGER,
    draft_text   TEXT NOT NULL,
    final_text   TEXT,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'edited', 'skipped', 'failed')),
    flagged      INTEGER NOT NULL DEFAULT 0,
    flag_reason  TEXT,
    crm_summary  TEXT,
    created_at   REAL NOT NULL,
    resolved_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts (status, created_at);

CREATE TABLE IF NOT EXISTS customer_cache (
    sender_id  TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription TEXT NOT NULL UNIQUE,
    created_at   REAL NOT NULL
);
"""


def init() -> None:
    global _conn
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    _conn.commit()


def _db() -> sqlite3.Connection:
    assert _conn is not None, "db.init() not called"
    return _conn


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ── conversations / messages ────────────────────────────────────────────────

def upsert_conversation(sender_id: str, name: str | None = None,
                        profile_pic: str | None = None,
                        customer_msg_at: float | None = None) -> None:
    with _lock:
        db = _db()
        db.execute(
            "INSERT INTO conversations (sender_id, created_at) VALUES (?, ?) "
            "ON CONFLICT(sender_id) DO NOTHING",
            (sender_id, time.time()),
        )
        if name:
            db.execute("UPDATE conversations SET name = ? WHERE sender_id = ?", (name, sender_id))
        if profile_pic:
            db.execute("UPDATE conversations SET profile_pic = ? WHERE sender_id = ?",
                       (profile_pic, sender_id))
        if customer_msg_at:
            db.execute("UPDATE conversations SET last_customer_msg_at = ? WHERE sender_id = ?",
                       (customer_msg_at, sender_id))
        db.commit()


def get_conversation(sender_id: str) -> dict | None:
    cur = _db().execute("SELECT * FROM conversations WHERE sender_id = ?", (sender_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def add_message(sender_id: str, direction: str, text: str,
                mid: str | None = None) -> int | None:
    """Store a message. Returns row id, or None if this mid was already stored."""
    with _lock:
        db = _db()
        try:
            cur = db.execute(
                "INSERT INTO messages (sender_id, direction, text, mid, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sender_id, direction, text, mid, time.time()),
            )
        except sqlite3.IntegrityError:
            return None  # duplicate webhook delivery
        db.commit()
        return cur.lastrowid


def recent_messages(sender_id: str, limit: int = 10) -> list[dict]:
    cur = _db().execute(
        "SELECT * FROM messages WHERE sender_id = ? ORDER BY created_at DESC LIMIT ?",
        (sender_id, limit),
    )
    return list(reversed(_rows(cur)))


# ── drafts ───────────────────────────────────────────────────────────────────

def create_draft(sender_id: str, message_id: int | None, draft_text: str,
                 flagged: bool, flag_reason: str | None, crm_summary: str | None) -> int:
    with _lock:
        db = _db()
        cur = db.execute(
            "INSERT INTO drafts (sender_id, message_id, draft_text, flagged, flag_reason, "
            "crm_summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sender_id, message_id, draft_text, int(flagged), flag_reason,
             crm_summary, time.time()),
        )
        db.commit()
        return cur.lastrowid


def get_draft(draft_id: int) -> dict | None:
    cur = _db().execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def resolve_draft(draft_id: int, status: str, final_text: str | None = None) -> None:
    with _lock:
        _db().execute(
            "UPDATE drafts SET status = ?, final_text = ?, resolved_at = ? WHERE id = ?",
            (status, final_text, time.time(), draft_id),
        )
        _db().commit()


def pending_drafts() -> list[dict]:
    cur = _db().execute(
        """SELECT d.*, c.name, c.profile_pic, m.text AS customer_message
           FROM drafts d
           LEFT JOIN conversations c ON c.sender_id = d.sender_id
           LEFT JOIN messages m ON m.id = d.message_id
           WHERE d.status = 'pending'
           ORDER BY d.created_at DESC"""
    )
    return _rows(cur)


def draft_history(limit: int = 100) -> list[dict]:
    cur = _db().execute(
        """SELECT d.*, c.name, c.profile_pic, m.text AS customer_message
           FROM drafts d
           LEFT JOIN conversations c ON c.sender_id = d.sender_id
           LEFT JOIN messages m ON m.id = d.message_id
           WHERE d.status != 'pending'
           ORDER BY d.resolved_at DESC LIMIT ?""",
        (limit,),
    )
    return _rows(cur)


def edited_examples(limit: int = 20) -> list[dict]:
    """Original draft + human edit pairs — future few-shot material."""
    cur = _db().execute(
        """SELECT d.draft_text, d.final_text, m.text AS customer_message
           FROM drafts d LEFT JOIN messages m ON m.id = d.message_id
           WHERE d.status = 'edited' AND d.final_text IS NOT NULL
           ORDER BY d.resolved_at DESC LIMIT ?""",
        (limit,),
    )
    return _rows(cur)


# ── customer cache ───────────────────────────────────────────────────────────

def cache_get(sender_id: str) -> dict | None:
    cur = _db().execute("SELECT data, fetched_at FROM customer_cache WHERE sender_id = ?",
                        (sender_id,))
    row = cur.fetchone()
    if not row:
        return None
    if time.time() - row["fetched_at"] > config.CUSTOMER_CACHE_TTL:
        return None
    return json.loads(row["data"])


def cache_set(sender_id: str, data: dict) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO customer_cache (sender_id, data, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT(sender_id) DO UPDATE SET data = excluded.data, "
            "fetched_at = excluded.fetched_at",
            (sender_id, json.dumps(data), time.time()),
        )
        _db().commit()


# ── push subscriptions ───────────────────────────────────────────────────────

def add_push_subscription(subscription: dict) -> None:
    with _lock:
        _db().execute(
            "INSERT OR IGNORE INTO push_subscriptions (subscription, created_at) VALUES (?, ?)",
            (json.dumps(subscription, sort_keys=True), time.time()),
        )
        _db().commit()


def list_push_subscriptions() -> list[dict]:
    cur = _db().execute("SELECT id, subscription FROM push_subscriptions")
    return [{"id": r["id"], "subscription": json.loads(r["subscription"])}
            for r in cur.fetchall()]


def remove_push_subscription(sub_id: int) -> None:
    with _lock:
        _db().execute("DELETE FROM push_subscriptions WHERE id = ?", (sub_id,))
        _db().commit()
