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
    "create_task":      "User wants to add / create a new task",
    "list_tasks":       "User wants to see, list, or view existing tasks",
    "search_tasks":     "User wants to find / search a specific task by keyword",
    "complete_task":    "User wants to mark a task as done / complete",
    "delete_task":      "User wants to delete or remove a task",
    "edit_task":        "User wants to edit, update, or change a task",
    "analytics":        "User wants stats, productivity info, or summary numbers",
    "optimize":         "User wants a schedule, time plan, or optimization",
    "weather":          "User is asking about weather, temperature, rain, or climate",
    "general_question": "User is asking a general knowledge or off-task question",
    "chitchat":         "General conversation, greeting, or small talk",
    "unclear":          "Cannot determine intent clearly",
}

# Which action names map to which intent
INTENT_TO_ACTIONS = {
    "create_task":      {"update_draft", "confirm_task", "create_task", "clear_draft"},
    "list_tasks":       {"list_tasks"},
    "search_tasks":     {"search_tasks"},
    "complete_task":    {"complete_task"},
    "delete_task":      {"delete_task"},
    "edit_task":        {"edit_task"},
    "analytics":        {"show_analytics"},
    "optimize":         set(),
    "weather":          set(),   # no task action — pure web search reply
    "general_question": set(),
    "chitchat":         set(),
    "unclear":          set(),
}

# Loading message shown while AI thinks
INTENT_STATUS = {
    "create_task":      "Building your task...",
    "list_tasks":       "Fetching your tasks...",
    "search_tasks":     "Searching tasks...",
    "complete_task":    "Updating task status...",
    "delete_task":      "Processing deletion...",
    "edit_task":        "Preparing task edit...",
    "analytics":        "Crunching your numbers...",
    "optimize":         "Optimizing your schedule...",
    "weather":          "Checking the weather...",
    "general_question": "Looking that up...",
    "chitchat":         "Thinking...",
    "unclear":          "Processing your request...",
}

# Intents that should trigger proxy web search
WEB_SEARCH_INTENTS = {"weather", "general_question"}

# Intents where task actions should be stripped from response
NO_ACTION_INTENTS = {"weather", "general_question", "chitchat"}

# ── Classify system prompt ────────────────────────────────────────────────────

INTENT_CLASSIFY_SYSTEM = """You are an intent classifier for a task management app.

Given a user message, return ONLY a JSON object — no markdown, no explanation:
{"intent": "<one of the intents>", "entities": {"task_name": null, "task_id": null, "keyword": null, "location": null}}

Valid intents: create_task, list_tasks, search_tasks, complete_task, delete_task, edit_task, analytics, optimize, weather, general_question, chitchat, unclear

Classification rules:
- weather / mausam / barish / garmi / sardi / temperature / baarish / thand → weather
- If user mentions a task ID like A1B2C3 → extract in task_id
- See/show/list/dikhao tasks → list_tasks
- Which task / kaunsa task / task detail → list_tasks or search_tasks
- Stats/productivity/rate/streak/analytics → analytics
- General knowledge not about tasks → general_question
- Greetings / hi / hello / kya haal / how are you → chitchat
- When unsure → unclear
- For weather queries, extract city/location in entities.location if user mentions one
"""

# ── Main chat system prompt ───────────────────────────────────────────────────

CHAT_SYSTEM = """You are TaskFlow AI — a sharp, no-filler productivity assistant inside a terminal task manager.

TODAY: {today}

=== LANGUAGE RULE (CRITICAL) ===
Detect the language/style of each user message and reply in the EXACT same language.
- English → English | Hindi (Devanagari) → Hindi | Hinglish → Hinglish | Mix → match mix
Never switch language on your own.

=== CURRENT TASK STATE ===
{task_stats}

Task state awareness rules:
- total_tasks=0 means user has NO tasks at all. Tell them clearly. Offer to add one.
- Never show a task list when there are 0 tasks — just say so in plain text.
- If overdue > 0, always mention it when user asks about tasks or analytics.
- If pending > 0, stay aware of this context.

=== CURRENT TASK DRAFT ===
{draft_context}

Draft rules:
- DO NOT re-ask fields already in draft.
- Ask 1-2 missing fields at a time.
- If user switches topic: answer first, then remind about the open draft.
- Emit "update_draft" when user gives any task field.
- Emit "confirm_task" when all fields are ready (shows preview).
- Emit "create_task" only after user confirms preview.
- Emit "clear_draft" if user abandons task creation.

=== DETECTED USER INTENT ===
{intent_context}

Intent alignment rules:
- ONLY emit show_analytics when intent is "analytics".
- ONLY emit list_tasks when intent is "list_tasks".
- For weather/general_question: just reply in text. DO NOT emit ANY task action.
- One action per response unless chaining is logically required.

=== LOCATION & WEB SEARCH CONTEXT ===
{location_context}

If web search results are injected in the prompt:
- Use them to answer weather / general questions accurately.
- Summarise clearly in user's language.
- Do not mention "web search" or "search results" explicitly — just answer naturally.

=== ACTIONS (task intents only) ===
TASKFLOW_ACTION:{"action":"ACTION_NAME","data":{...}}  ← append at very END of reply, nothing after.

  update_draft   → {name?, priority?, due_date?, category?, notes?}
  confirm_task   → full task fields for preview
  create_task    → {name, priority, due_date, category, notes?}
  clear_draft    → {}
  search_tasks   → {query}
  list_tasks     → {status?, category?, priority?}
  edit_task      → {task_id, updates:{field:value,...}}
  complete_task  → {task_id}
  delete_task    → {task_id}
  show_analytics → {}

=== STYLE ===
- 1-2 sentences unless explaining something complex.
- No "Certainly!", "Of course!", "Great!".
- Direct and human. Just help.
"""


