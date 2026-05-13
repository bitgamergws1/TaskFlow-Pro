"""
ai_gateway.py — Multi-Model AI Routing via DevNest Proxy
         + Response Validator & Auto-Retry (v2)
"""

import json
import re
import time
import requests
from datetime import date
from timezone_utils import today_local, tz_label

PROXY_URL        = "https://devnest-proxy-server.onrender.com/v1/proxy/ai"
PROXY_HEALTH_URL = "https://devnest-proxy-server.onrender.com/health"
HEADERS          = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type":    "application/json",
}

RETRY_WAIT  = 3   # ← was 25; no reason to wait 25s between retries
MAX_RETRIES = 1

# ── Validation settings ───────────────────────────────────────────────────────
CHAT_MAX_RETRIES   = 2          # max auto-retries on bad response
CHAT_RETRY_DELAY   = 3          # seconds between retries
MIN_REPLY_LENGTH   = 8          # a valid reply must have at least 8 chars
JUDGE_THRESHOLD    = 5          # judge score below this → retry (0-10 scale)

EXPIRY     = date(2026, 5, 20)
DEEPSHI_R1 = "deepshi-r1"   # replaces Claude for all classifier/judge/utility calls
DEEPSHI    = "deepshi-r2"

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

INTENT_TO_ACTIONS = {
    "create_task":      {"update_draft", "confirm_task", "create_task", "clear_draft"},
    "list_tasks":       {"list_tasks"},
    "search_tasks":     {"search_tasks"},
    "complete_task":    {"complete_task"},
    "delete_task":      {"delete_task"},
    "edit_task":        {"edit_task"},
    "set_reminder":     {"set_reminder", "edit_task"},
    "analytics":        {"show_analytics"},
    "optimize":         set(),
    "weather":          set(),
    "general_question": set(),
    "chitchat":         set(),
    "unclear":          set(),
}

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

WEB_SEARCH_INTENTS = {"weather", "general_question"}
NO_ACTION_INTENTS  = {"weather", "general_question", "chitchat"}

# ── Intent classify system prompt ─────────────────────────────────────────────

# ── Dynamic Intent Rulebook ───────────────────────────────────────────────────
# This is the AI-readable rulebook. No hardcoded keywords — the AI uses its own
# multilingual understanding to match user messages to intents.
# Add new languages, phrasings, or edge cases here freely.

INTENT_RULEBOOK = """
=== TASKFLOW INTENT RULEBOOK ===

You are a multilingual intent classifier. Use your full language understanding —
do NOT rely on exact keywords. Understand meaning, not just words.

--- INTENT: complete_task ---
The user is saying they HAVE DONE / FINISHED something, OR they want a task marked as done.
Understand this across ALL languages and styles:

• User says they finished an action that matches a task: "I drank water", "mene pani pi liya",
  "paani pee liya", "pee leya" (Punjabi), "kudichuten" (Tamil), "kudichhu" (Malayalam),
  "kheyechi" (Bengali), "naan kudichittaen", "done kar diya", "ho gaya", "nipta diya",
  "complete ho gaya", "finish kar diya", "kar liya", "kr liya", "khatam ho gaya"
• User asks what to do AFTER saying they finished: "ab kya?", "tho ab?", "to ab kya karna hai?",
  "now what?", "aage kya?", "next step?"  ← if context has a matching pending task → complete_task
• User says "mark as done", "done karo", "complete karo", "tick karo", "haan kar do"
• Key signal: user describes completing an ACTION that a pending task is about

NOT complete_task if: user is asking about task status without saying they did it.

--- INTENT: create_task ---
User wants to ADD a new task to their list.
• "add karo", "new task", "task banana hai", "remind me to", "note kar lo",
  "ek task add karo", "likh lo", "save kar lo", "bana do"
• Describing a future to-do: "mujhe kal report likhni hai" → create_task

--- INTENT: list_tasks ---
User wants to SEE their existing tasks.
• "mere tasks dikhao", "kya karna hai", "list karo", "show tasks", "mera kya pending hai",
  "konsa task hai", "tasks batao", "kya chal raha hai mere saath", "meri list"
• "konsa" / "which one" / "kaun sa" when asking about current tasks → list_tasks

--- INTENT: search_tasks ---
User wants to FIND a specific task by name or keyword (not listing all).
• "dhundho", "search karo", "find the task about X", "X wala task kahan hai"

--- INTENT: delete_task ---
User wants to REMOVE a task permanently.
• "hata do", "delete karo", "remove karo", "hatao", "nikal do", "mujhe ye nahi chahiye"

--- INTENT: edit_task ---
User wants to CHANGE something about an existing task.
• "badlo", "change karo", "update karo", "priority change", "due date update",
  "naam badlo", "edit karo"

--- INTENT: analytics ---
User wants productivity stats, numbers, or a summary.
• "stats dikhao", "kitne complete kiye", "productivity kya hai", "streak", "analytics",
  "kitne pending hain", "meri progress"

--- INTENT: optimize ---
User wants a schedule or time plan.
• "schedule banao", "plan karo", "optimize karo", "time table", "kab karu ye sab"

--- INTENT: general_question ---
User is asking general knowledge NOT about their task list.
• "pani kab pina chahiye" (when to drink water — general health tip, NOT a task search)
• "best time for exercise", "ye kya hota hai", "kaise kare", advice/tips/facts
• Key rule: if user asks ABOUT A TOPIC (like water/exercise/food) rather than ABOUT THEIR TASKS → general_question

--- INTENT: weather ---
User asks about weather conditions.
• "aaj mausam kaisa hai", "barish hogi", "temperature kya hai", "garmi hai kya",
  "will it rain", "mausam batao"

--- INTENT: chitchat ---
Casual conversation, greetings, small talk.
• "hi", "hello", "kya haal hai", "kaisa chal raha hai", "theek ho?", "shukriya", "thanks"

--- INTENT: unclear ---
Use ONLY when genuinely cannot determine intent even with full context.

=== DECISION PRIORITY (when ambiguous) ===
complete_task > delete_task > edit_task > create_task > list_tasks > search_tasks > analytics > general_question > weather > chitchat > unclear

=== KEY PRINCIPLES ===
1. Use conversation history — a message makes more sense with context
2. "ab kya" / "tho ab" / "now what" AFTER user describes an action → complete_task
3. General knowledge questions about a TOPIC (not their task list) → general_question
4. When user describes doing something that matches a pending task → complete_task
5. Trust meaning over keywords — understand intent, not literal words
"""

