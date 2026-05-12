"""
ai_gateway.py — Multi-Model AI Routing via DevNest Proxy
"""

import json
import re
import time
import requests
from datetime import date

PROXY_URL        = "https://devnest-proxy-server.onrender.com/v1/proxy/ai"
PROXY_HEALTH_URL = "https://devnest-proxy-server.onrender.com/health"
HEADERS          = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type":    "application/json",
}

RETRY_WAIT  = 25
MAX_RETRIES = 1

EXPIRY  = date(2026, 5, 20)
CLAUDE  = "claude-haiku-4-5-20251001"
DEEPSHI = "deepshi-r2"

ACTION_TAG = "TASKFLOW_ACTION:"

# ── Intent definitions ────────────────────────────────────────────────────────

INTENTS = {
    "create_task":   "User wants to add / create a new task",
    "list_tasks":    "User wants to see, list, or view existing tasks",
    "search_tasks":  "User wants to find / search a specific task by keyword",
    "complete_task": "User wants to mark a task as done / complete",
    "delete_task":   "User wants to delete or remove a task",
    "edit_task":     "User wants to edit, update, or change a task",
    "analytics":     "User wants stats, productivity info, or summary numbers",
    "optimize":      "User wants a schedule, time plan, or optimization",
    "chitchat":      "General conversation, greeting, or unrelated to tasks",
    "unclear":       "Cannot determine intent clearly",
}

# Which action names map to which intent
INTENT_TO_ACTIONS = {
    "create_task":   {"update_draft", "confirm_task", "create_task", "clear_draft"},
    "list_tasks":    {"list_tasks"},
    "search_tasks":  {"search_tasks"},
    "complete_task": {"complete_task"},
    "delete_task":   {"delete_task"},
    "edit_task":     {"edit_task"},
    "analytics":     {"show_analytics"},
    "optimize":      set(),
    "chitchat":      set(),
    "unclear":       set(),
}

# Human-readable loading messages per intent
INTENT_STATUS = {
    "create_task":   "Building your task...",
    "list_tasks":    "Fetching your tasks...",
    "search_tasks":  "Searching tasks...",
    "complete_task": "Updating task status...",
    "delete_task":   "Processing deletion...",
    "edit_task":     "Preparing task edit...",
    "analytics":     "Crunching your numbers...",
    "optimize":      "Optimizing your schedule...",
    "chitchat":      "Thinking...",
    "unclear":       "Processing your request...",
}

INTENT_CLASSIFY_SYSTEM = """You are an intent classifier for a task management app.

Given a user message, return ONLY a JSON object — no markdown, no explanation:
{"intent": "<one of the intents>", "entities": {"task_name": null, "task_id": null, "keyword": null}}

Valid intents: create_task, list_tasks, search_tasks, complete_task, delete_task, edit_task, analytics, optimize, chitchat, unclear

Rules:
- If user mentions a task ID (like A1B2C3), extract it in task_id
- If user wants to see/show/list tasks → list_tasks
- If user asks "which task" or "what task" or "show me that task" → list_tasks or search_tasks
- Stats/productivity/rate/streak → analytics
- General greetings or off-topic → chitchat
- When unsure → unclear
"""

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

=== DETECTED USER INTENT ===
{intent_context}

