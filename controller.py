"""
controller.py — Logic Bridge: Database ↔ AI Gateway
"""

from datetime import date
from database import Database
from ai_gateway import AIGateway


class TaskController:
    def __init__(self):
        self.db = Database()
        self.ai = AIGateway()

    # ── Task CRUD ─────────────────────────────────────────────────────────────

    def add_manual(self, name, category, priority, due_date, notes):
        task_id = self.db.add_task(name, category, priority, due_date, notes)
        return task_id, None

    def add_ai(self, natural_text):
        parsed, err = self.ai.parse_task(natural_text)
        if err or not parsed:
            return None, None, err or "AI parsing failed."
        task_id = self.db.add_task(
            name=parsed.get("name") or natural_text[:60],
            category=parsed.get("category", "General"),
            priority=parsed.get("priority", "Medium"),
            due_date=parsed.get("due_date"),
            notes=parsed.get("notes"),
        )
        return task_id, parsed, None

    def get_task(self, task_id):
        task = self.db.get_task(task_id)
        if not task:
            return None, "Task not found."
        return task, None

    def list_tasks(self, status=None, category=None, search=None):
        return self.db.get_tasks(status=status, category=category, search=search)

    def list_bin(self):
        return self.db.get_tasks(deleted=True)

    def complete_task(self, task_id):
        task, err = self.get_task(task_id)
        if err:
            return False, err
        if task["is_deleted"]:
            return False, "Task is in recycle bin. Restore it first."
        if task["status"] == "completed":
            return False, "Task already marked as completed."
        self.db.complete_task(task_id)
        return True, None

    def delete_task(self, task_id):
        task, err = self.get_task(task_id)
        if err:
            return False, err
        if task["is_deleted"]:
            return False, "Task already in recycle bin."
        self.db.soft_delete(task_id)
        return True, None

    def restore_task(self, task_id):
        task, err = self.get_task(task_id)
        if err:
            return False, err
        if not task["is_deleted"]:
            return False, "Task is not in recycle bin."
        self.db.restore_task(task_id)
        return True, None

    def edit_task(self, task_id, **kwargs):
        task, err = self.get_task(task_id)
        if err:
            return False, err
        self.db.update_task(task_id, **kwargs)
        return True, None

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_analytics(self):
        return self.db.get_analytics()

    # ── AI Features ───────────────────────────────────────────────────────────

    def optimize_schedule(self):
        pending = self.db.get_tasks(status="pending")
        if not pending:
            return None, "No pending tasks to optimize."
        return self.ai.optimize_schedule(pending)

    def get_motivation(self):
        stats = self.db.get_analytics()
        return self.ai.get_motivation(stats)

    # ── Export ────────────────────────────────────────────────────────────────

    def export_report(self):
        tasks = self.db.get_tasks()
        stats = self.db.get_analytics()
        today = date.today().isoformat()

        lines = [
            "# TaskFlow Pro — Daily Report",
            f"**Generated:** {today}",
            "",
            "## Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Tasks | {stats['total']} |",
            f"| Completed   | {stats['completed']} |",
            f"| Pending     | {stats['pending']} |",
            f"| Overdue     | {stats['overdue']} |",
            f"| Productivity| {stats['productivity']}% |",
            f"| Streak      | {stats['streak']} days 🔥 |",
            "",
            "## Task List",
        ]

        for t in tasks:
            icon = "✅" if t["status"] == "completed" else "🔴" if self._is_overdue(t) else "⏳"
            lines.append(
                f"- {icon} **{t['name']}** | `{t['priority']}` | {t.get('category','General')} | Due: {t.get('due_date') or '—'}"
            )
            if t.get("notes"):
                lines.append(f"  > {t['notes']}")

        filename = f"report_{today}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filename

    def _is_overdue(self, task):
        if not task.get("due_date") or task["status"] == "completed":
            return False
        try:
            return date.fromisoformat(task["due_date"]) < date.today()
        except ValueError:
            return False