# ── Intent classify system prompt ─────────────────────────────────────────────

INTENT_CLASSIFY_SYSTEM = """You are a multilingual intent classifier for a task management app.

{rulebook}

Given the conversation context and the user's latest message, return ONLY a JSON object:
{{"intent": "<intent_name>", "entities": {{"task_name": null, "task_id": null, "keyword": null, "location": null}}}}

Valid intents: create_task, list_tasks, search_tasks, complete_task, delete_task, edit_task, analytics, optimize, weather, general_question, chitchat, unclear

Rules:
- Read the FULL rulebook above before deciding
- Extract task_id if user mentions an ID like 9E15C7B6
- Extract location in entities.location for weather queries
- Return ONLY the JSON object, no markdown, no explanation
""".replace("{rulebook}", INTENT_RULEBOOK)

# ── Action Playbook ───────────────────────────────────────────────────────────
# Situation → Action mapping for the main AI.
# Language-agnostic: describes WHAT THE USER MEANS, not how they say it.
# Add new rules here freely — AI applies them using its own understanding.

ACTION_PLAYBOOK = """
=== ACTION PLAYBOOK ===
These are situation-to-action rules. Read them before deciding what action to emit.
Language does not matter — understand the MEANING, then apply the rule.

── RULE 1: User completed a task ──────────────────────────────────────────────
SITUATION: User says they have done / finished / completed something that matches
           a pending task in their list.
SIGNALS (any language, any phrasing):
  - "I drank water" when "Drink water" is pending
  - "pani pi liya" when "Pani peena" is pending
  - "report likh di" when a report-writing task is pending
  - "gym ho gaya", "kha liya", "so gaya", "padh liya"
  - User implies the action is done, not that they want to do it
ACTION: emit complete_task with the matching task_id
REPLY: Confirm completion naturally in user's language. e.g. "Done! Pani peena ✓"

── RULE 2: User asks "now what?" after completing ─────────────────────────────
SITUATION: User completed something (or just said they did) and asks what to do next.
SIGNALS: "ab kya?", "tho ab?", "next?", "aage kya karna hai?", "what's next?"
ACTION: emit complete_task for the finished task (if not already done),
        then emit list_tasks to show remaining pending work
REPLY: Acknowledge completion, show what's still pending.

── RULE 3: User wants to add a task ───────────────────────────────────────────
SITUATION: User describes a future to-do, something they NEED to do, or explicitly
           asks to add/create/save a task.
SIGNALS: "mujhe kal X karna hai", "remind me to X", "add a task for X",
         "X karna hai note kar lo", "save this: X", "task banana hai", "note kar"

TASK FIELDS — what to collect, in priority order:
  ① name        REQUIRED — always extract first. If unclear, ask.
  ② due_date    Ask: "Kab tak karna hai?" / "By when?"
                ⚠ PAST DATE RULE: If user gives a date that is before today (check via context):
                  - Do NOT silently accept it.
                  - Say: "Ye date toh past mein hai ({their_date}). Sahi date batao?"
                  - Ask again. Only accept today or future dates.
                  - If user insists it's intentional, accept but add a note: "User confirmed past date."
  ③ due_time    Ask ONLY if task is time-specific ("dawai 8 baje", "meeting 3pm")
                or if user says "remind me at X". Format: HH:MM 24h.
                Skip for vague tasks (no specific time needed).
  ④ priority    Ask: "Kitna important hai? High/Medium/Low?" — skip if obvious from context
                (e.g. "urgent" → High, "kabhi bhi" → Low)
  ⑤ category    Guess from context; ask only if genuinely unclear
                Work/Study/Personal/Health/Finance/General
  ⑥ reminder_at Ask: "Yaad dilana chahoge? Agar haan, kab?" — ONLY ask this if:
                  - user says "remind me", "yaad dilana", "bhoolna nahi chahta"
                  - OR task has a due_time (natural to set reminder)
                Format: "YYYY-MM-DD HH:MM"
  ⑦ recurrence  Ask: "Ye roz karna hai ya ek baar?" — ONLY ask if task sounds repeated
                  - "roz paani peena", "daily standup", "har hafte report"
                Values: none / daily / weekly / weekdays / monthly
  ⑧ notes       Optional — offer: "Koi extra note?" only after other fields done

MANDATORY FIELDS — task CANNOT be created without these 4:
  ✦ name      — always required, no exceptions
  ✦ due_date  — always required. If user resists: "Ek rough date bhi chalegi, bilkul exact nahi chahiye."
  ✦ priority  — always required. If unclear: guess from context, then confirm: "High rakh dun?"
  ✦ category  — always required. Guess from context (gym→Health, project→Work). Confirm if unsure.

  ⚠ NEVER emit confirm_task or create_task if ANY of the 4 above are missing.
  ⚠ NEVER emit create_task directly — always emit confirm_task first so user can review.

OPTIONAL FIELDS — ask only when contextually relevant:
  ◦ due_time       — only if task is time-specific or user mentions a time
  ◦ reminder_at    — only if user says "remind", "yaad dilana", "bhoolna nahi chahta"
  ◦ recurrence     — only if task sounds repeated (roz, daily, har hafte)
  ◦ notes          — offer last: "Koi extra detail add karu?"

COLLECTION STRATEGY:
  1. Extract everything possible from the first message → emit update_draft.
  2. Ask for missing MANDATORY fields one at a time (name → due_date → priority → category).
  3. Once all 4 mandatory fields are in draft → emit confirm_task for preview.
  4. After user confirms ("haan", "save karo", "yes") → emit create_task.
  5. User can skip optional fields at any point — never block on them.
  6. If user says "bas save karo" / "create karo" but mandatory fields are still missing
     → do NOT create. Politely say which field is still needed.
     Example: "Ek kaam — due date batao, phir save kar deta hun."

REPLY: In user's language — confirm what you captured, ask exactly ONE missing field.
       Example: "Gym jana note kar liya! Kab tak karna hai?" (not "Please provide name, priority, date...")

── RULE 4: User wants to see their tasks ──────────────────────────────────────
SITUATION: User wants to view/see their current task list.
SIGNALS: "mere tasks dikhao", "kya pending hai", "list karo", "show my tasks",
         "konsa task hai mera", "kya karna hai abhi"
ACTION: emit list_tasks (with optional status/category filters if mentioned)
REPLY: ONLY say something like "Yeh raha:" or "Dekh lo:" — 2-3 words max.
       NEVER write task names, due dates, priorities, or any task details in your text.
       The system will fetch and display real task data automatically after your action.
       Making up task details = WRONG. You do not know the task names — only the count.

── RULE 5: User wants to delete a task ────────────────────────────────────────
SITUATION: User wants to remove a task from their list.
SIGNALS: "hata do", "delete karo", "mujhe ye nahi chahiye", "remove this task"
ACTION: emit delete_task with task_id
REPLY: Confirm deletion. Mention they can restore it from recycle bin.

── RULE 6: User wants to edit a task ──────────────────────────────────────────
SITUATION: User wants to change something about an existing task.
SIGNALS: "priority change karo", "due date aage karo", "naam badlo", "edit karo"
ACTION: emit edit_task with task_id and the specific field updates
REPLY: Confirm what was changed.

── RULE 7: User asks for stats / productivity ─────────────────────────────────
SITUATION: User wants numbers — how many done, pending, streak, productivity rate.
SIGNALS: "kitne complete kiye", "meri productivity", "stats", "streak kitna hai",
         "summarize kro", "batao kya chal raha hai", "progress kya hai"
ACTION: emit show_analytics
REPLY: Give a SHORT but MEANINGFUL human summary in user's language. DO NOT just
       recite raw numbers like "1 total, 0 pending" — that's what the chart below
       already shows. Instead:
       1. Lead with ONE overall verdict: "Sab kuch on track hai", "Achi progress hai",
          "Thodi struggle ho rahi hai", etc.
       2. Highlight what's notable: streak, productivity %, overdue count if > 0.
       3. If overdue > 0 → mention it with a nudge.
       4. If productivity is 100% or streak > 3 → give a small praise.
       5. Keep it 2-3 lines MAX. Natural, conversational, in user's language.
       EXAMPLE (Hinglish): "Ek hi task tha aur wo complete bhi ho gaya — 100% productivity!
       Abhi koi pending nahi hai. Ek naya task add karo kuch productive karne ke liye."

── RULE 8: User asks a general knowledge question ─────────────────────────────
SITUATION: User asks about a topic (health, tips, facts, how-to) that is NOT
           specifically about their task list.
SIGNALS: "pani kab pina chahiye" (when to drink water — health tip, not a task search)
         "best time to study", "ye kaise karte hain", "X kya hota hai"
ACTION: NO task action. Just answer the question in text.
REPLY: Answer naturally. Do not emit any TASKFLOW_ACTION.

── RULE 9: Ambiguous — could be completion OR question ────────────────────────
SITUATION: User message is unclear. Check pending tasks list first.
           If a pending task closely matches what user described doing → assume RULE 1.
           If no match → ask one short clarifying question.
ACTION: complete_task if match found, else ask clarification
REPLY: If asking, be brief: one question only.

── RULE 10: Draft in progress ─────────────────────────────────────────────────
SITUATION: A task draft is already being built (fields in draft context).
           User provides more information about it.
ACTION: emit update_draft with new fields. Do NOT re-ask collected fields.
        When all 4 core fields (name, priority, due_date, category) are ready →
        emit confirm_task to show preview.
REPLY: Acknowledge what was added, ask for the next missing field only.
"""

