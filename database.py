"""
database.py — Local SQLite Engine + Proxy-Routed Supabase Sync
"""

import sqlite3
import uuid
import threading
import os
from datetime import date, datetime, timedelta

DB_PATH   = os.getenv("DB_PATH", "tasks.db")
SYNC_URL  = "https://devnest-proxy-server.onrender.com/v1/proxy/sync"
SYNC_HEADERS = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type": "application/json",
}


class Database:
    def __init__(self):
        self._init_db()

    # ── Connection ────────────────────────────────────────────────────────────

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    category    TEXT DEFAULT 'General',
                    priority    TEXT DEFAULT 'Medium',
                    due_date    TEXT,
                    status      TEXT DEFAULT 'pending',
                    is_deleted  INTEGER DEFAULT 0,
                    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
                    completed_at TEXT,
                    notes       TEXT
                )
            """)
            conn.commit()

    # ── Write Operations ──────────────────────────────────────────────────────

    def add_task(self, name, category="General", priority="Medium", due_date=None, notes=None):
        task_id = str(uuid.uuid4())[:8].upper()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tasks (id, name, category, priority, due_date, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, name, category, priority, due_date, notes),
            )
            conn.commit()
        self._background_sync(task_id)
        return task_id

    def update_task(self, task_id, **kwargs):
        allowed = {"name", "category", "priority", "due_date", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id = ?",
                [*updates.values(), task_id],
            )
            conn.commit()
        self._background_sync(task_id)
        return True

    def complete_task(self, task_id):
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'completed', completed_at = datetime('now', 'localtime') WHERE id = ?",
                (task_id,),
            )
            conn.commit()
        self._background_sync(task_id)

    def soft_delete(self, task_id):
        with self._conn() as conn:
            conn.execute("UPDATE tasks SET is_deleted = 1 WHERE id = ?", (task_id,))
            conn.commit()
        self._background_sync(task_id)

    def restore_task(self, task_id):
        with self._conn() as conn:
            conn.execute("UPDATE tasks SET is_deleted = 0 WHERE id = ?", (task_id,))
            conn.commit()
        self._background_sync(task_id)

    # ── Read Operations ───────────────────────────────────────────────────────

    def get_task(self, task_id):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id.upper(),)).fetchone()
        return dict(row) if row else None

    def get_tasks(self, deleted=False, status=None, category=None, search=None):
        query = "SELECT * FROM tasks WHERE is_deleted = ?"
        params = [1 if deleted else 0]

        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        if search:
            query += " AND (name LIKE ? OR notes LIKE ? OR category LIKE ?)"
            s = f"%{search}%"
            params += [s, s, s]

        query += """
            ORDER BY
                CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
                due_date ASC NULLS LAST
        """
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_analytics(self):
        with self._conn() as conn:
            total     = conn.execute("SELECT COUNT(*) FROM tasks WHERE is_deleted = 0").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE is_deleted = 0 AND status = 'completed'").fetchone()[0]
            pending   = conn.execute("SELECT COUNT(*) FROM tasks WHERE is_deleted = 0 AND status = 'pending'").fetchone()[0]
            overdue   = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE is_deleted = 0 AND status = 'pending' AND due_date < date('now') AND due_date IS NOT NULL"
            ).fetchone()[0]
            by_priority = dict(conn.execute(
                "SELECT priority, COUNT(*) FROM tasks WHERE is_deleted = 0 GROUP BY priority"
            ).fetchall())
            by_category = dict(conn.execute(
                "SELECT category, COUNT(*) FROM tasks WHERE is_deleted = 0 GROUP BY category"
            ).fetchall())
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM tasks WHERE is_deleted = 0 GROUP BY status"
            ).fetchall())
            streak = self._calc_streak(conn)

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "overdue": overdue,
            "productivity": round((completed / total * 100) if total > 0 else 0, 1),
            "by_priority": by_priority,
            "by_category": by_category,
            "by_status": by_status,
            "streak": streak,
        }

    def _calc_streak(self, conn):
        rows = conn.execute(
            "SELECT DISTINCT date(completed_at) AS d FROM tasks "
            "WHERE status = 'completed' AND completed_at IS NOT NULL ORDER BY d DESC"
        ).fetchall()
        if not rows:
            return 0
        streak = 0
        check = date.today()
        for row in rows:
            try:
                d = date.fromisoformat(row[0])
            except (ValueError, TypeError):
                continue
            if d >= check - timedelta(days=1):
                streak += 1
                check = d - timedelta(days=1)
            else:
                break
        return streak

    # ── Proxy-Routed Supabase Sync ────────────────────────────────────────────

    def _background_sync(self, task_id):
        t = threading.Thread(target=self._do_sync, args=(task_id,), daemon=True)
        t.start()

    def _do_sync(self, task_id):
        try:
            import requests
            task = self.get_task(task_id)
            if not task:
                return
            payload = {**task, "is_deleted": bool(task["is_deleted"])}
            requests.post(SYNC_URL, json=payload, headers=SYNC_HEADERS, timeout=12)
        except Exception:
            pass
