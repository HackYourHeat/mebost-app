"""
db.py — MEBOST Hải Đăng V2 (Clean)
Dual-mode: SQLite (local/Railway Volume) hoặc PostgreSQL (Railway Plugin).
"""
from __future__ import annotations
import os, sqlite3
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_PG      = bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = "/data" if os.path.isdir("/data") else os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "mebost.db")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def ensure_data_dir() -> None:
    if not _USE_PG:
        os.makedirs(DATA_DIR, exist_ok=True)

def db_mode() -> str:
    return "postgresql" if _USE_PG else "sqlite"

# ── PostgreSQL wrapper ──────────────────────────────────────────────────────

class _PGRow:
    def __init__(self, row, desc):
        self._row  = row
        self._keys = [d[0] for d in desc] if desc else []
    def __getitem__(self, key):
        if isinstance(key, int): return self._row[key]
        return self._row[self._keys.index(key)]
    def get(self, key, default=None):
        try: return self[key]
        except (ValueError, IndexError): return default
    def keys(self): return self._keys
    def __iter__(self): return iter(self._row)

class _PGCursor:
    def __init__(self, cur): self._cur = cur
    def execute(self, sql, params=()):
        self._cur.execute(sql.replace("?", "%s"), params); return self
    def fetchone(self):
        r = self._cur.fetchone()
        return _PGRow(r, self._cur.description) if r else None
    def fetchall(self):
        return [_PGRow(r, self._cur.description) for r in self._cur.fetchall()]
    def executescript(self, sql):
        for stmt in sql.split(";"): 
            s = stmt.strip()
            if s: self._cur.execute(s)
        return self
    @property
    def lastrowid(self): return self._cur.fetchone()[0] if self._cur.rowcount else None
    @property
    def rowcount(self): return self._cur.rowcount

class _PGConn:
    def __init__(self, conn): self._conn = conn
    def cursor(self): return _PGCursor(self._conn.cursor())
    def execute(self, sql, params=()):
        cur = _PGCursor(self._conn.cursor()); cur.execute(sql, params); return cur
    def executescript(self, sql):
        cur = _PGCursor(self._conn.cursor()); cur.executescript(sql); return cur
    def commit(self): self._conn.commit()
    def close(self): self._conn.close()
    def __enter__(self): return self
    def __exit__(self, *a): self._conn.close()

def get_db():
    if _USE_PG:
        import psycopg2
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return _PGConn(conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

# ── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    display_name   TEXT,
    language       TEXT,
    device_hash    TEXT,
    memory_enabled INTEGER DEFAULT 1,
    is_guest       INTEGER DEFAULT 1,
    account_id     TEXT,
    guest_expires_at TEXT,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  TEXT PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    email_verified      INTEGER DEFAULT 0,
    verification_token  TEXT,
    verification_expires TEXT,
    created_at          TEXT,
    is_active           INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT,
    client_type TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT,
    session_id       TEXT,
    role             TEXT,
    message_text     TEXT,
    language         TEXT,
    timestamp        TEXT,
    response_time_ms INTEGER,
    error_flag       INTEGER DEFAULT 0,
    emotion_label    TEXT,
    emotion_intensity INTEGER,
    intent_label     TEXT,
    importance_score INTEGER,
    memory_saved     INTEGER DEFAULT 0,
    deleted_by_user  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_nodes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT,
    memory_type      TEXT,
    memory_text      TEXT,
    source_message_id INTEGER,
    importance_score INTEGER,
    status           TEXT DEFAULT 'active',
    created_at       TEXT,
    updated_at       TEXT,
    last_used_at     TEXT,
    deleted_flag     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_pronoun_profile (
    user_id      TEXT PRIMARY KEY,
    ai_pronoun   TEXT DEFAULT 'mình',
    user_pronoun TEXT DEFAULT 'bạn',
    source       TEXT DEFAULT 'default',
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS user_trust (
    user_id    TEXT PRIMARY KEY,
    trust      REAL DEFAULT 0.30,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS rate_limits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS signup_rate_limits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT,
    created_at TEXT
);
"""

def _pg_schema(s: str) -> str:
    return s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

def init_db() -> None:
    ensure_data_dir()
    db = get_db()
    db.executescript(_pg_schema(_SCHEMA) if _USE_PG else _SCHEMA)
    db.commit()
    db.close()
