"""
reminder_worker.py — Detached background process for TaskFlow Pro reminders.

Spawned automatically by main.py on first run.
Runs silently in background — survives after CLI exits.
Shows Windows toast notifications when reminders are due.
"""

import os
import sys
import time
import json
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
WORKER_DIR = Path(__file__).parent          # TaskFlow-Pro folder
PID_FILE   = Path.home() / ".taskflow_reminder.pid"
LOG_FILE   = Path.home() / ".taskflow_reminder.log"

# ── Notification ─────────────────────────────────────────────────────────────

def _notify(title: str, message: str):
    """Show a Windows toast notification. Falls back silently if unavailable."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="TaskFlow Pro",
            timeout=8,
        )
        return
    except Exception:
        pass

    # Fallback: PowerShell toast (no extra library needed)
    try:
        import subprocess
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
        $xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{title}')) | Out-Null
        $xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{message}')) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TaskFlow Pro').Show($toast)
        """
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _log(msg: str):
    """Append a timestamped line to the log file (for debugging)."""
    try:
        from datetime import datetime
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    # Write own PID so main.py can check if we're already alive
    PID_FILE.write_text(str(os.getpid()))
    _log(f"Reminder worker started (PID {os.getpid()})")

    # Make sure imports from TaskFlow-Pro folder work
    sys.path.insert(0, str(WORKER_DIR))

    try:
        from database import Database
        db = Database()
    except Exception as e:
        _log(f"DB init failed: {e}")
        sys.exit(1)

    while True:
        try:
            due = db.get_due_reminders()
            for task in due:
                title = f"🔔 {task['name']}"
                lines = [f"{task.get('category','General')} · {task['priority']}"]
                if task.get("due_date"):
                    due_str = task["due_date"]
                    if task.get("due_time"):
                        due_str += f" at {task['due_time']}"
                    lines.append(f"Due: {due_str}")
                message = "\n".join(lines)

                _notify(title, message)
                _log(f"Fired: {task['name']} ({task['id']})")
                db.mark_reminder_sent(task["id"])

        except Exception as e:
            _log(f"Check error: {e}")

        time.sleep(10)


if __name__ == "__main__":
    main()
