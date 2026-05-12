"""
ai_gateway.py — Multi-Model AI Routing via DevNest Proxy
"""

import json
import requests
from datetime import date

PROXY_URL = "https://devnest-proxy-server.onrender.com/v1/proxy/ai"
HEADERS   = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type":    "application/json",
}

EXPIRY  = date(2026, 5, 20)
CLAUDE  = "claude-haiku-4-5-20251001"
DEEPSHI = "deepshi-r2"

ACTION_TAG = "TASKFLOW_ACTION:"

CHAT_SYSTEM = """You are TaskFlow AI — a sharp, no-filler productivity assistant inside a terminal task manager.

TODAY: {today}

=== LANGUAGE RULE (CRITICAL) ===
Detect the language/style of each user message and reply in the EXACT same language.
- English only → English only
- Hindi (Devanagari) → Hindi
- Hinglish (Hindi words in Roman script) → Hinglish
- Mix → match their mix
Never switch language on your own.

=== CURRENT TASK DRAFT ===
{draft_context}

=== DRAFT RULES ===
- DO NOT ask again for fields already in the draft above.
- Ask for missing fields 1-2 at a time. Don't dump all questions at once.
- If user switches topic mid-creation: answer them, then gently remind about the unfinished task.
- Once you have at least the NAME, you may apply defaults (priority: Medium, category: General) and confirm.
- Emit "update_draft" whenever user gives any task field, even partially.
- Emit "confirm_task" to show preview BEFORE saving when all fields are ready.
- Emit "create_task" only after user confirms the preview or clearly says to save.
- Emit "clear_draft" if user explicitly abandons the current task.

=== OTHER ACTIONS ===
search_tasks | list_tasks | edit_task | complete_task | delete_task | show_analytics

=== ACTION FORMAT ===
Append exactly ONE JSON block at the very END of your reply — nothing after it:

TASKFLOW_ACTION:{"action":"ACTION_NAME","data":{...}}

Action reference:
  update_draft   → data: {name?, priority?, due_date?, category?, notes?}
  confirm_task   → data: full task fields to preview (shows confirm prompt to user)
  create_task    → data: {name, priority, due_date, category, notes?}
  clear_draft    → data: {}
  search_tasks   → data: {query}
  list_tasks     → data: {status?, category?, priority?}
  edit_task      → data: {task_id, updates:{field:value,...}}
  complete_task  → data: {task_id}
  delete_task    → data: {task_id}
  show_analytics → data: {}

=== STYLE ===
- 1-2 sentences unless explaining something complex.
- No "Certainly!", "Of course!", "Great!", "Sure thing!".
- Be direct and human. Just help.
"""


class AIGateway:

    def _expired(self):
        return date.today() > EXPIRY

    def _call(self, model, prompt, history=None, timeout=75):
        if self._expired():
            return None, "Evaluation period ended."
        try:
            resp = requests.post(
                PROXY_URL,
                json={"model": model, "prompt": prompt, "history": (history or [])[-12:]},
                headers=HEADERS,
                timeout=timeout,
            )
            if resp.status_code != 200:
                return None, f"Proxy error HTTP {resp.status_code}."
            data = resp.json()
            text = (
                data.get("response") or data.get("reply") or data.get("content")
                or data.get("message") or data.get("text") or data.get("output")
            )
            if isinstance(text, list):
                text = " ".join(str(b.get("text", "")) for b in text if isinstance(b, dict))
            return str(text).strip() if text else None, None
        except requests.exceptions.Timeout:
            return None, "AI request timed out."
        except requests.exceptions.ConnectionError:
            return None, "Cannot reach proxy."
        except Exception as e:
            return None, str(e)

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(self, user_message: str, history=None, draft: dict = None):
        """
        Returns (reply_text, action_dict | None, error)
        draft = current partial task being built, e.g. {"name": "Math", "priority": "High"}
        """
        draft = draft or {}
        if draft:
            collected  = ", ".join(f"{k}: {v}" for k, v in draft.items() if v)
            remaining  = [k for k in ("name", "priority", "due_date", "category") if not draft.get(k)]
            draft_ctx  = (
                f"Already collected → {collected}\n"
                f"Still missing     → {', '.join(remaining) if remaining else 'nothing (all set, ready to confirm)'}"
            )
        else:
            draft_ctx = "Empty — no task being created yet."

        system = (
            CHAT_SYSTEM
            .replace("{today}",        date.today().isoformat())
            .replace("{draft_context}", draft_ctx)
        )
        raw, err = self._call(CLAUDE, f"{system}\n\nUser: {user_message}", history=history, timeout=50)
        if err or not raw:
            return None, None, err or "No response."

        action, reply = None, raw
        if ACTION_TAG in raw:
            parts      = raw.split(ACTION_TAG, 1)
            reply      = parts[0].strip()
            action_raw = parts[1].strip()
            try:
                clean  = action_raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                action = json.loads(clean)
            except json.JSONDecodeError:
                action = None

        return reply, action, None

    # ── NL Task Parser ───────────────────────────────────────────────────────

    def parse_task(self, text: str):
        prompt = (
            f'Parse this task. Return ONLY a JSON object, no markdown.\n'
            f'Fields: name (str), priority (High|Medium|Low), due_date (YYYY-MM-DD|null), '
            f'category (Work|Study|Personal|Health|Finance|General), notes (str|null)\n\n'
            f'Input: "{text}"\nJSON:'
        )
        result, err = self._call(CLAUDE, prompt, timeout=30)
        if err or not result:
            return None, err or "No response."
        try:
            clean = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(clean), None
        except json.JSONDecodeError:
            return None, f"Parse error: {result[:80]}"

    # ── Schedule Optimizer ───────────────────────────────────────────────────

    def optimize_schedule(self, tasks):
        if not tasks:
            return None, "No pending tasks."
        lines = "\n".join(
            f"  [{t['priority']}] {t['name']} | Due: {t.get('due_date') or 'flexible'} | {t.get('category','General')}"
            for t in tasks
        )
        prompt = (
            f"Productivity expert. Build a focused time-blocked schedule for today.\n\n"
            f"Tasks:\n{lines}\n\n"
            f"Rules: 9AM-9PM, High priority first, group by category, 15-min break every 90min, "
            f"25-min Pomodoro blocks, realistic pacing.\n\n"
            f"Format each block: HH:MM - HH:MM | Task | [Priority] | Category\n"
            f"End with one line starting with >>"
        )
        return self._call(DEEPSHI, prompt, timeout=90)

    # ── Motivation ───────────────────────────────────────────────────────────

    def get_motivation(self, stats: dict):
        p    = stats.get("productivity", 0)
        tone = "savage roast" if p < 30 else ("strong praise" if p >= 70 else "balanced push")
        prompt = (
            f"Productivity coach. 3-4 lines. Tone: {tone}.\n"
            f"Stats: {stats.get('completed')} done, {stats.get('pending')} pending, "
            f"{stats.get('overdue')} overdue, {p}% rate, {stats.get('streak')}-day streak.\n"
            f"Direct, witty, specific. No filler. End with one punchy line."
        )
        return self._call(DEEPSHI, prompt, timeout=30)