# ── Main chat system prompt ───────────────────────────────────────────────────

CHAT_SYSTEM = """You are TaskFlow AI — a sharp, no-filler productivity assistant inside a terminal task manager.

TODAY: {today}

=== LANGUAGE RULE ===
Detect the language/style of each user message and reply in the EXACT same language.
English → English | Hindi → Hindi | Hinglish → Hinglish | any other → match it.
Never switch language. Never translate.

=== ACTION PLAYBOOK ===
{action_playbook}

=== CURRENT TASK STATE ===
{task_stats}

- total_tasks=0 → user has NO tasks. Say so clearly. Offer to add one.
- PAST DATE RULE: If user provides a due_date that is before TODAY ({today}), always flag it.
  Say: "Ye date past mein hai — sahi date kya hai?" Do NOT silently save past dates.
- Never show a task list when there are 0 tasks — just say so in plain text.
- If overdue > 0, mention it when user asks about tasks or analytics.

=== PENDING TASKS — USE EXACT IDs ===
{task_list_context}
When emitting complete_task / delete_task / edit_task → copy the ID EXACTLY from above.
NEVER invent or guess a task_id. If no match found → ask user to clarify.

=== ⚠ ANTI-HALLUCINATION RULE (CRITICAL) ===
You only know task COUNTS (total, pending, completed, overdue) from stats above.
You do NOT know actual task names, due dates, priorities, or IDs.
NEVER write specific task details in your text reply — not even as examples.
When user asks to see tasks → say only "Yeh raha:" / "Here you go:" and emit list_tasks.
The system will fetch and display the REAL task data. You inventing task info = serious bug.

=== CURRENT TASK DRAFT ===
{draft_context}

=== DETECTED USER INTENT ===
{intent_context}

=== LOCATION & WEB SEARCH CONTEXT ===
{location_context}

If web search results are in the prompt: use them to answer naturally. Don't say "search results show".

=== AVAILABLE ACTIONS ===
Append at the very END of your reply — nothing after it:
TASKFLOW_ACTION:{{"action":"ACTION_NAME","data":{{...}}}}

  update_draft   → {{name?, priority?, due_date?, due_time?, category?, notes?, reminder_at?, recurrence?, recurrence_end_date?}}
  confirm_task   → full task fields for preview
  create_task    → {{name, priority, due_date, due_time?, category, notes?, reminder_at?, recurrence?, recurrence_end_date?}}
  clear_draft    → {{}}
  search_tasks   → {{query}}
  list_tasks     → {{status?, category?, priority?}}
  edit_task      → {{task_id, updates:{{field:value,...}}}}  -- valid fields: name,category,priority,due_date,due_time,notes,reminder_at,recurrence
  set_reminder   → {{task_id, reminder_at: "YYYY-MM-DD HH:MM"}}  -- use when user asks to remind about existing task
  complete_task  → {{task_id}}
  delete_task    → {{task_id}}
  show_analytics → {{}}

=== STYLE ===
- 1-2 sentences max unless explaining something complex.
- No "Certainly!", "Of course!", "Great!" filler.
- Direct, human, helpful.
""".replace("{action_playbook}", ACTION_PLAYBOOK)

