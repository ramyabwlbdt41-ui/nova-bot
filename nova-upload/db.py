# -*- coding: utf-8 -*-
"""قاعدة البيانات — sqlite بسيطة بدون مكتبات خارجية"""

import sqlite3
import time
from contextlib import contextmanager
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    mode        TEXT    NOT NULL DEFAULT 'chat',
    banned      INTEGER NOT NULL DEFAULT 0,
    day         TEXT    NOT NULL DEFAULT '',
    used_today  INTEGER NOT NULL DEFAULT 0,
    used_total  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role    TEXT    NOT NULL,
    content TEXT    NOT NULL,
    ts      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        with self._c() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _c(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ================= المستخدمون =================
    def ensure_user(self, user_id: int, username: str, first_name: str):
        """يرجع (الصف, هل هو مستخدم جديد)"""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._c() as con:
            row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            is_new = row is None
            if is_new:
                con.execute(
                    "INSERT INTO users(user_id, username, first_name, created_at) "
                    "VALUES(?,?,?,?)",
                    (user_id, username, first_name, now),
                )
            else:
                con.execute(
                    "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                    (username, first_name, user_id),
                )
            row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row, is_new

    def get_user(self, user_id: int):
        with self._c() as con:
            return con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

    def is_banned(self, user_id: int) -> bool:
        row = self.get_user(user_id)
        return bool(row and row["banned"])

    def set_mode(self, user_id: int, mode: str):
        with self._c() as con:
            con.execute("UPDATE users SET mode=? WHERE user_id=?", (mode, user_id))

    def set_banned(self, user_id: int, banned: bool):
        with self._c() as con:
            con.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))

    def consume(self, user_id: int, limit: int):
        """يسجل رسالة جديدة. يرجع (مسموح؟, المستخدم اليوم, الحد)"""
        today = date.today().isoformat()
        with self._c() as con:
            row = con.execute(
                "SELECT day, used_today FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            if not row:
                return False, 0, limit
            used = row["used_today"] if row["day"] == today else 0
            if used >= limit:
                return False, used, limit
            con.execute(
                "UPDATE users SET day=?, used_today=?, used_total=used_total+1 WHERE user_id=?",
                (today, used + 1, user_id),
            )
        return True, used + 1, limit

    def today_usage(self, user_id: int) -> int:
        today = date.today().isoformat()
        row = self.get_user(user_id)
        if not row:
            return 0
        return row["used_today"] if row["day"] == today else 0

    # ================= الذاكرة =================
    def add_message(self, user_id: int, role: str, content: str):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._c() as con:
            con.execute(
                "INSERT INTO messages(user_id, role, content, ts) VALUES(?,?,?,?)",
                (user_id, role, content, now),
            )

    def history(self, user_id: int, limit: int):
        with self._c() as con:
            rows = con.execute(
                "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def reset_history(self, user_id: int):
        with self._c() as con:
            con.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

    # ================= الإحصائيات =================
    def stats(self) -> dict:
        today = date.today().isoformat()
        with self._c() as con:
            users = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            active = con.execute(
                "SELECT COUNT(*) AS n FROM users WHERE day=?", (today,)
            ).fetchone()["n"]
            total = con.execute(
                "SELECT COALESCE(SUM(used_total),0) AS n FROM users"
            ).fetchone()["n"]
            today_msgs = con.execute(
                "SELECT COALESCE(SUM(used_today),0) AS n FROM users WHERE day=?", (today,)
            ).fetchone()["n"]
        return {"users": users, "active": active, "total": total, "today": today_msgs}

    def all_user_ids(self):
        with self._c() as con:
            return [r["user_id"] for r in con.execute("SELECT user_id FROM users").fetchall()]