=== INTENT ALIGNMENT RULES ===
- ONLY emit show_analytics if the intent is "analytics". Do NOT add it for list_tasks or search_tasks.
- ONLY emit list_tasks if the intent is "list_tasks". Do NOT show analytics alongside it.
- Match the action to the intent — one action per response unless chaining is logically needed.
- If intent is "search_tasks", emit search_tasks, NOT list_tasks + show_analytics.

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

    # ── Block parser ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(raw) -> str | None:
        if not raw:
            return None

        if isinstance(raw, list):
            text_parts = [
                b.get("text", "")
                for b in raw
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            result = " ".join(text_parts).strip()
            if not result:
                result = " ".join(
                    b.get("content", b.get("text", ""))
                    for b in raw
                    if isinstance(b, dict) and b.get("type") in ("reasoning", "thinking")
                ).strip()
            return result or None

        raw = str(raw).strip()

        if raw.startswith("["):
            try:
                blocks = json.loads(raw)
                return AIGateway._extract_text(blocks)
            except json.JSONDecodeError:
                pass

        if raw.startswith("{"):
            try:
                block = json.loads(raw)
                if block.get("type") == "text":
                    return block.get("text", "").strip() or None
                if block.get("type") in ("reasoning", "thinking"):
                    return (block.get("content") or block.get("text") or "").strip() or None
            except json.JSONDecodeError:
                pass

        text_match = re.search(
            r'"type"\s*:\s*"text".*?"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
            raw, re.DOTALL
        )
        if text_match:
            return text_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()

        reasoning_match = re.search(
            r'"type"\s*:\s*"(?:reasoning|thinking)".*?"(?:content|text)"\s*:\s*"((?:[^"\\]|\\.)*)"',
            raw, re.DOTALL
        )
        if reasoning_match:
            return reasoning_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()

        return raw or None

    # ── Proxy error detector ─────────────────────────────────────────────────

    _PROXY_ERR_MARKERS = ("too slow", "timed out", "provider", "⚠", "error:", "unavailable")

    def _is_proxy_error(self, text: str) -> bool:
        lo = text.lower()
        return any(m in lo for m in self._PROXY_ERR_MARKERS)

    # ── Wake-up ping ─────────────────────────────────────────────────────────

    @staticmethod
    def wake_up():
        try:
            requests.get(PROXY_HEALTH_URL, timeout=10)
        except Exception:
            pass

    # ── Core call ────────────────────────────────────────────────────────────

    def _call(self, model, prompt, history=None, timeout=75, **extra):
        if self._expired():
            return None, "Evaluation period ended."

        payload = {
            "model":   model,
            "prompt":  prompt,
            "history": (history or [])[-12:],
            **extra,
        }

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    PROXY_URL, json=payload, headers=HEADERS, timeout=timeout
                )

                if resp.status_code in (502, 503, 504):
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_WAIT)
                        continue
                    return None, (
                        f"Backend is starting up (HTTP {resp.status_code}). "
                        "Wait ~30s and try again."
                    )

                if resp.status_code != 200:
                    return None, f"Proxy error HTTP {resp.status_code}."

                data = resp.json()
                raw  = (
                    data.get("response") or data.get("reply") or data.get("content")
                    or data.get("message") or data.get("text") or data.get("output")
                )
                text = self._extract_text(raw)

                if text and self._is_proxy_error(text):
                    return None, "AI is taking too long. Please try again in a moment."

                return text, None

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES:
                    time.sleep(5)
                    continue
                return None, "AI is thinking too long — try again in a moment."
            except requests.exceptions.ConnectionError:
                if attempt < MAX_RETRIES:
                    time.sleep(10)
                    continue
                return None, "Cannot reach proxy."
            except Exception as e:
                return None, str(e)

        return None, "Request failed after retry."

    # ── Intent Classifier ─────────────────────────────────────────────────────

    def classify_intent(self, user_message: str, history=None) -> dict:
        """
        Fast Haiku call to classify user intent before the main AI response.
        Returns dict: {intent, entities, status_msg}
        Falls back to 'unclear' on any error — never blocks the main flow.
        """
        # Build recent context (last 2 exchanges only — keep it cheap)
        recent = ""
        if history:
            tail = history[-4:]
            recent = "\n".join(
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content'][:120]}"
                for m in tail
            )

        prompt = (
            f"{INTENT_CLASSIFY_SYSTEM}\n\n"
            f"Recent context:\n{recent}\n\n" if recent else f"{INTENT_CLASSIFY_SYSTEM}\n\n"
        ) + f"User message: \"{user_message}\"\n\nJSON:"

        result, err = self._call(CLAUDE, prompt, timeout=15)
        if err or not result:
            return {"intent": "unclear", "entities": {}, "status_msg": INTENT_STATUS["unclear"]}

        try:
            clean = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
            intent = parsed.get("intent", "unclear")
            if intent not in INTENTS:
                intent = "unclear"
            return {
                "intent":     intent,
                "entities":   parsed.get("entities", {}),
                "status_msg": INTENT_STATUS.get(intent, INTENT_STATUS["unclear"]),
                "label":      INTENTS.get(intent, ""),
            }
        except (json.JSONDecodeError, AttributeError):
            return {"intent": "unclear", "entities": {}, "status_msg": INTENT_STATUS["unclear"]}

    def validate_action(self, intent: str, action_name: str | None) -> tuple[bool, str]:
        """
        Check if the AI's triggered action matches the classified intent.
        Returns (is_match, message)
        """
        if not action_name or intent in ("chitchat", "unclear"):
            return True, ""

        expected = INTENT_TO_ACTIONS.get(intent, set())
        if not expected:  # intent has no required action
            return True, ""

        if action_name in expected:
            return True, f"✓ {action_name}"

        # Mismatch — but some are acceptable cross-triggers
        # e.g. user said "list tasks" and AI also updates draft → fine
        soft_ok = {
            "list_tasks":    {"search_tasks"},
            "search_tasks":  {"list_tasks"},
            "create_task":   {"list_tasks", "search_tasks"},
        }
        if action_name in soft_ok.get(intent, set()):
            return True, ""

        return False, (
            f"Expected action for '{intent}' but got '{action_name}'"
        )

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(self, user_message: str, history=None, draft: dict = None, intent_info: dict = None):
        """
        Uses Deepshi R2 with thinking enabled.
        intent_info — optional pre-classified intent dict from classify_intent()
        Returns (reply_text, action_dict | None, error)
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

        # Inject intent context so AI knows what NOT to add
        if intent_info and intent_info.get("intent"):
            intent_ctx = (
                f"Classified intent: {intent_info['intent']} — {INTENTS.get(intent_info['intent'], '')}\n"
                f"Stick to this intent. Do NOT emit unrelated actions (e.g. show_analytics for list_tasks)."
            )
        else:
            intent_ctx = "Intent: unclear — use your best judgement."

        system = (
            CHAT_SYSTEM
            .replace("{today}",         date.today().isoformat())
            .replace("{draft_context}", draft_ctx)
            .replace("{intent_context}", intent_ctx)
        )

        raw, err = self._call(
            DEEPSHI,
            f"{system}\n\nUser: {user_message}",
            history=history,
            timeout=120,
            enable_thinking=True,
            session_key="taskflow_chat",
        )
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
        return self._call(DEEPSHI, prompt, timeout=120)

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
        return self._call(CLAUDE, prompt, timeout=30)