# ── Response Validator judge prompt ──────────────────────────────────────────

JUDGE_SYSTEM = """You are a strict quality checker for an AI assistant's responses.

Score the response 0-10 based on:
- Is it a complete, coherent sentence? (not truncated mid-word)
- Does it actually address the user's message?
- Is it free of random symbols, JSON fragments, or gibberish?
- Is it in a language the user would understand?

IMPORTANT EXCEPTIONS — these are valid responses, score them 8+:
- Very short replies like "Yeh raha:", "Here you go:", "Dekh lo:", "Done!" are valid
  when the user asked to list/show tasks (the system shows a table separately)
- Completion confirmations like "✓ Done!" or "Ho gaya!" are valid
- A reply that says only "Theek hai." or "Ok." after agreeing to something is valid
- Analytics summaries that give an overall verdict + highlights are valid even if they
  don't repeat every raw number (the chart renders separately — repetition = bad)

Return ONLY a JSON object, nothing else:
{"score": <0-10>, "reason": "<one short sentence>", "is_valid": <true|false>}

A score of 5+ = valid. Below 5 = invalid (retry needed).
"""


class AIGateway:

    def _expired(self):
        return date.today() > EXPIRY

    # ── IP → City ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_city_from_ip() -> str | None:
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
            # ONLY extract "text" type blocks — NEVER fall back to thinking/reasoning.
            # Thinking blocks are internal model cognition; leaking them causes validator
            # failures because they start with JSON fragments, symbols, or raw markdown.
            text_parts = [
                b.get("text", "")
                for b in raw
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            result = " ".join(text_parts).strip()
            return result or None   # Return None if no text block → triggers retry

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
                # Skip reasoning/thinking blocks entirely
                if block.get("type") in ("reasoning", "thinking"):
                    return None
            except json.JSONDecodeError:
                pass

        text_match = re.search(
            r'"type"\s*:\s*"text".*?"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
            raw, re.DOTALL
        )
        if text_match:
            return text_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()

        # If raw looks like a thinking/reasoning block, discard it
        if re.search(r'"type"\s*:\s*"(?:reasoning|thinking)"', raw):
            return None

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

                # Main server returns {"reply": "clean string", "thinking": "...", "status": "success"}
                # Priority: reply > response > content > message > text > output
                # If "reply" is a clean string (which it always is from /api/deepshi-chat),
                # use it directly without running _extract_text on it.
                raw = (
                    data.get("reply") or data.get("response") or data.get("content")
                    or data.get("message") or data.get("text") or data.get("output")
                )

                # If raw is already a plain string (most common case), use it directly.
                # Only run _extract_text when raw is a list/dict (block format).
                if isinstance(raw, str):
                    text = raw.strip() or None
                else:
                    text = self._extract_text(raw)

                # Scrub any reasoning/thinking content that leaked into the reply.
                # Happens when parse_deepshi_sse()'s except-fallback appends raw
                # SSE chunks (containing reasoning_content) to the text buffer.
                if text:
                    text = self._strip_thinking(text) or None

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

    def _call_with_r1_fallback(self, prompt, history=None, timeout=45, **extra):
        """
        Tries deepshi-r2 first. If it returns 504/502/503 or times out,
        immediately falls back to deepshi-r1 — no 25s sleep, no hang.
        Returns (text, error, used_model).

        Timeout strategy (independent of caller's `timeout` param):
          r2 = 70s  — slow model, needs runway; was timing out at 45s
          r1 = 35s  — fast model, 35s is plenty; keeps total worst-case at ~105s
        """
        R2_TIMEOUT = 70   # r2 is slow — give it room to breathe
        R1_TIMEOUT = 35   # r1 is fast — no need to wait longer

        # --- Attempt r2 with a short-circuit timeout ---
        payload = {
            "model":   DEEPSHI,
            "prompt":  prompt,
            "history": (history or [])[-12:],
            **extra,
        }
        try:
            resp = requests.post(PROXY_URL, json=payload, headers=HEADERS, timeout=R2_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                raw  = (
                    data.get("reply") or data.get("response") or data.get("content")
                    or data.get("message") or data.get("text") or data.get("output")
                )
                text = raw.strip() if isinstance(raw, str) else self._extract_text(raw)
                if text:
                    text = self._strip_thinking(text) or None
                if text and not self._is_proxy_error(text):
                    return text, None, DEEPSHI
            # r2 returned non-200 — fall through to r1
            print(f"  [fallback] r2 returned HTTP {resp.status_code}, switching to r1", flush=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  [fallback] r2 timed out ({e}), switching to r1", flush=True)
        except Exception as e:
            print(f"  [fallback] r2 error ({e}), switching to r1", flush=True)

        # --- Fall back to r1 ---
        text, err = self._call(DEEPSHI_R1, prompt, history=history, timeout=R1_TIMEOUT, **extra)
        return text, err, DEEPSHI_R1

    @staticmethod
    def _scrub_leaked_json(text: str) -> str:
        """
        DEEPSHI sometimes leaks a JSON blob into the text portion just before
        TASKFLOW_ACTION (or instead of it). Strip any trailing OR leading {...}
        that looks like an action object from the reply text.
        """
        # Remove trailing JSON objects
        cleaned = re.sub(r'\s*\{[^{}]*"action"\s*:[^{}]*\}\s*$', '', text).strip()
        # Also remove trailing code-fenced JSON blocks
        cleaned = re.sub(r'\s*```(?:json)?\s*\{.*?\}\s*```\s*$', '', cleaned, flags=re.DOTALL).strip()
        # NEW: also strip LEADING action JSON blobs (model sometimes puts action first)
        cleaned = re.sub(r'^\s*\{[^{}]*"action"\s*:[^{}]*\}\s*', '', cleaned).strip()
        cleaned = re.sub(r'^\s*```(?:json)?\s*\{.*?\}\s*```\s*', '', cleaned, flags=re.DOTALL).strip()
        return cleaned or text

    # ── ✅ Thinking-leak scrubber ─────────────────────────────────────────────

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """
        Strips leaked reasoning/thinking content from Deepshi SSE replies.

        Root cause: parse_deepshi_sse() in main.py has an `except` fallback
        that does `content += data` — meaning raw SSE lines (JSON blobs with
        reasoning_content) get appended to the text reply when JSON parsing
        fails on a chunk.

        We fix this on the client side so enable_thinking=True can stay ON
        (better output quality) without poisoning the user-facing text.

        What we strip:
        1. Raw SSE lines leaked verbatim  → `data: {...}`
        2. <thinking>...</thinking> style XML blocks
        3. Orphaned JSON fragments with reasoning_content key
        4. Leading/trailing whitespace after cleaning
        """
        if not text:
            return text

        # 1. Remove raw SSE data lines that leaked into the reply
        #    e.g. `data: {"choices":[{"delta":{"reasoning_content":"…"}}]}`
        text = re.sub(
            r'data:\s*\{[^\n]*"reasoning_content"[^\n]*\}\s*',
            '', text
        )
        # Generic SSE data: lines that look like raw event-stream fragments
        text = re.sub(r'(?m)^data:\s*\{.*?\}\s*$', '', text)

        # 2. XML-style thinking blocks  <thinking>…</thinking>
        text = re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', text, flags=re.DOTALL)

        # 3. Orphan JSON objects containing reasoning_content anywhere in text
        text = re.sub(
            r'\{[^{}]*"reasoning_content"\s*:[^{}]*\}',
            '', text
        )

        # 4. Trailing/leading artefacts left by above passes
        text = re.sub(r'\n{3,}', '\n\n', text)   # collapse excessive blank lines
        return text.strip()

    # ── ✅ NEW: Rule-based fast validator ─────────────────────────────────────

    def _fast_validate(self, text: str) -> tuple[bool, str]:
        """
        Quick heuristic checks before spending tokens on the judge.
        NOTE: receives already-stripped text (no ACTION_TAG, no leaked JSON).
        Returns (is_valid, reason).
        """
        if not text or len(text.strip()) < MIN_REPLY_LENGTH:
            return False, f"Response too short ({len(text.strip()) if text else 0} chars)"

        t = text.strip()

        # Strip leading markdown formatting before checking start character
        # (DEEPSHI sometimes returns **bold**, # heading, or `inline code` — all fine)
        # ← backtick added: model wraps analytics/stats replies in `...` code spans
        t_check = re.sub(r'^[\*_#`]+\s*', '', t)

        # Starts with TRULY garbage chars: JSON fragments, brackets, pipes, slashes
        # Note: !, ?, ., #, *, ` removed from this set — they appear in valid responses
        if re.match(r'^[,\{\}\[\]<>|\\\/^&~]+', t_check or t):
            return False, "Response starts with punctuation/symbols"

        # Ends abruptly mid-word or with open bracket
        if re.search(r'[\{\[\(]\s*$', t):
            return False, "Response ends with unclosed bracket"

        # Contains raw JSON key-value fragments (after all cleanup, this is a real problem)
        if re.search(r'"action"\s*:\s*"[a-z_]+"', t):
            return False, "Response still contains action JSON in text body"

        # Detect proxy/model error responses that slip through as HTTP 200
        # These look like valid text but are actually error messages from the model/proxy
        _ERROR_STARTERS = (
            "i'm sorry, i ", "i am sorry, i ", "i apologize",
            "sorry, i ", "sorry, there ", "sorry, the ",
            "an error occurred", "i encountered an error",
            "i cannot access", "i don't have access", "i do not have access",
            "unable to process", "failed to process",
            "i'm unable to", "i am unable to",
        )
        t_lower = t.lower()
        for phrase in _ERROR_STARTERS:
            if t_lower.startswith(phrase):
                return False, f"Response appears to be a model/proxy error message"

        # Pure whitespace / newlines
        if not t.replace('\n', '').replace('\r', '').strip():
            return False, "Response is only whitespace"

        # Suspiciously short reply that looks truncated (word cut mid)
        # ':' added — "Yeh raha:" and "Here you go:" are valid list responses
        words = t.split()
        if len(words) <= 3 and not any(c in t for c in '.?!।:'):
            return False, f"Response suspiciously short ({len(words)} words, no sentence ender)"

        return True, "ok"

    # ── ✅ NEW: Haiku judge (AI validates AI) ─────────────────────────────────

    def _judge_response(self, user_msg: str, ai_reply: str) -> tuple[bool, int, str]:
        """
        Sends user message + AI reply to Haiku for quality scoring.
        Returns (is_valid, score, reason).
        Fast: Haiku responds in ~3-5s.
        """
        prompt = (
            f"{JUDGE_SYSTEM}\n\n"
            f"User message: \"{user_msg[:300]}\"\n"
            f"AI reply: \"{ai_reply[:500]}\"\n\n"
            f"JSON:"
        )
        result, err = self._call(DEEPSHI_R1, prompt, timeout=12)
        if err or not result:
            # If judge itself fails, assume valid (don't block forever)
            return True, 6, "Judge unavailable — assuming valid"

        try:
            clean  = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
            score  = int(parsed.get("score", 6))
            reason = parsed.get("reason", "")
            valid  = parsed.get("is_valid", score >= JUDGE_THRESHOLD)
            return bool(valid), score, reason
        except (json.JSONDecodeError, ValueError, TypeError):
            return True, 6, f"Judge parse error: {result[:60]}"

    # ── ✅ NEW: Combined validation pipeline ──────────────────────────────────

    # Intents where the reply is intentionally short (chart/table renders separately).
    # Skip the AI judge for these — it always rates short replies poorly.
    _JUDGE_SKIP_INTENTS = {"analytics", "list_tasks", "search_tasks", "complete_task", "delete_task"}

    def _validate_response(self, user_msg: str, raw_reply: str, intent: str = "") -> tuple[bool, str]:
        # Pass 1: strip action tag
        reply_clean = (
            raw_reply.split(ACTION_TAG, 1)[0].strip()
            if ACTION_TAG in raw_reply
            else raw_reply
        )
        # Pass 2: strip leaked action JSON
        reply_clean = self._scrub_leaked_json(reply_clean)

        # Pass 3: strip any surviving think/thinking tags
        reply_clean = self._strip_thinking(reply_clean)

        # Stage 1 — fast rules
        fast_ok, fast_reason = self._fast_validate(reply_clean)
        if not fast_ok:
            return False, f"[fast-check] {fast_reason}"

        # Stage 2 — AI judge (skipped for intents where short reply is expected)
        if intent in self._JUDGE_SKIP_INTENTS:
            print(f"  [validator] judge skipped for intent='{intent}' — fast-check passed", flush=True)
            return True, "ok"

        judge_ok, score, judge_reason = self._judge_response(user_msg, reply_clean)
        if not judge_ok:
            return False, f"[judge score={score}] {judge_reason}"

        return True, "ok"

    # ── ✅ NEW: Prompt Enhancer ────────────────────────────────────────────────

    def enhance_prompt(self, user_message: str, history=None, draft=None) -> str:
        """
        Haiku call (~3s) that rewrites the user's message to be unambiguous
        before it hits the classifier and main AI.

        Resolves:
        - Pronouns → actual task names  ("us task" → "Pani peena task")
        - Follow-up questions           ("iska due date?" → "Pani peena task ka due date kya hai?")
        - Mixed-language ambiguity
        - Conversational shortcuts      ("haan", "wahi wala", "isko", "pehle wala")

        Returns the enhanced message string. On failure returns original unchanged.
        """
        if not history and not draft:
            return user_message  # no context to resolve against, skip

        recent_ctx = ""
        if history:
            recent_ctx = "\n".join(
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
                for m in history[-6:]
            )

        draft_ctx = ""
        if draft:
            draft_ctx = "Current task draft: " + ", ".join(
                f"{k}={v}" for k, v in draft.items() if v
            )

        prompt = f"""You are a message clarifier for a multilingual task manager chatbot.

Use this intent rulebook to understand what the user is trying to do:
{INTENT_RULEBOOK}

Your job: rewrite the user's LATEST MESSAGE to be fully self-contained and unambiguous,
so the intent classifier and main AI are not confused by pronouns or follow-up shortcuts.

STRICT RULES:
1. LANGUAGE — reply in the EXACT SAME language/style as the user's original message.
   Hindi → Hindi, Hinglish → Hinglish, English → English, Punjabi → Punjabi.
   NEVER add a language that wasn't in the original. NEVER translate.

2. PRONOUN RESOLUTION — replace vague references with actuals from history:
   "us task" / "isko" / "woh" / "wahi wala" / "it" / "that" → actual task name or ID

3. COMPLETION SIGNALS — if user says they did something matching a pending task,
   make it explicit: "Maine [task name] complete kar liya — please isko done mark karo"

4. FOLLOW-UP SHORTCUTS — "haan" / "theek hai" / "ok" → spell out what they agreed to

5. GENERAL QUESTIONS — if the question is general knowledge (tips, facts, how-to)
   NOT about their task list → prepend "[general question]: " to the original message,
   keep the rest unchanged in the original language.

6. IF ALREADY CLEAR → return the message UNCHANGED.

7. Return ONLY the rewritten message. No explanation. No quotes.

{draft_ctx}

Conversation history:
{recent_ctx}

User's latest message: "{user_message}"

Rewritten message:"""

        result, err = self._call(DEEPSHI_R1, prompt, timeout=12)
        if err or not result:
            return user_message

        enhanced = result.strip().strip('"').strip("'")
        # Safety: if enhancer returns something wildly different (>4x length), discard
        if len(enhanced) > len(user_message) * 5:
            return user_message

        return enhanced or user_message

    # ── Intent Classifier ─────────────────────────────────────────────────────

    def classify_intent(self, user_message: str, history=None) -> dict:
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

        result, err = self._call(DEEPSHI_R1, prompt, timeout=15)
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

    # ── Chat (with validation + auto-retry) ──────────────────────────────────

    def chat(
        self,
        user_message: str,
        history=None,
        draft: dict = None,
        intent_info: dict = None,
        task_stats: dict = None,
        task_list: list = None,
        location: str = None,
    ):
        """
        Main chat. Validates every response before returning.
        Auto-retries up to CHAT_MAX_RETRIES times on garbage output.
        Returns (reply_text, action_dict | None, error)
        """
        draft = draft or {}

        # ── Build system prompt contexts ──────────────────────────────────────
        if draft:
            collected = ", ".join(f"{k}: {v}" for k, v in draft.items() if v)
            remaining = [k for k in ("name", "priority", "due_date", "category") if not draft.get(k)]
            draft_ctx = (
                f"Already collected → {collected}\n"
                f"Still missing     → {', '.join(remaining) if remaining else 'nothing (ready to confirm)'}"
            )
        else:
            draft_ctx = "Empty — no task being created yet."

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

        if task_list:
            task_lines = "\n".join(
                f"  ID={t['id']} | {t['name']} | {t['priority']} | "
                f"{t.get('category','General')} | due={t.get('due_date') or 'none'}"
                for t in task_list
            )
            task_list_ctx = f"Pending tasks:\n{task_lines}"
        else:
            task_list_ctx = "Not loaded — do not invent task IDs."

        intent_name = (intent_info or {}).get("intent", "unclear")
        intent_ctx  = (
            f"Classified intent: {intent_name} — {INTENTS.get(intent_name, '')}\n"
            f"Stick to this intent. Do NOT emit unrelated task actions."
        )

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
            .replace("{today}",            today_local().isoformat())
            .replace("{draft_context}",    draft_ctx)
            .replace("{task_stats}",       stats_ctx)
            .replace("{task_list_context}", task_list_ctx)
            .replace("{intent_context}",   intent_ctx)
            .replace("{location_context}", loc_ctx)
        )

        needs_web   = (intent_info or {}).get("needs_web", False)
        user_prompt = user_message
        if needs_web and location:
            user_prompt = f"[User location: {location}]\n{user_message}"

        full_prompt = f"{system}\n\nUser: {user_prompt}"

        # ── ✅ Retry loop with validation ─────────────────────────────────────
        last_err        = None
        validation_log  = []   # track what went wrong across attempts

        for attempt in range(1, CHAT_MAX_RETRIES + 2):   # +2 → 1 original + N retries
            raw, err = self._call(
                DEEPSHI_R1,
                full_prompt,
                history=history,
                timeout=45,
                enable_thinking=True,
                session_key="taskflow_chat",
                web_search=needs_web,
            )
            used_model = DEEPSHI_R1

            if err or not raw:
                last_err = err or "No response."
                if attempt <= CHAT_MAX_RETRIES:
                    time.sleep(CHAT_RETRY_DELAY)
                    continue
                return None, None, last_err

            # Run validation pipeline
            is_valid, fail_reason = self._validate_response(user_message, raw, intent=intent_name)

            if is_valid:
                # ── Good response — parse and return ─────────────────────────
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

                if action and intent_name in NO_ACTION_INTENTS:
                    action = None

                if attempt > 1:
                    # Append a subtle note so the user knows a retry happened
                    # (purely informational — won't break anything)
                    reply = reply  # keep clean, log silently
                    print(
                        f"  [validator] attempt {attempt} succeeded "
                        f"(prev failures: {'; '.join(validation_log)})",
                        flush=True,
                    )

                return reply, action, None

            else:
                # Bad response — log it and retry
                validation_log.append(f"attempt {attempt}: {fail_reason}")
                print(
                    f"  [validator] attempt {attempt} FAILED — {fail_reason} — retrying...",
                    flush=True,
                )
                if attempt <= CHAT_MAX_RETRIES:
                    time.sleep(CHAT_RETRY_DELAY)
                # On last attempt we'll fall through to the error below

        # All attempts exhausted with bad responses
        return (
            None,
            None,
            f"AI returned low-quality responses after {CHAT_MAX_RETRIES + 1} attempts. "
            f"Try again in a moment. (Last issue: {validation_log[-1] if validation_log else 'unknown'})"
        )

    # ── NL Task Parser ───────────────────────────────────────────────────────

    def parse_task(self, text: str):
        prompt = (
            f'Parse this task. Return ONLY a JSON object, no markdown.\n'
            f'Fields:\n'
            f'  name (str, required), priority (High|Medium|Low), '
            f'category (Work|Study|Personal|Health|Finance|General),\n'
            f'  due_date (YYYY-MM-DD|null), '
            f'due_time (HH:MM 24h|null — e.g. "8 baje"→"08:00", "9pm"→"21:00"),\n'
            f'  reminder_at ("YYYY-MM-DD HH:MM"|null — set when user says remind/yaad/alert),\n'
            f'  recurrence (none|daily|weekly|weekdays|monthly — "roz"→daily, "har hafte"→weekly),\n'
            f'  recurrence_end_date (YYYY-MM-DD|null), notes (str|null)\n'
            f'Today is {today_local().isoformat()} ({tz_label()}).\n'            f'IMPORTANT: due_date must be today or in the future. If user gives a past date,\n'            f'set due_date to null and add a note in the notes field: "User gave past date: <their date>".\n\n'
            f'Input: "{text}"\nJSON:'
        )
        result, err = self._call(DEEPSHI_R1, prompt, timeout=30)
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
        return self._call(DEEPSHI_R1, prompt, timeout=30)
    # ── Multi-Agent: Prompt Decomposer ───────────────────────────────────────

    def decompose_prompt(self, user_message: str, history=None) -> list:
        """
        Splits a complex multi-intent prompt into ordered sub-tasks.
        Each sub-task: {"sub_message": str, "intent": str}
        Returns list with 1 item for simple prompts, 2+ for compound ones.
        Fast Haiku call ~2-4s. Never raises; returns single-item fallback on failure.
        """
        recent = ""
        if history:
            recent = "\n".join(
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content'][:120]}"
                for m in history[-4:]
            )

        prompt = (
            "You are a task decomposer for a multilingual task manager.\n\n"
            "Valid intents: create_task, list_tasks, search_tasks, complete_task, "
            "delete_task, edit_task, analytics, optimize, weather, general_question, chitchat\n\n"
            "Split the user message into 1 or more independent sub-tasks.\n"
            "RULES:\n"
            "1. Single intent -> list with 1 item.\n"
            "2. Mixed intents (create task AND show analytics) -> split them.\n"
            "3. Preserve the user language in each sub_message.\n"
            "4. Order: complete/delete first, list/search next, create then, analytics last.\n"
            "5. Return ONLY a JSON array, no markdown.\n\n"
            'Format: [{"sub_message": "...", "intent": "..."}, ...]\n\n'
            + (f"Recent context:\n{recent}\n\n" if recent else "")
            + f'User message: "{user_message}"\n\nJSON array:'
        )

        fallback = [{"sub_message": user_message, "intent": "unclear"}]
        result, err = self._call(DEEPSHI_R1, prompt, timeout=15)
        if err or not result:
            return fallback
        try:
            clean = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
            if isinstance(parsed, list) and parsed:
                valid = [
                    item for item in parsed
                    if isinstance(item, dict)
                    and item.get("sub_message")
                    and item.get("intent") in INTENTS
                ]
                return valid if valid else fallback
        except (json.JSONDecodeError, TypeError):
            pass
        return fallback
