"""
db.py — MEBOST Hải Đăng V2.4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dual-mode database layer:

  MODE A — SQLite  (mặc định, local + Railway Volume)
    /data/mebost.db  khi Railway Volume mount tại /data
    ./data/mebost.db khi local

  MODE B — PostgreSQL  (khi có DATABASE_URL)
    Railway tự inject DATABASE_URL khi add Postgres plugin.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations
import os, sqlite3
from datetime import datetime, timezone
from typing import Any

# Railway inject "postgres://" nhưng psycopg2 cần "postgresql://"
_raw_db_url = os.environ.get("DATABASE_URL", "")
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = "postgresql://" + _raw_db_url[len("postgres://"):]
    os.environ["DATABASE_URL"] = _raw_db_url
DATABASE_URL = _raw_db_url
_USE_PG      = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql://"))

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

# ── Wrapper ───────────────────────────────────────

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
    def __init__(self, cur): self._cur = cur; self._last = None
    def execute(self, sql, params=()):
        self._cur.execute(sql.replace("?","%s"), params)
        return self
    def fetchone(self):
        r = self._cur.fetchone()
        return _PGRow(r, self._cur.description) if r else None
    def fetchall(self):
        return [_PGRow(r, self._cur.description) for r in self._cur.fetchall()]
    @property
    def lastrowid(self):
        try:
            self._cur.execute("SELECT lastval()")
            return self._cur.fetchone()[0]
        except Exception: return None
    def __iter__(self): return iter(self.fetchall())
    def __getitem__(self, i): return self.fetchall()[i]

class DBConn:
    def __init__(self, conn, is_pg=False):
        self._conn = conn; self._is_pg = is_pg
    def _adapt(self, sql): return sql.replace("?","%s") if self._is_pg else sql
    def execute(self, sql, params=()):
        if self._is_pg:
            cur = _PGCursor(self._conn.cursor())
            cur.execute(sql, params)
            return cur
        return self._conn.execute(self._adapt(sql), params)
    def executescript(self, sql):
        if self._is_pg:
            cur = self._conn.cursor()
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    try: cur.execute(stmt)
                    except Exception: self._conn.rollback()
            self._conn.commit()
        else:
            self._conn.executescript(sql)
    def commit(self): self._conn.commit()
    def close(self):  self._conn.close()
    def cursor(self):
        return _PGCursor(self._conn.cursor()) if self._is_pg else self._conn.cursor()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

def get_db() -> DBConn:
    if _USE_PG:
        try: import psycopg2
        except ImportError as e:
            raise RuntimeError("psycopg2-binary chưa install. Thêm vào requirements.txt") from e
        url = DATABASE_URL.replace("postgres://","postgresql://",1)
        conn = psycopg2.connect(url)
        conn.autocommit = False
        return DBConn(conn, is_pg=True)
    else:
        ensure_data_dir()
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return DBConn(conn, is_pg=False)

# ── Schema ────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, display_name TEXT, language TEXT, device_hash TEXT, memory_enabled INTEGER DEFAULT 1, is_guest INTEGER DEFAULT 1, account_id TEXT, guest_expires_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, user_id TEXT, client_type TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, session_id TEXT, role TEXT, message_text TEXT, language TEXT, timestamp TEXT, response_time_ms INTEGER, error_flag INTEGER, emotion_label TEXT, emotion_intensity INTEGER, intent_label TEXT, importance_score INTEGER, is_memory_candidate INTEGER DEFAULT 0, memory_saved INTEGER DEFAULT 0, deleted_by_user INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS emotion_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, session_id TEXT, emotion TEXT, timestamp TEXT);
CREATE TABLE IF NOT EXISTS memory_nodes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, memory_type TEXT, memory_text TEXT, source_message_id INTEGER, importance_score INTEGER, confidence_score REAL, status TEXT, created_at TEXT, updated_at TEXT, last_used_at TEXT, deleted_flag INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS memory_summaries (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, summary_text TEXT, summary_version INTEGER, source_memory_count INTEGER, created_at TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS intent_state (user_id TEXT PRIMARY KEY, emotion_momentum INTEGER DEFAULT 0, trust_level TEXT DEFAULT 'medium', memory_summary TEXT, memory_enabled INTEGER DEFAULT 1, last_interaction TEXT, last_mode TEXT DEFAULT 'normal', updated_at TEXT);
CREATE TABLE IF NOT EXISTS rate_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS memory_decay_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, memory_node_id INTEGER, old_importance_score INTEGER, new_importance_score INTEGER, decayed_at TEXT);
CREATE TABLE IF NOT EXISTS life_nodes (node_id TEXT PRIMARY KEY, user_id TEXT, node_type TEXT, label TEXT, importance INTEGER DEFAULT 5, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS life_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, source_node TEXT, target_node TEXT, relation TEXT, weight REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS life_threads (thread_id TEXT, user_id TEXT, name TEXT, emotional_weight REAL, last_activity TEXT, node_count INTEGER DEFAULT 0, PRIMARY KEY (thread_id, user_id));
CREATE TABLE IF NOT EXISTS memory_thread_links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, thread_id TEXT, node_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, email_verified INTEGER DEFAULT 0, verification_token TEXT, verification_expires TEXT, created_at TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS signup_rate_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS user_pronoun_profile (user_id TEXT PRIMARY KEY, pronoun_mode TEXT DEFAULT 'neutral_default', ai_pronoun TEXT DEFAULT 'mình', user_pronoun TEXT DEFAULT 'bạn', source TEXT DEFAULT 'default', updated_at TEXT);
CREATE TABLE IF NOT EXISTS user_tone_numeric (user_id TEXT PRIMARY KEY, reply_length REAL DEFAULT 0.50, reflection_level REAL DEFAULT 0.50, question_style REAL DEFAULT 0.50, warmth_level REAL DEFAULT 0.55, updated_at TEXT);
CREATE TABLE IF NOT EXISTS user_bio_state (user_id TEXT PRIMARY KEY, heartbeat_rate REAL DEFAULT 70, breath_phase TEXT DEFAULT 'exhale', conversation_depth REAL DEFAULT 0.0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS user_internal_state (user_id TEXT PRIMARY KEY, arousal REAL DEFAULT 0.0, calm REAL DEFAULT 0.5, pressure REAL DEFAULT 0.0, trust REAL DEFAULT 0.3, depth REAL DEFAULT 0.0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS user_preferences (user_id TEXT PRIMARY KEY, listening_style TEXT DEFAULT 'gentle_companion', updated_at TEXT);
CREATE TABLE IF NOT EXISTS user_tone_profile (user_id TEXT PRIMARY KEY, reply_length TEXT DEFAULT 'medium', reflection_level TEXT DEFAULT 'medium', question_style TEXT DEFAULT 'gentle', advice_style TEXT DEFAULT 'ask_first', warmth_level TEXT DEFAULT 'warm', updated_at TEXT);
CREATE TABLE IF NOT EXISTS personality_profile (user_id TEXT PRIMARY KEY, empathy_level REAL DEFAULT 0.7, question_frequency REAL DEFAULT 0.5, reflection_depth REAL DEFAULT 0.5, guidance_strength REAL DEFAULT 0.2, warmth_level REAL DEFAULT 0.7, updated_at TEXT);
CREATE TABLE IF NOT EXISTS conversation_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, session_id TEXT, ai_message_id INTEGER, feedback_text TEXT, created_at TEXT);
"""