class AIGateway:

    def _expired(self):
        return date.today() > EXPIRY

    # ── IP → City ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_city_from_ip() -> str | None:
        """Quick IP geolocation. Returns city name or None."""
        try:
            data = requests.get("https://ipinfo.io/json", timeout=3).json()
            return data.get("city")
        except Exception:
            return None

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
        return any(m in text.lower() for m in self._PROXY_ERR_MARKERS)

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
        """Fast Haiku call (~2-4s) to classify user intent before main AI."""
        recent = ""
        if history:
            recent = "\n".join(
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content'][:120]}"
                for m in history[-4:]
            )

        prompt = (
            INTENT_CLASSIFY_SYSTEM + "\n\n"
            + (f"Recent context:\n{recent}\n\n" if recent else "")
            + f"User message: \"{user_message}\"\n\nJSON:"
        )

        result, err = self._call(CLAUDE, prompt, timeout=15)
        if err or not result:
            return {
                "intent": "unclear", "entities": {},
                "status_msg": INTENT_STATUS["unclear"], "needs_web": False,
            }

        try:
            clean  = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
            intent = parsed.get("intent", "unclear")
            if intent not in INTENTS:
                intent = "unclear"
            return {
                "intent":     intent,
                "entities":   parsed.get("entities", {}),
                "status_msg": INTENT_STATUS.get(intent, INTENT_STATUS["unclear"]),
                "label":      INTENTS.get(intent, ""),
                "needs_web":  intent in WEB_SEARCH_INTENTS,
            }
        except (json.JSONDecodeError, AttributeError):
            return {
                "intent": "unclear", "entities": {},
                "status_msg": INTENT_STATUS["unclear"], "needs_web": False,
            }

    # ── Action validator ─────────────────────────────────────────────────────

    def validate_action(self, intent: str, action_name: str | None) -> tuple[bool, str]:
        if not action_name or intent in NO_ACTION_INTENTS or intent == "unclear":
            return True, ""
        expected = INTENT_TO_ACTIONS.get(intent, set())
        if not expected:
            return True, ""
        if action_name in expected:
            return True, ""
        soft_ok = {
            "list_tasks":   {"search_tasks"},
            "search_tasks": {"list_tasks"},
            "create_task":  {"list_tasks", "search_tasks"},
        }
        if action_name in soft_ok.get(intent, set()):
            return True, ""
        return False, f"Expected action for '{intent}' but got '{action_name}'"

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        history=None,
        draft: dict = None,
        intent_info: dict = None,
        task_stats: dict = None,
        location: str = None,
    ):
        """
        Main chat. Passes task_stats + location + intent into system prompt.
        Enables web_search=True for weather/general_question intents.
        Returns (reply_text, action_dict | None, error)
        """
        draft = draft or {}

        # ── Draft context ─────────────────────────────────────────────────────
        if draft:
            collected = ", ".join(f"{k}: {v}" for k, v in draft.items() if v)
            remaining = [k for k in ("name", "priority", "due_date", "category") if not draft.get(k)]
            draft_ctx = (
                f"Already collected → {collected}\n"
                f"Still missing     → {', '.join(remaining) if remaining else 'nothing (ready to confirm)'}"
            )
        else:
            draft_ctx = "Empty — no task being created yet."

        # ── Task stats context ────────────────────────────────────────────────
        if task_stats:
            stats_ctx = (
                f"total_tasks={task_stats.get('total', 0)}  "
                f"pending={task_stats.get('pending', 0)}  "
                f"completed={task_stats.get('completed', 0)}  "
                f"overdue={task_stats.get('overdue', 0)}  "
                f"productivity={task_stats.get('productivity', 0)}%"
            )
        else:
            stats_ctx = "Task stats unavailable."

        # ── Intent context ────────────────────────────────────────────────────
        intent_name = (intent_info or {}).get("intent", "unclear")
        intent_ctx  = (
            f"Classified intent: {intent_name} — {INTENTS.get(intent_name, '')}\n"
            f"Stick to this intent. Do NOT emit unrelated task actions."
        )

        # ── Location context ──────────────────────────────────────────────────
        if location:
            loc_ctx = (
                f"User's location (IP-detected): {location}\n"
                f"Web search results are injected in the prompt. "
                f"Use them to answer weather queries naturally."
            )
        else:
            loc_ctx = "Location not detected."

        system = (
            CHAT_SYSTEM
            .replace("{today}",            date.today().isoformat())
            .replace("{draft_context}",    draft_ctx)
            .replace("{task_stats}",       stats_ctx)
            .replace("{intent_context}",   intent_ctx)
            .replace("{location_context}", loc_ctx)
        )

        # Inject location into prompt for weather queries
        needs_web   = (intent_info or {}).get("needs_web", False)
        user_prompt = user_message
        if needs_web and location:
            user_prompt = f"[User location: {location}]\n{user_message}"

        raw, err = self._call(
            DEEPSHI,
            f"{system}\n\nUser: {user_prompt}",
            history=history,
            timeout=120,
            enable_thinking=True,
            session_key="taskflow_chat",
            web_search=needs_web,          # proxy enriches prompt with search
        )
        if err or not raw:
            return None, None, err or "No response."

        # Split out action block
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

        # Hard strip: no task actions for non-task intents
        if action and intent_name in NO_ACTION_INTENTS:
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
