"""
controller.py — Logic Bridge: Database <-> AI Gateway
"""

from datetime import date
from database import Database
from ai_gateway import AIGateway

# Actions the AI might return that are valid "no-op" responses
_SOFT_PASSTHROUGH_ACTIONS = {
    "general_response", "general_answer", "reply", "text_response",
    "no_action", "none", "chitchat_response", "answer",
}


class TaskController:
    def __init__(self):
        self.db = Database()
        self.ai = AIGateway()

    # Task CRUD────────────────────────────────────────────────────────────

    def add_manual(self, name, category, priority, due_date, notes,
                   due_time=None, reminder_at=None, recurrence="none", recurrence_end_date=None):
        task_id = self.db.add_task(
            name, category, priority, due_date, notes,
            due_time=due_time, reminder_at=reminder_at,
            recurrence=recurrence, recurrence_end_date=recurrence_end_date,
        )
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
            due_time=parsed.get("due_time"),
            reminder_at=parsed.get("reminder_at"),
            recurrence=parsed.get("recurrence", "none"),
            recurrence_end_date=parsed.get("recurrence_end_date"),
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

    def set_reminder(self, task_id, reminder_at: str):
        """Set/update reminder for a task. reminder_at = 'YYYY-MM-DD HH:MM'"""
        task, err = self.get_task(task_id)
        if err:
            return False, err
        self.db.update_task(task_id, reminder_at=reminder_at, reminder_sent=0)
        return True, None

    # Reminder Daemon

    def get_due_reminders(self):
        """Fetch tasks whose reminder time has passed and haven't been notified."""
        return self.db.get_due_reminders()

    def mark_reminder_sent(self, task_id):
        self.db.mark_reminder_sent(task_id)

    # Analytics

    def get_analytics(self):
        return self.db.get_analytics()

    # Intent & Validation

    def classify_intent(self, user_message: str, history=None) -> dict:
        """Fast Haiku intent classifier. Never raises."""
        return self.ai.classify_intent(user_message, history=history)

    def validate_action(self, intent: str, action_name: str | None) -> tuple[bool, str]:
        return self.ai.validate_action(intent, action_name)

    # Prompt Enhancer

    def enhance_prompt(self, user_message: str, history=None, draft=None) -> str:
        return self.ai.enhance_prompt(user_message, history=history, draft=draft)

    # AI Chat

    def chat(
        self,
        user_message: str,
        history=None,
        draft: dict = None,
        intent_info: dict = None,
        location: str = None,
    ):
        task_stats = self.db.get_analytics()

        _TASK_ID_INTENTS = {"complete_task", "delete_task", "edit_task", "search_tasks"}
        task_list = None
        if intent_info and intent_info.get("intent") in _TASK_ID_INTENTS:
            task_list = self.db.get_tasks(status="pending")

        return self.ai.chat(
            user_message,
            history=history,
            draft=draft,
            intent_info=intent_info,
            task_stats=task_stats,
            task_list=task_list,
            location=location,
        )

    def handle_chat_action(self, action_dict: dict, current_draft: dict = None):
        """
        Dispatch a structured action from the AI.
        Returns (result_type, result_data, error, new_draft)
        """
        if not action_dict:
            return "error", None, "No action.", current_draft

        action = action_dict.get("action", "")
        data   = action_dict.get("data", {})
        draft  = dict(current_draft or {})

        if action.lower() in _SOFT_PASSTHROUGH_ACTIONS:
            return "passthrough", None, None, draft

        if action == "update_draft":
            draft.update({k: v for k, v in data.items() if v})
            return "draft_updated", draft, None, draft

        elif action == "clear_draft":
            return "draft_cleared", {}, None, {}

        elif action == "confirm_task":
            preview = {**draft, **{k: v for k, v in data.items() if v}}
            preview.setdefault("priority", "Medium")
            preview.setdefault("category", "General")
            preview.setdefault("recurrence", "none")
            return "confirm_preview", preview, None, draft

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
                due_time=merged.get("due_time"),
                reminder_at=merged.get("reminder_at"),
                recurrence=merged.get("recurrence", "none"),
                recurrence_end_date=merged.get("recurrence_end_date"),
            )
            task, _ = self.get_task(task_id)
            return "task_created", task, None, {}

        elif action == "search_tasks":
            tasks = self.db.get_tasks(search=data.get("query", ""))
            return "task_list", tasks, None, draft

        elif action == "list_tasks":
            tasks = self.db.get_tasks(status=data.get("status"), category=data.get("category"))
            pf    = data.get("priority")
            if pf:
                tasks = [t for t in tasks if t["priority"] == pf]
            return "task_list", tasks, None, draft

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

        elif action == "set_reminder":
            tid         = str(data.get("task_id", "")).upper().strip()
            reminder_at = data.get("reminder_at", "").strip()
            if not tid or not reminder_at:
                return "error", None, "Task ID and reminder time required.", draft
            ok, err = self.set_reminder(tid, reminder_at)
            if not ok:
                return "error", None, err, draft
            task, _ = self.get_task(tid)
            return "reminder_set", task, None, draft

        elif action == "complete_task":
            tid = str(data.get("task_id", "")).upper().strip()
            if not tid:
                return "error", None, "Task ID required.", draft
            ok, err = self.complete_task(tid)
            if not ok:
                matches = self.db.get_tasks(search=tid, status="pending") if tid else []
                if not matches:
                    raw_tid = str(data.get("task_id", "")).strip()
                    matches = self.db.get_tasks(search=raw_tid, status="pending")
                if matches:
                    tid = matches[0]["id"]
                    ok, err = self.complete_task(tid)
            if not ok:
                return "error", None, err, draft
            task, _ = self.get_task(tid)
            return "task_completed", task, None, draft

        elif action == "delete_task":
            tid = str(data.get("task_id", "")).upper().strip()
            if not tid:
                return "error", None, "Task ID required.", draft
            ok, err = self.delete_task(tid)
            if not ok:
                return "error", None, err, draft
            return "task_deleted", {"id": tid}, None, draft

        elif action == "show_analytics":
            return "analytics", self.get_analytics(), None, draft

        else:
            print(f"  [controller] unknown action '{action}' — skipping silently", flush=True)
            return "passthrough", None, None, draft

    # AI Features

    def optimize_schedule(self):
        """Single-shot schedule (used by chat /optimize slash command)."""
        pending = self.db.get_tasks(status="pending")
        if not pending:
            return None, "No pending tasks to optimize."
        return self.ai.optimize_schedule(pending)

    def generate_schedule_variants(self, goal, start_time, end_time, deadline_task):
        """
        Generate 3 schedule variants in parallel for the interactive optimize flow.
        Returns list of (mode_name, schedule_text | None, error | None).
        """
        import threading
        pending = self.db.get_tasks(status="pending")
        if not pending:
            return []

        MODES = [
            ("Deep Work Mode",  "maximum focus blocks, minimal interruptions, hardest tasks first"),
            ("Balanced Mode",   "mix of deep work and admin tasks, energy-aware pacing"),
            ("Quick Wins Mode", "short tasks first to build momentum, then deeper work blocks"),
        ]

        results = [None] * len(MODES)

        def _gen(idx, mode_name, mode_desc):
            sched, err = self.ai.generate_schedule_variant(
                pending, goal, start_time, end_time, deadline_task, mode_name, mode_desc
            )
            results[idx] = (mode_name, sched, err)

        threads = [
            threading.Thread(target=_gen, args=(i, name, desc), daemon=True)
            for i, (name, desc) in enumerate(MODES)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return [r for r in results if r is not None]

    def get_motivation(self):
        return self.ai.get_motivation(self.db.get_analytics())

    # Export

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
            due  = t.get("due_date") or "no date"
            if t.get("due_time"):
                due += f" {t['due_time']}"
            recur = f" [{t['recurrence']}]" if t.get("recurrence") and t["recurrence"] != "none" else ""
            lines.append(
                f"- [{icon}] **{t['name']}** | {t['priority']} | {t.get('category','General')} | {due}{recur}"
            )
            if t.get("notes"):
                lines.append(f"  > {t['notes']}")
            if t.get("reminder_at") and not t.get("reminder_sent"):
                lines.append(f"  🔔 Reminder: {t['reminder_at']}")
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
