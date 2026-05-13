# TaskFlow Pro — Cyber-Sync Edition

> **DevNest Python Developer Internship | Week 1 Project**
> A professional, AI-powered terminal task manager built on a hybrid offline-first + cloud-sync architecture.

---

## Table of Contents

- [Overview](#overview)
- [What's Inside](#whats-inside)
- [Quick Start](#quick-start)
- [Manual Setup](#manual-setup)
- [Zero Configuration](#zero-configuration)
- [Supabase Cloud Sync Setup](#supabase-cloud-sync-setup)
- [Commands Reference](#commands-reference)
- [AI Features](#ai-features)
- [Architecture](#architecture)
- [Data Storage](#data-storage)
- [Features Checklist](#features-checklist)
- [Dependencies](#dependencies)
- [Project Structure](#project-structure)
- [Submission](#submission)

---

## Overview

TaskFlow Pro is a fully offline-capable, AI-augmented terminal task manager built for the **DevNest Python Developer Internship Week 1** assignment. It combines:

- A **Rich-powered** cyberpunk CLI dashboard for a beautiful terminal experience
- **SQLite** as the primary database — zero latency, works with no internet
- **Supabase** for background cloud sync — your tasks follow you across devices
- **Multi-agent AI pipeline** for natural-language task parsing, validation, and scheduling
- **Intelligent reminder daemon** — background thread fires bell notifications right in the terminal
- **Recurrence engine** — repeating tasks (daily, weekly, weekdays, monthly)
- A **Render-hosted proxy server** that keeps all API keys off your machine entirely

The app is designed to require **no secrets on the client machine**. You clone it, run one script, and you're live.

---

## What's Inside

| File | Role |
|---|---|
| `main.py` | CLI entry point — all commands, Rich UI, Pomodoro timer, animated AI thinking display |
| `controller.py` | Logic bridge between database and AI — routes intents to actions |
| `database.py` | SQLite engine + background Supabase sync + reminder daemon queries |
| `ai_gateway.py` | Multi-model AI routing, multi-agent decomposition, response validator, prompt enhancer |
| `timezone_utils.py` | Dynamic timezone detection via IP — powers all date/time comparisons correctly |
| `supabase_setup.sql` | Run once in Supabase SQL Editor to set up cloud sync |
| `run.sh` | One-command setup and launch — Linux / macOS |
| `run.bat` | One-command setup and launch — Windows |
| `taskflow` | Short command wrapper — Linux / macOS (`taskflow add`, `taskflow list`, ...) |
| `taskflow.bat` | Short command wrapper — Windows CMD |

---

## Quick Start

### 🐧 Linux / macOS

**One command — paste and go:**

```bash
git clone https://github.com/bitgamergws1/TaskFlow-Pro.git && cd TaskFlow-Pro && chmod +x run.sh && ./run.sh
```

Already cloned? Just:

```bash
chmod +x run.sh && ./run.sh
```

---

### 🪟 Windows (CMD / PowerShell)

**One command — paste in CMD or PowerShell:**

```cmd
git clone https://github.com/bitgamergws1/TaskFlow-Pro.git && cd TaskFlow-Pro && run.bat
```

Already cloned? Just:

```cmd
run.bat
```

> **Note for Windows users:** Make sure Python is added to PATH during installation (check "Add Python to PATH" on the Python installer screen). Windows also requires the `tzdata` package for IANA timezone support — `run.bat` handles this automatically.

---

Both scripts automatically:

1. **Check** Python 3.9+ is installed
2. **Create** a virtual environment (`venv/`)
3. **Install** all dependencies from `requirements.txt`
4. **Check** timezone data (`tzdata`) is available
5. **Launch** the TaskFlow Pro dashboard

On first launch you'll see the Rich dashboard with a live AI motivation/roast message. All tasks are stored locally in `tasks.db` — cloud sync happens silently in the background.

---

## Manual Setup

If you prefer step-by-step control instead of the setup scripts:

**Linux / macOS:**

```bash
git clone https://github.com/bitgamergws1/TaskFlow-Pro.git
cd TaskFlow-Pro
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

**Windows (CMD):**

```cmd
git clone https://github.com/bitgamergws1/TaskFlow-Pro.git
cd TaskFlow-Pro
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/bitgamergws1/TaskFlow-Pro.git
cd TaskFlow-Pro
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

> **No configuration needed.** The app is ready to run immediately after `pip install`. All API keys and Supabase credentials are baked into the DevNest proxy server — your machine holds zero secrets.

---

## Zero Configuration

**There is no `.env` file.** The app requires zero configuration on your machine.

All API keys, the Supabase URL, and the Supabase anon key live exclusively on the **DevNest Render proxy server**. They are hardcoded server-side and never transmitted to the client.

The only thing `database.py` needs to run is a writable directory for `tasks.db` — which defaults to the project folder automatically:

```python
DB_PATH = os.getenv("DB_PATH", "tasks.db")   # default: tasks.db in project root
```

If you ever want the database stored somewhere else, you can set `DB_PATH` as a shell variable before running — but this is entirely optional:

```bash
DB_PATH=/tmp/mytasks.db python main.py
```

---

## Supabase Cloud Sync Setup

Supabase credentials live **only on the Render proxy server** — never on your machine. Follow these two steps to enable cloud sync.

### Step 1 — Set up the Supabase table

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor → New Query**
3. Paste the entire contents of `supabase_setup.sql` and click **Run**

This creates the `tasks` table with the correct schema, RLS policies, and indexes that the proxy server expects. The schema includes all columns for reminders, recurrence, and due times.

### Step 2 — Add environment variables to the Render proxy

1. Go to your Render service dashboard → **Environment** tab
2. Add these two variables:

```
SUPABASE_URL       = https://your-project-id.supabase.co
SUPABASE_ANON_KEY  = your-anon-public-key
```

3. Render will **auto-redeploy** with the new secrets — takes about 30 seconds

That's it. Every task write from the CLI (add / complete / delete / restore / edit) will silently sync through the proxy to Supabase — no credentials on the client machine, no blocking of your terminal.

> **How sync works under the hood:** `database.py` spawns a background daemon thread on every write. That thread sends the task payload to the DevNest proxy over HTTPS. The proxy verifies the token, injects the Supabase credentials server-side, and upserts to your cloud table. If the proxy is unreachable (offline), the write is silently dropped — your local SQLite data is always the source of truth.

---

## Commands Reference

### Running Commands

The project includes a `taskflow` shortcut so you don't have to type `python main.py` every time.

**Linux / macOS** — run once:
```bash
chmod +x taskflow
```

**Windows CMD** — `taskflow.bat` is already included, just use `taskflow <command>`.

> Both `taskflow` and `python main.py` are identical — use whichever you prefer.

---

### Core Task Management

```
taskflow                              → Dashboard + weather widget + AI daily brief
taskflow add                          → Add a task interactively (with reminders + recurrence)
taskflow add --ai                     → Natural language task parsing
taskflow list                         → List all active tasks
taskflow list --status pending        → Filter: pending | completed
taskflow list --category Work         → Filter by category
taskflow list --priority High         → Filter: High | Medium | Low
taskflow complete <ID>                → Mark task as done ✓
taskflow complete                     → Pick from pending list interactively
taskflow delete <ID>                  → Soft-delete → recycle bin
taskflow delete                       → Pick from list interactively
taskflow restore <ID>                 → Restore from recycle bin
taskflow restore                      → Pick from bin interactively
taskflow bin                          → View recycle bin
taskflow edit <ID>                    → Edit any field interactively (with reminder validation)
taskflow search "keyword"             → Search name, notes, category
taskflow weather                      → Show current weather (auto-detects city from IP)
taskflow weather "Shimla"             → Set your city and show weather
```

### Reminders & Recurrence (via `taskflow add` or `taskflow edit`)

When adding or editing a task you will be offered:

- **Due time** — set `HH:MM` alongside the due date for time-specific tasks
- **Reminder** — set a `YYYY-MM-DD HH:MM` reminder that fires in the terminal while `taskflow chat` is open
- **Recurrence** — `daily`, `weekly`, `weekdays`, or `monthly`; optionally set an end date

> Reminders are validated — the app refuses to save a past reminder time and warns if the reminder is set after the task's due time.

### AI Chat (`taskflow chat`)

Start a natural-language session where you can manage tasks by just talking. Supports English, Hindi, and Hinglish — AI matches your language automatically.

**What happens behind the scenes every time you send a message:**

```
Step 0 — Prompt Enhancement    Resolve pronouns, shortcuts, follow-ups
Step 1 — Decomposition         Split compound requests into ordered sub-tasks
Step 2 — Intent Classification Detect what you want (complete_task / create_task / ...)
Step 3 — Main AI Call          Generate reply + structured action (with live thinking animation)
Step 4 — Response Validation   Fast rules + AI judge score; auto-retry on bad output
Step 5 — Action Dispatch       Execute the action (save task, mark done, etc.)
```

**Slash commands inside chat:**

```
/add              Start a fresh task creation
/list             Show all tasks
/list pending     Filter by status
/list Work        Filter by category
/done <ID>        Complete a task
/del <ID>         Delete a task
/search <query>   Search tasks
/optimize         Generate AI schedule
/stats            Show analytics
/report           Export Markdown report
/draft            Show current task draft
/clear            Clear current draft
/help             Show all slash commands
/exit             Leave chat
```

**How chat draft memory works:**

1. You say `"add a math assignment"` → AI stores `name: Math Assignment` in draft
2. AI asks for priority → you say `"high"` → draft updates: `priority: High`
3. You suddenly ask `"show my pending tasks"` → AI lists tasks, **draft is preserved**
4. You say `"ok continue"` → AI remembers draft, asks for due date
5. All 4 mandatory fields ready (name, priority, due_date, category) → AI shows a **preview card**, asks you to confirm before saving
6. You confirm → task saved, draft cleared

**Reminder daemon in chat:** While `taskflow chat` is running, a background thread checks every 30 seconds for due reminders. When a reminder fires, a bold 🔔 notification prints directly in your terminal — no external notification system needed.

### AI-Powered Commands

```
taskflow optimize                     → Full AI time-blocked daily schedule
taskflow focus <ID>                   → 25-minute Pomodoro timer
taskflow focus <ID> --minutes 50      → Custom duration
```

### Reporting & Analytics

```
taskflow analytics                    → Analytics + ASCII bar charts
taskflow export                       → Export Markdown report
```

---

## AI Features

### Multi-Agent Pipeline (Chat Mode)

The chat mode runs a **4-stage multi-agent pipeline** on every message:

| Stage | What it does |
|---|---|
| Prompt Enhancer | Resolves pronouns, follow-ups, ambiguity — rewrites message to be unambiguous |
| Decomposer | Splits compound requests into ordered independent sub-tasks |
| Intent Classifier | Tags each sub-task with one of 12 intents using a multilingual rulebook |
| Main Chat AI | Generates reply + structured `TASKFLOW_ACTION` using an action playbook |

Each stage is a separate AI call routed through the DevNest proxy — compound requests like _"mark gym done and show me analytics"_ are split, processed in order, and rendered independently.

### Response Validator

Every AI response goes through a two-stage validation before being shown to you:

1. **Fast rules** — checks for minimum length, garbage characters, truncated output, leaked JSON, proxy error patterns
2. **AI judge** — scores the reply 0–10 for coherence, relevance, and language match; replies below threshold are retried

If validation fails, the pipeline automatically retries up to 2 times with a brief delay. The judge is skipped for intents where a short reply is expected (list, analytics, complete) to avoid false positives.

### Animated Thinking Display

While any AI call is running, a live spinner shows **intent-aware progress messages** — different messages for create_task vs optimize vs analytics vs chitchat, cycling every ~1.5 seconds. After 3 seconds an elapsed-time counter also appears so you always know the AI is actively working.

### Natural Language Task Parsing (`taskflow add --ai`)

Describe your task in plain English or Hinglish:

```
Kal subah tak law ka revision karna hai, priority high hai
```

**Parsed output:**
```json
{
  "name": "Law Revision",
  "priority": "High",
  "due_date": "2026-05-13",
  "category": "Study"
}
```

Supports extraction of: name, priority, category, due_date, due_time, reminder_at, recurrence, recurrence_end_date, notes.

### Multilingual Intent Understanding

The classifier uses a **language-agnostic rulebook** — not keyword lists. It understands meaning across English, Hindi, Hinglish, and other languages:

- _"pani pi liya"_ → `complete_task` (matched to "Drink water" pending task)
- _"ab kya karna hai?"_ → `list_tasks` (user asking what's next)
- _"pani kab pina chahiye"_ → `general_question` (health tip, not a task search)
- _"schedule banao"_ → `optimize`

### AI Schedule Optimizer

```bash
taskflow optimize
```

Sends all pending tasks to the AI, which returns a complete time-blocked daily schedule:
- Priority ordering — High first
- Pomodoro 25-min blocks with 15-min breaks every 90 minutes
- Category grouping to minimize context switching
- Realistic 9AM–9PM window

### Daily Motivation / Roast

Every dashboard open (`taskflow`) fetches a **personalized AI message** based on your stats:
- **Productivity < 30%** → savage roast 
- **Productivity ≥ 70%** → fired-up praise 
- **Streak ≥ 3 days** → streak acknowledgement with  badge

Fetched asynchronously — never delays dashboard load.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    main.py (CLI + Rich UI)                      │
│  Commands: add, list, complete, delete, restore, bin,           │
│            weather, focus, optimize, analytics, export, chat    │
│  Animated Thinking Display  |  Reminder Daemon (chat mode)      │
└──────────────────────────────┬─────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    controller.py     │
                    │  Business logic,     │
                    │  intent routing,     │
                    │  action dispatch     │
                    └──────┬──────────────┘
                           │
            ┌──────────────┼──────────────────────┐
            │              │                       │
  ┌─────────▼──────┐  ┌────▼──────────────────┐   │
  │  database.py   │  │     ai_gateway.py      │   │
  │                │  │                        │   │
  │  SQLite ──── ◄─┘  │  Prompt Enhancer       │   │
  │  (primary,        │  Decomposer            │   │
  │   0ms, offline)   │  Intent Classifier     │   │
  │                   │  Main Chat (R1/R2)     │   │
  │  Supabase ◄────── │  Response Validator    │   │
  │  (background      │  + AI Judge            │   │
  │   sync thread)    │  Schedule Optimizer    │   │
  └────────────────┘  │  Motivation Engine     │   │
                       └────────────┬──────────┘   │
                                    │               │
                    ┌───────────────▼───────────────▼──────┐
                    │        timezone_utils.py              │
                    │  IP-based timezone detection,         │
                    │  in-memory + file cache (7-day),      │
                    │  powers all date/time comparisons     │
                    └──────────────────────────────────────┘

                    DevNest Proxy Server (Render — already deployed)
                    HTTPS + token-verified | All API keys server-side
                    Routes: /v1/proxy/ai  |  /v1/proxy/sync  |  /health
```

### Model Routing

| Call type | Purpose |
|---|---|
| Prompt Enhancer | Fast — resolves pronouns and shortcuts before classification |
| Intent Classifier | Deterministic — returns structured JSON intent |
| Decomposer | Splits compound requests into ordered sub-tasks |
| AI Judge | Scores reply quality 0–10; triggers retry if below threshold |
| Main Chat | Generates reply + structured action with full context |
| Schedule Optimizer | Heavy reasoning — builds complete time-blocked daily plan |
| Motivation | Generates personalized productivity brief on dashboard |

All calls route through the **DevNest proxy** — model selection is handled server-side.

---

## Data Storage

### Primary: SQLite (`tasks.db`)

- Created automatically on first run in the project directory
- **0ms latency** — all reads/writes are instant, no network needed
- Fully functional offline — the app never requires internet to operate
- **Soft delete** — tasks are never hard-deleted. An `is_deleted` flag moves them to the recycle bin. Run `taskflow restore <ID>` to bring them back

### Cloud Backup: Supabase (Background Thread)

- Every write operation spawns a non-blocking background thread
- The thread syncs the change to Supabase via the Render proxy
- Sync failures are silent — they never interrupt your terminal workflow

### Schema (SQLite — current)

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | Primary key (8-char UUID) |
| `name` | TEXT | Task title |
| `priority` | TEXT | High / Medium / Low |
| `status` | TEXT | pending / completed |
| `category` | TEXT | Work, Study, Personal, Health, Finance, General |
| `due_date` | TEXT | ISO date string (YYYY-MM-DD) |
| `due_time` | TEXT | 24-hour time (HH:MM), optional |
| `notes` | TEXT | Optional long-form notes |
| `is_deleted` | INTEGER | 0 = active, 1 = recycle bin |
| `created_at` | TEXT | Timestamp of creation |
| `completed_at` | TEXT | Timestamp of completion (nullable) |
| `reminder_at` | TEXT | Reminder datetime (YYYY-MM-DD HH:MM), nullable |
| `reminder_sent` | INTEGER | 0 = pending, 1 = already fired |
| `recurrence` | TEXT | none / daily / weekly / weekdays / monthly |
| `recurrence_end_date` | TEXT | ISO date when recurrence stops, nullable |

> **Migrations run safely on every startup.** New columns are added via `ALTER TABLE ... ADD COLUMN` statements that silently skip if the column already exists — so existing databases are upgraded automatically.

### Timezone Handling (`timezone_utils.py`)

All date/time comparisons (overdue detection, reminder firing, past-date validation) use **the user's local timezone**, not the server's. `timezone_utils.py` resolves the correct timezone via:

1. In-memory cache (process lifetime)
2. `~/.taskflow_tz` file cache (7-day TTL)
3. `ipinfo.io` IP-based detection
4. System local timezone
5. UTC hard fallback

This means TaskFlow works correctly for users in any timezone without any manual configuration.

---

## Features Checklist

### Core (Assignment Requirements)

- [x] Add / Edit / Delete / Complete tasks
- [x] High / Medium / Low priority levels
- [x] Due date assignment with overdue detection
- [x] SQLite persistent storage
- [x] Menu-driven terminal interface
- [x] Clean output formatting with Rich
- [x] Error handling and input validation throughout

### Bonus (Extra Credit)

- [x] Cyberpunk-themed colorful CLI (Rich panels, tables, live spinners)
- [x] Search tasks by keyword (name, notes, category)
- [x] Filter tasks by status, priority, or category
- [x] Category-based task organization
- [x] Due time support (`HH:MM`) on top of due date
- [x] **Reminder system** — set `YYYY-MM-DD HH:MM` reminders; daemon fires  bell in terminal
- [x] **Recurrence engine** — daily / weekly / weekdays / monthly with optional end date
- [x] **Soft delete + Recycle bin** — `taskflow bin`, `taskflow restore <ID>`
- [x] **Weather widget** — dashboard + `taskflow weather` command; IP-auto-detects city
- [x] **Timezone-aware** — `timezone_utils.py` detects user's local timezone via IP
- [x] **Multi-agent AI pipeline** — Enhancer → Decomposer → Classifier → Chat → Validator
- [x] **Prompt Enhancer (Step 0)** — resolves pronouns and shortcuts before classification
- [x] **Multi-agent Decomposer** — splits compound prompts into ordered sub-tasks
- [x] **Multilingual Intent Classifier** — language-agnostic rulebook (EN/HI/Hinglish/etc.)
- [x] **AI Response Validator** — fast rules + AI judge with auto-retry (up to 2x)
- [x] **Thinking-leak scrubber** — strips raw SSE reasoning fragments from replies
- [x] **Animated thinking display** — intent-aware cycling messages + elapsed timer
- [x] AI natural language task parsing (`taskflow add --ai`)
- [x] AI full-day schedule optimizer (`taskflow optimize`)
- [x] AI daily motivation / productivity roast on dashboard
- [x] AI Chat mode with slash commands (`/add`, `/list`, `/done`, `/stats`, etc.)
- [x] Chat draft memory — AI remembers partial task across topic switches
- [x] Task confirmation preview before saving (via chat)
- [x] Past-date validation with user confirmation flow
- [x] Reminder validation (blocks past times; warns if reminder is after due time)
- [x] Background Supabase cloud sync (non-blocking, zero client secrets)
- [x] ASCII productivity analytics with bar charts
- [x] Streak tracking with badge
- [x] Pomodoro focus timer with live Rich countdown display
- [x] Markdown report export
- [x] One-command setup scripts — `run.sh` (Linux/macOS) + `run.bat` (Windows)
- [x] Evaluation time-bomb — app auto-locks after **20 May 2026**

---

## Dependencies

```
rich>=13.7.0       — Terminal UI (tables, panels, live spinner, Pomodoro timer)
click>=8.1.7       — CLI framework (commands, options, arguments)
requests>=2.31.0   — HTTP client for AI proxy calls + Supabase REST sync + IP detection
python-dotenv>=1.0.0 — Env var support (optional DB_PATH override)
tzdata>=2024.1     — IANA timezone database (required on Windows; auto-installed by run.bat)
```

**Standard library only** (no extra install needed) for:
`sqlite3`, `threading`, `uuid`, `datetime`, `json`, `os`, `time`, `zoneinfo`, `re`

Install everything at once:

```bash
pip install -r requirements.txt
```

---

## Project Structure

```
taskflow-pro/
├── main.py                 ← CLI entry point (Rich UI, Click commands, animated thinking, Pomodoro)
├── controller.py           ← Business logic + AI orchestration + action dispatch
├── database.py             ← SQLite CRUD + reminder daemon queries + Supabase sync thread
├── ai_gateway.py           ← Multi-agent AI: enhancer, decomposer, classifier, chat, validator
├── timezone_utils.py       ← IP-based timezone detection + caching (powers all date/time ops)
├── requirements.txt        ← Python dependencies
├── run.sh                  ← One-command setup + launch (Linux / macOS)
├── run.bat                 ← One-command setup + launch (Windows, handles tzdata install)
├── taskflow                ← Short command wrapper (Linux / macOS)
├── taskflow.bat            ← Short command wrapper (Windows CMD)
├── supabase_setup.sql      ← Run once in Supabase SQL Editor (includes all new columns)
├── tasks.db                ← SQLite database (auto-created, git-ignored)
└── README.md
```

> **Git hygiene:** Only `tasks.db` and `__pycache__/` need to be in `.gitignore`. There is no `.env` file — the project has nothing sensitive to hide on the client side.

---

## Submission

| Item | Details |
|---|---|
| **GitHub** | Push all files except `tasks.db` — add it to `.gitignore`. No `.env` to worry about |
| **Demo Video** | Show: dashboard open, `add --ai`, `chat` (multilingual), `optimize`, `focus`, `analytics`, `weather`, and `export` |
| **Deployment** | App runs locally — the DevNest proxy is already live on Render |

### Demo Script (suggested order)

```bash
taskflow                               # 1. Dashboard + weather + AI brief
taskflow weather "Shimla"              # 2. Set city (only needed once)
taskflow add                           # 3. Manual add — show reminder + recurrence prompts
taskflow add --ai                      # 4. Natural language add
taskflow chat                          # 5. Open AI chat (multilingual demo)
  "add karo gym task kal ke liye"      #    Create task in Hinglish — shows multi-agent pipeline
  "pani pi liya"                       #    Complete by describing action — shows intent understanding
  /stats                               #    Slash command analytics
  /exit
taskflow optimize                      # 6. Generate AI schedule
taskflow focus <ID>                    # 7. Pomodoro timer
taskflow analytics                     # 8. ASCII charts
taskflow bin                           # 9. View recycle bin
taskflow restore <ID>                  # 10. Restore a task
taskflow export                        # 11. Export report
```

---

> Built for **DevNest Python Developer Internship — Week 1**
> Proxy server managed by Scam Buster India — already deployed and running.
