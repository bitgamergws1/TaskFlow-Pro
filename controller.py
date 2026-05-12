"""
controller.py — Logic Bridge: Database <-> AI Gateway
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
            return False, "Task is in recycle bin."
        if task["status"] == "completed":
            return False, "Already completed."
        self.db.complete_task(task_id)
        return True, None

    def delete_task(self, task_id):
        task, err = self.get_task(task_id)
        if err:
            return False, err
        if task["is_deleted"]:
            return False, "Already in recycle bin."
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

    # ── AI Chat ───────────────────────────────────────────────────────────────

    def chat(self, user_message: str, history=None, draft: dict = None):
        """Returns (reply, action, error)."""
        return self.ai.chat(user_message, history=history, draft=draft)

    def handle_chat_action(self, action_dict: dict, current_draft: dict = None):
        """
        Dispatch a structured action from the AI.
        Returns (result_type, result_data, error, new_draft)

        result_type values:
            draft_updated | confirm_preview | task_created | task_list |
            task_edited   | task_completed  | task_deleted | analytics |
            draft_cleared | error
        """
        if not action_dict:
            return "error", None, "No action.", current_draft

        action = action_dict.get("action", "")
        data   = action_dict.get("data", {})
        draft  = dict(current_draft or {})

        # ── update_draft ──────────────────────────────────────────────────────
        if action == "update_draft":
            draft.update({k: v for k, v in data.items() if v})
            return "draft_updated", draft, None, draft

        # ── clear_draft ───────────────────────────────────────────────────────
        elif action == "clear_draft":
            return "draft_cleared", {}, None, {}

        # ── confirm_task (preview before save) ────────────────────────────────
        elif action == "confirm_task":
            # Merge current draft with what AI suggests
            preview = {**draft, **{k: v for k, v in data.items() if v}}
            preview.setdefault("priority", "Medium")
            preview.setdefault("category", "General")
            return "confirm_preview", preview, None, draft

        # ── create_task ───────────────────────────────────────────────────────
        elif action == "create_task":
            merged = {**draft, **{k: v for k, v in data.items() if v}}
            name   = merged.get("name", "").strip()
            if not name:
                return "error", None, "Task name is required.", draft
            task_id = self.db.add_task(
                name=name,
                category=merged.get("category", "General"),
                priority=merged.get("priority", "Medium"),
                due_date=merged.get("due_date"),
                notes=merged.get("notes"),
            )
            task, _ = self.get_task(task_id)
            return "task_created", task, None, {}   # clear draft on success

        # ── search_tasks ──────────────────────────────────────────────────────
        elif action == "search_tasks":
            tasks = self.db.get_tasks(search=data.get("query", ""))
            return "task_list", tasks, None, draft

        # ── list_tasks ────────────────────────────────────────────────────────
        elif action == "list_tasks":
            tasks = self.db.get_tasks(status=data.get("status"), category=data.get("category"))
            pf    = data.get("priority")
            if pf:
                tasks = [t for t in tasks if t["priority"] == pf]
            return "task_list", tasks, None, draft

        # ── edit_task ─────────────────────────────────────────────────────────
        elif action == "edit_task":
            tid = str(data.get("task_id", "")).upper().strip()
            upd = data.get("updates", {})
            if not tid:
                return "error", None, "Task ID required.", draft
            ok, err = self.edit_task(tid, **upd)
            if not ok:
                return "error", None, err, draft
            task, _ = self.get_task(tid)
            return "task_edited", task, None, draft

        # ── complete_task ─────────────────────────────────────────────────────
        elif action == "complete_task":
            tid = str(data.get("task_id", "")).upper().strip()
            if not tid:
                return "error", None, "Task ID required.", draft
            ok, err = self.complete_task(tid)
            if not ok:
                return "error", None, err, draft
            task, _ = self.get_task(tid)
            return "task_completed", task, None, draft

        # ── delete_task ───────────────────────────────────────────────────────
        elif action == "delete_task":
            tid = str(data.get("task_id", "")).upper().strip()
            if not tid:
                return "error", None, "Task ID required.", draft
            ok, err = self.delete_task(tid)
            if not ok:
                return "error", None, err, draft
            return "task_deleted", {"id": tid}, None, draft

        # ── show_analytics ────────────────────────────────────────────────────
        elif action == "show_analytics":
            return "analytics", self.get_analytics(), None, draft

        else:
            return "error", None, f"Unknown action: '{action}'", draft

    # ── AI Features ───────────────────────────────────────────────────────────

    def optimize_schedule(self):
        pending = self.db.get_tasks(status="pending")
        if not pending:
            return None, "No pending tasks to optimize."
        return self.ai.optimize_schedule(pending)

    def get_motivation(self):
        return self.ai.get_motivation(self.db.get_analytics())

    # ── Export ────────────────────────────────────────────────────────────────

    def export_report(self):
        tasks = self.db.get_tasks()
        stats = self.db.get_analytics()
        today = date.today().isoformat()
        lines = [
            "# TaskFlow Pro -- Daily Report",
            f"**Generated:** {today}", "",
            "## Summary",
            "| Metric | Value |", "|--------|-------|",
            f"| Total       | {stats['total']} |",
            f"| Completed   | {stats['completed']} |",
            f"| Pending     | {stats['pending']} |",
            f"| Overdue     | {stats['overdue']} |",
            f"| Productivity| {stats['productivity']}% |",
            f"| Streak      | {stats['streak']} days |",
            "", "## Tasks",
        ]
        for t in tasks:
            icon = "x" if t["status"] == "completed" else "!" if self._is_overdue(t) else " "
            lines.append(
                f"- [{icon}] **{t['name']}** | {t['priority']} | {t.get('category','General')} | {t.get('due_date') or 'no date'}"
            )
            if t.get("notes"):
                lines.append(f"  > {t['notes']}")
        fn = f"report_{today}.md"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return fn

    def _is_overdue(self, task):
        if not task.get("due_date") or task["status"] == "completed":
            return False
        try:
            return date.fromisoformat(task["due_date"]) < date.today()
        except ValueError:
            return False