def _pg_schema(s): return s.replace("INTEGER PRIMARY KEY AUTOINCREMENT","SERIAL PRIMARY KEY")

def init_db():
    ensure_data_dir()
    db = get_db()
    db.executescript(_pg_schema(_SCHEMA) if _USE_PG else _SCHEMA)
    db.commit(); db.close()

_MIGRATIONS = [
    ("users","is_guest",        "ALTER TABLE users ADD COLUMN is_guest INTEGER DEFAULT 1"),
    ("users","account_id",      "ALTER TABLE users ADD COLUMN account_id TEXT"),
    ("users","guest_expires_at","ALTER TABLE users ADD COLUMN guest_expires_at TEXT"),
]

def migrate_db():
    db = get_db()
    for table, col, sql in _MIGRATIONS:
        try:
            if _USE_PG:
                cur = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name=? AND column_name=?",(table,col))
                if not cur.fetchone(): db.execute(sql); db.commit()
            else:
                cols=[r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
                if col not in cols: db.execute(sql); db.commit()
        except Exception: pass
    db.close()

def migrate_accounts_schema():
    ensure_data_dir()
    db = get_db()
    sql = """
        CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, email_verified INTEGER DEFAULT 0, verification_token TEXT, verification_expires TEXT, created_at TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS signup_rate_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS user_pronoun_profile (user_id TEXT PRIMARY KEY, pronoun_mode TEXT DEFAULT 'neutral_default', ai_pronoun TEXT DEFAULT 'mình', user_pronoun TEXT DEFAULT 'bạn', source TEXT DEFAULT 'default', updated_at TEXT);
        CREATE TABLE IF NOT EXISTS user_tone_numeric (user_id TEXT PRIMARY KEY, reply_length REAL DEFAULT 0.50, reflection_level REAL DEFAULT 0.50, question_style REAL DEFAULT 0.50, warmth_level REAL DEFAULT 0.55, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS user_bio_state (user_id TEXT PRIMARY KEY, heartbeat_rate REAL DEFAULT 70, breath_phase TEXT DEFAULT 'exhale', conversation_depth REAL DEFAULT 0.0, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS user_internal_state (user_id TEXT PRIMARY KEY, arousal REAL DEFAULT 0.0, calm REAL DEFAULT 0.5, pressure REAL DEFAULT 0.0, trust REAL DEFAULT 0.3, depth REAL DEFAULT 0.0, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS personality_profile (user_id TEXT PRIMARY KEY, empathy_level REAL DEFAULT 0.7, question_frequency REAL DEFAULT 0.5, reflection_depth REAL DEFAULT 0.5, guidance_strength REAL DEFAULT 0.2, warmth_level REAL DEFAULT 0.7, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS memory_thread_links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, thread_id TEXT, node_id INTEGER, created_at TEXT);
    """
    db.executescript(_pg_schema(sql) if _USE_PG else sql)
    db.commit(); db.close()

def migrate_v13_schema():
    ensure_data_dir()
    db = get_db()
    sql = """
        CREATE TABLE IF NOT EXISTS memory_thread_links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, thread_id TEXT, node_id INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS user_preferences (user_id TEXT PRIMARY KEY, listening_style TEXT DEFAULT 'gentle_companion', updated_at TEXT);
        CREATE TABLE IF NOT EXISTS user_tone_profile (user_id TEXT PRIMARY KEY, reply_length TEXT DEFAULT 'medium', reflection_level TEXT DEFAULT 'medium', question_style TEXT DEFAULT 'gentle', advice_style TEXT DEFAULT 'ask_first', warmth_level TEXT DEFAULT 'warm', updated_at TEXT);
        CREATE TABLE IF NOT EXISTS conversation_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, session_id TEXT, ai_message_id INTEGER, feedback_text TEXT, created_at TEXT);
    """
    db.executescript(_pg_schema(sql) if _USE_PG else sql)
    db.commit(); db.close()
