"""
database.py — Local SQLite Engine + Proxy-Routed Supabase Sync
"""

import sqlite3
import uuid
import threading
import os
from datetime import date, datetime, timedelta
from timezone_utils import get_tz, now_local, today_local

DB_PATH   = os.getenv("DB_PATH", "tasks.db")
SYNC_URL  = "https://devnest-proxy-server.onrender.com/v1/proxy/sync"
SYNC_HEADERS = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type": "application/json",
}

# Migrations: run on every startup — safe to re-run (errors silently ignored)
_MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN due_time TEXT",
    "ALTER TABLE tasks ADD COLUMN reminder_at TEXT",
    "ALTER TABLE tasks ADD COLUMN reminder_sent INTEGER DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN recurrence TEXT DEFAULT 'none'",
    "ALTER TABLE tasks ADD COLUMN recurrence_end_date TEXT",
]

VALID_RECURRENCE = {"none", "daily", "weekly", "weekdays", "monthly"}

# Normalize helpers — AI or user may send lowercase
_CAT_MAP  = {c.lower(): c for c in ["Work","Study","Personal","Health","Finance","General"]}
_PRI_MAP  = {p.lower(): p for p in ["High","Medium","Low"]}

def _norm_category(v):  return _CAT_MAP.get((v or "general").lower(), "General")
def _norm_priority(v):  return _PRI_MAP.get((v or "medium").lower(), "Medium")
def _norm_recurrence(v): return v if v in VALID_RECURRENCE else "none"


class Database:
    def __init__(self):
        self._init_db()

    # Connection

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id                  TEXT PRIMARY KEY,
                    name                TEXT NOT NULL,
                    category            TEXT DEFAULT 'General',
                    priority            TEXT DEFAULT 'Medium',
                    due_date            TEXT,
                    due_time            TEXT,
                    status              TEXT DEFAULT 'pending',
                    is_deleted          INTEGER DEFAULT 0,
                    created_at          TEXT DEFAULT (datetime('now', 'localtime')),
                    completed_at        TEXT,
                    notes               TEXT,
                    reminder_at         TEXT,
                    reminder_sent       INTEGER DEFAULT 0,
                    recurrence          TEXT DEFAULT 'none',
                    recurrence_end_date TEXT
                )
            """)
            for sql in _MIGRATIONS:
                try:
                    conn.execute(sql)
                except Exception:
                    pass  # Column already exists — skip silently
            conn.commit()

    # Write Operations

    def add_task(self, name, category="General", priority="Medium",
                 due_date=None, notes=None, due_time=None,
                 reminder_at=None, recurrence="none", recurrence_end_date=None):
        task_id = str(uuid.uuid4())[:8].upper()
        category   = _norm_category(category)
        priority   = _norm_priority(priority)
        recurrence = _norm_recurrence(recurrence)
        # Validate due_date — drop if malformed (UI already warned user)
        if due_date:
            try:
                from datetime import date as _date
                _date.fromisoformat(due_date)   # just validate; past dates are allowed (user confirmed)
            except ValueError:
                due_date = None   # malformed — drop silently
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (id, name, category, priority, due_date, due_time,
                    notes, reminder_at, recurrence, recurrence_end_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, name, category, priority, due_date, due_time,
                 notes, reminder_at, recurrence, recurrence_end_date),
            )
            conn.commit()
        self._background_sync(task_id)
        return task_id

    def update_task(self, task_id, **kwargs):
        allowed = {
            "name", "category", "priority", "due_date", "due_time",
            "notes", "reminder_at", "reminder_sent", "recurrence", "recurrence_end_date",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        # Normalize casing for enum fields
        if "category"   in updates: updates["category"]   = _norm_category(updates["category"])
        if "priority"   in updates: updates["priority"]   = _norm_priority(updates["priority"])
        if "recurrence" in updates: updates["recurrence"] = _norm_recurrence(updates["recurrence"])
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

    def mark_reminder_sent(self, task_id):
        """Mark reminder as fired — won't trigger again."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET reminder_sent = 1 WHERE id = ?",
                (task_id,),
            )
            conn.commit()

    # Read Operations

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
                due_date ASC NULLS LAST,
                due_time ASC NULLS LAST
        """
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_due_reminders(self):
        """
        Returns pending tasks whose reminder_at <= now and reminder_sent = 0.
        Called by the reminder daemon every 30s.
        """
        now = now_local().strftime("%Y-%m-%d %H:%M")
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE is_deleted = 0
                     AND status = 'pending'
                     AND reminder_sent = 0
                     AND reminder_at IS NOT NULL
                     AND reminder_at <= ?""",
                (now,),
            ).fetchall()
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
        check = today_local()
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

    # Proxy-Routed Supabase Sync

    def _background_sync(self, task_id):
        t = threading.Thread(target=self._do_sync, args=(task_id,), daemon=True)
        t.start()

    def _do_sync(self, task_id):
        try:
            import requests
            task = self.get_task(task_id)
            if not task:
                return
            payload = {
                **task,
                "is_deleted": bool(task["is_deleted"]),
                "reminder_sent": bool(task.get("reminder_sent", 0)),
            }
            requests.post(SYNC_URL, json=payload, headers=SYNC_HEADERS, timeout=12)
        except Exception:
            # Sync failures are non-critical; local DB is source of truth
            return
