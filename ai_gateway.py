"""
ai_gateway.py — Multi-Model AI Routing via DevNest Proxy
         + Response Validator & Auto-Retry (v2)
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

# ── Validation settings ───────────────────────────────────────────────────────
CHAT_MAX_RETRIES   = 2          # max auto-retries on bad response
CHAT_RETRY_DELAY   = 3          # seconds between retries
MIN_REPLY_LENGTH   = 8          # a valid reply must have at least 8 chars
JUDGE_THRESHOLD    = 5          # judge score below this → retry (0-10 scale)

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

INTENT_TO_ACTIONS = {
    "create_task":      {"update_draft", "confirm_task", "create_task", "clear_draft"},
    "list_tasks":       {"list_tasks"},
    "search_tasks":     {"search_tasks"},
    "complete_task":    {"complete_task"},
    "delete_task":      {"delete_task"},
    "edit_task":        {"edit_task"},
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
         "X karna hai note kar lo", "save this: X"
ACTION: emit update_draft with extracted fields, ask for missing ones one at a time
REPLY: Confirm what you captured, ask for 1-2 missing fields (not all at once)

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
SIGNALS: "kitne complete kiye", "meri productivity", "stats", "streak kitna hai"
ACTION: emit show_analytics
REPLY: Brief summary in user's language.

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
- Never show a task list when there are 0 tasks — just say so in plain text.
- If overdue > 0, mention it when user asks about tasks or analytics.

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

  update_draft   → {{name?, priority?, due_date?, category?, notes?}}
  confirm_task   → full task fields for preview
  create_task    → {{name, priority, due_date, category, notes?}}
  clear_draft    → {{}}
  search_tasks   → {{query}}
  list_tasks     → {{status?, category?, priority?}}
  edit_task      → {{task_id, updates:{{field:value,...}}}}
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

    @staticmethod
    def _scrub_leaked_json(text: str) -> str:
        """
        DEEPSHI sometimes leaks a JSON blob into the text portion just before
        TASKFLOW_ACTION (or instead of it). Strip any trailing {...} or {...}
        that looks like an action object from the end of the reply text.
        """
        # Remove trailing JSON objects: optional whitespace then {...}
        cleaned = re.sub(r'\s*\{[^{}]*"action"\s*:[^{}]*\}\s*$', '', text).strip()
        # Also remove trailing code-fenced JSON blocks
        cleaned = re.sub(r'\s*```(?:json)?\s*\{.*?\}\s*```\s*$', '', cleaned, flags=re.DOTALL).strip()
        return cleaned or text

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

        # Starts with garbage punctuation/symbols (like ', so may{')
        if re.match(r'^[,\.\!\?\{\}\[\]<>|\\\/\*#@%^&~`]+', t):
            return False, "Response starts with punctuation/symbols"

        # Ends abruptly mid-word or with open bracket
        if re.search(r'[\{\[\(]\s*$', t):
            return False, "Response ends with unclosed bracket"

        # Contains raw JSON key-value fragments (after all cleanup, this is a real problem)
        if re.search(r'"action"\s*:\s*"[a-z_]+"', t):
            return False, "Response still contains action JSON in text body"

        # Pure whitespace / newlines
        if not t.replace('\n', '').replace('\r', '').strip():
            return False, "Response is only whitespace"

        # Suspiciously short reply that looks truncated (word cut mid)
        words = t.split()
        if len(words) <= 3 and not any(c in t for c in '.?!।'):
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
        result, err = self._call(CLAUDE, prompt, timeout=12)
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

    def _validate_response(self, user_msg: str, raw_reply: str) -> tuple[bool, str]:
        """
        Stage 1: fast heuristics (no API call)
        Stage 2: Haiku judge (only if Stage 1 passes)
        Returns (is_valid, failure_reason)

        Cleans the reply in two passes before validation:
        1. Strip TASKFLOW_ACTION tag (internal protocol JSON)
        2. Strip any leaked action JSON that DEEPSHI leaked into the text body
        Both the fast checker and judge only see the clean user-facing text.
        """
        # Pass 1: strip action tag
        reply_clean = (
            raw_reply.split(ACTION_TAG, 1)[0].strip()
            if ACTION_TAG in raw_reply
            else raw_reply
        )
        # Pass 2: strip any leaked action JSON from end of text body
        reply_clean = self._scrub_leaked_json(reply_clean)

        # Stage 1 — instant rules (on double-cleaned text)
        fast_ok, fast_reason = self._fast_validate(reply_clean)
        if not fast_ok:
            return False, f"[fast-check] {fast_reason}"

        # Stage 2 — AI judge (never sees action JSON)
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

        result, err = self._call(CLAUDE, prompt, timeout=12)
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

    # ── Chat (with validation + auto-retry) ──────────────────────────────────

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
            .replace("{today}",            date.today().isoformat())
            .replace("{draft_context}",    draft_ctx)
            .replace("{task_stats}",       stats_ctx)
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
                DEEPSHI,
                full_prompt,
                history=history,
                timeout=120,
                enable_thinking=True,
                session_key="taskflow_chat",
                web_search=needs_web,
            )

            if err or not raw:
                last_err = err or "No response."
                if attempt <= CHAT_MAX_RETRIES:
                    time.sleep(CHAT_RETRY_DELAY)
                    continue
                return None, None, last_err

            # Run validation pipeline
            is_valid, fail_reason = self._validate_response(user_message, raw)

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
