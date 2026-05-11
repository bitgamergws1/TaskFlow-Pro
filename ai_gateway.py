"""
ai_gateway.py — Multi-Model AI Routing via DevNest Proxy
"""

import json
import requests
from datetime import date

PROXY_URL = "https://devnest-proxy-server.onrender.com/v1/proxy/ai"
HEADERS = {
    "X-DevNest-Token": "DEVNEST_EVAL_2026",
    "Content-Type": "application/json",
}

EXPIRY = date(2026, 5, 20)

CLAUDE  = "claude-haiku-4-5-20251001"
DEEPSHI = "deepshi-r2"


class AIGateway:

    def _expired(self):
        return date.today() > EXPIRY

    def _call(self, model, prompt, timeout=75):
        if self._expired():
            return None, "Evaluation period ended."
        try:
            resp = requests.post(
                PROXY_URL,
                json={"model": model, "prompt": prompt},
                headers=HEADERS,
                timeout=timeout,
            )
            if resp.status_code != 200:
                return None, f"Proxy returned HTTP {resp.status_code}."
            data = resp.json()
            text = (
                data.get("response")
                or data.get("reply")
                or data.get("content")
                or data.get("message")
                or data.get("text")
                or data.get("output")
            )
            if isinstance(text, list):
                text = " ".join(str(b.get("text", "")) for b in text if isinstance(b, dict))
            return str(text).strip() if text else None, None
        except requests.exceptions.Timeout:
            return None, "AI request timed out. Try again."
        except requests.exceptions.ConnectionError:
            return None, "Cannot reach proxy server."
        except Exception as e:
            return None, str(e)

    # ── Claude: Natural Language Task Parser ──────────────────────────────────

    def parse_task(self, natural_text):
        prompt = f"""Parse this task description and return ONLY a valid JSON object. No explanation, no markdown.

Fields:
- name (string): concise task title
- priority (string): High | Medium | Low
- due_date (string): YYYY-MM-DD or null
- category (string): Work | Study | Personal | Health | Finance | General
- notes (string): extra context or null

Input: "{natural_text}"

JSON only:"""

        result, err = self._call(CLAUDE, prompt, timeout=30)
        if err or not result:
            return None, err or "No response from AI."
        try:
            clean = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(clean), None
        except json.JSONDecodeError:
            return None, f"Could not parse AI response: {result[:100]}"

    # ── Deepshi R2: Full Day Schedule Optimizer ───────────────────────────────

    def optimize_schedule(self, tasks):
        if not tasks:
            return None, "No pending tasks to optimize."

        task_lines = "\n".join(
            f"  [{t['priority']}] {t['name']} | Due: {t.get('due_date') or 'flexible'} | {t.get('category', 'General')}"
            for t in tasks
        )

        prompt = f"""You are a productivity expert. Build a focused time-blocked schedule for today using these pending tasks:

{task_lines}

Rules:
- Working hours: 9:00 AM to 9:00 PM
- High priority tasks first, then Medium, then Low
- Group tasks by category when possible
- Include a 15-min break every 90 minutes
- Use 25-min Pomodoro blocks for deep work tasks
- Be realistic — do not cram everything in

Format every block exactly like this (one per line):
⏰ HH:MM AM - HH:MM AM | Task Name | [Priority] | Category

End with a single motivational line starting with 💡"""

        return self._call(DEEPSHI, prompt, timeout=90)

    # ── Deepshi R2: Daily Motivation / Roast ──────────────────────────────────

    def get_motivation(self, stats):
        p  = stats.get("productivity", 0)
        c  = stats.get("completed", 0)
        pn = stats.get("pending", 0)
        ov = stats.get("overdue", 0)
        sk = stats.get("streak", 0)

        tone = "savage roast + kick" if p < 30 else ("powerful praise + energy" if p >= 70 else "balanced push")

        prompt = f"""You are a sharp productivity coach. Give a 3-4 line daily message in this tone: {tone}.

Today's stats:
- Completed tasks: {c}
- Pending tasks: {pn}
- Overdue tasks: {ov}
- Productivity rate: {p}%
- Day streak: {sk} days

Be direct, witty, specific to the numbers. No filler. No corporate speak. End with a power line."""

        return self._call(DEEPSHI, prompt, timeout=30)
