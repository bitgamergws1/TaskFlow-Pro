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
- **AI** for natural-language task parsing
- **AI** for schedule optimization and personalized daily motivation
- A **Render-hosted proxy server** that keeps all API keys off your machine entirely

The app is designed to require **no secrets on the client machine**. You clone it, run one script, and you're live.

---

## What's Inside

| File | Role |
|---|---|
| `main.py` | CLI entry point — all commands, Rich UI, Pomodoro timer |
| `controller.py` | Logic bridge between database and AI |
| `database.py` | SQLite engine + background Supabase sync |
| `ai_gateway.py` | Multi-model AI routing via the DevNest proxy |
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

> **Note for Windows users:** Make sure Python is added to PATH during installation (check "Add Python to PATH" on the Python installer screen).

---

Both scripts automatically:

1. **Check** Python 3.9+ is installed
2. **Create** a virtual environment (`venv/`)
3. **Install** all dependencies from `requirements.txt`
4. **Launch** the TaskFlow Pro dashboard

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
python main.py
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

This creates the `tasks` table with the correct schema, RLS policies, and indexes that the proxy server expects.

### Step 2 — Add environment variables to the Render proxy

1. Go to your Render service dashboard → **Environment** tab
2. Add these two variables:

```
SUPABASE_URL       = https://your-project-id.supabase.co
SUPABASE_ANON_KEY  = your-anon-public-key
```

3. Render will **auto-redeploy** with the new secrets — takes about 30 seconds

That's it. Every task write from the CLI (add / complete / delete / restore) will silently sync through the proxy to Supabase — no credentials on the client machine, no blocking of your terminal.

> **How sync works under the hood:** `database.py` spawns a background daemon thread on every write. That thread sends the task payload to the DevNest proxy over HTTPS. The proxy verifies the HMAC signature, injects the Supabase credentials server-side, and writes to your cloud table. If the proxy is unreachable (offline), the write is silently dropped — your local SQLite data is always the source of truth.

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
taskflow                              → Dashboard + AI daily brief
taskflow add                          → Add a task interactively
taskflow add --ai                     → Natural language task parsing
taskflow list                         → List all active tasks
taskflow list --status pending        → Filter: pending | completed
taskflow list --category Work         → Filter by category
taskflow list --priority High         → Filter: High | Medium | Low
taskflow complete <ID>                → Mark task as done ✓
taskflow delete <ID>                  → Soft-delete → recycle bin
taskflow restore <ID>                 → Restore from recycle bin
taskflow bin                          → View recycle bin
taskflow edit <ID>                    → Edit any field interactively
taskflow search "keyword"             → Search name, notes, category
taskflow weather                      → Show current weather (auto-detects city from IP)
taskflow weather "Shimla"             → Set your city and show weather
```

### AI Chat (`taskflow chat`)

Start a natural-language session where you can manage tasks by just talking. Supports English, Hindi, and Hinglish — AI matches your language automatically.

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
5. All fields ready → AI shows a **preview card**, asks you to confirm before saving
6. You confirm → task saved, draft cleared

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

### Natural Language Task Parsing

Instead of filling in every field manually, just describe your task in plain English — or even Hinglish:

```bash
python main.py add --ai
```

**Example input:**
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

The AI extracts task name, priority, due date, and category from any natural language description. You confirm before saving.

---

### AI Schedule Optimizer

```bash
python main.py optimize
```

Sends all your pending tasks to the AI, which returns a complete, time-blocked daily schedule including:

- **Priority ordering** — urgent/important tasks scheduled first
- **Pomodoro blocks** — each task slotted into focused 25-min work blocks
- **Break reminders** — short breaks after every 2 Pomodoros, long break after 4
- **Estimated completion times** — so you know exactly when you'll be done

The schedule is rendered as a Rich table directly in your terminal.

---

### Daily Motivation / Roast

Every time you open the dashboard (`python main.py`), the **AI** generates a personalized message based on your recent productivity data:

- **Low productivity** → you get roasted 🔥
- **High productivity** → you get fired-up motivation 💪
- **Streak active** → streak acknowledgement with 🔥 badge

The message is fetched asynchronously so it doesn't delay the dashboard load.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│            main.py (CLI + Rich UI)           │
│  Commands: add, list, complete, focus, ...   │
└─────────────────────┬────────────────────────┘
                      │
             ┌────────▼────────┐
             │  controller.py  │   ← Business logic, validation, AI fallbacks
             └────┬────────┬───┘
                  │        │
     ┌────────────▼──┐  ┌──▼──────────────────┐
     │  database.py  │  │    ai_gateway.py     │
     │               │  │                      │
     │  SQLite ───── │  │  AI  (parsing)       │
     │  (primary,    │  │  AI  (optimize       │
     │   0ms, local) │  │       + motivation)  │
     │               │  └──────────┬───────────┘
     │  Supabase ◄── │             │
     │  (background  │     DevNest Proxy Server
     │   sync thread)│     (Render — already deployed)
     └───────────────┘     HMAC-verified, key-secure
```

**Proxy URL:** `https://devnest-proxy-server.onrender.com`

All AI calls route through the DevNest proxy, which:
- Holds all API keys server-side — zero secrets on client
- Verifies request integrity via HMAC signatures on every call
- Routes to the correct model based on the request type
- Returns responses in a unified format regardless of backend

**Proxy routes used by this app:**

| Route | Used for |
|---|---|
| `POST /v1/proxy/ai` | All AI calls — auto-routes to the appropriate model |
| `POST /v1/proxy/sync` | Task upsert to Supabase after every local write |
| `GET  /health` | Liveness check + eval-window status |

---

## Data Storage

### Primary: SQLite (`tasks.db`)

- Created automatically on first run in the project directory
- **0ms latency** — all reads/writes are instant, no network needed
- Fully functional offline — the app never requires internet to operate
- **Soft delete** — tasks are never hard-deleted. An `is_deleted` flag moves them to the recycle bin. Run `python main.py restore <ID>` to bring them back

### Cloud Backup: Supabase (Background Thread)

- Every write operation spawns a non-blocking background thread
- The thread syncs the change to Supabase via the Render proxy
- Sync failures are silent — they never interrupt your terminal workflow
- Enables **multi-device access**: the same tasks appear anywhere you configure the proxy

### Schema (SQLite)

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | Task title |
| `priority` | TEXT | High / Medium / Low |
| `status` | TEXT | pending / in-progress / done |
| `category` | TEXT | Work, Study, Personal, etc. |
| `due_date` | TEXT | ISO 8601 date string |
| `notes` | TEXT | Optional long-form notes |
| `is_deleted` | INTEGER | 0 = active, 1 = recycle bin |
| `created_at` | TEXT | Timestamp of creation |
| `completed_at` | TEXT | Timestamp of completion (nullable) |

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

- [x] Cyberpunk-themed colorful CLI (Rich panels, tables, gradients)
- [x] Search tasks by keyword (name, notes, category)
- [x] Filter tasks by status, priority, or category
- [x] Category-based task organization
- [x] AI natural language task parsing
- [x] AI full-day schedule optimizer
- [x] AI daily motivation / productivity roast on dashboard open
- [x] AI Chat mode with slash commands (`/add`, `/list`, `/done`, `/stats`, etc.)
- [x] Chat draft memory — AI remembers partial task across topic switches
- [x] Multi-language chat — AI matches English / Hindi / Hinglish automatically
- [x] Task confirmation preview before saving (via chat)
- [x] Weather widget on dashboard (auto-detects city from IP via ipinfo.io)
- [x] Background Supabase cloud sync (non-blocking, zero client secrets)
- [x] Soft delete with fully functional recycle bin + restore
- [x] ASCII productivity analytics charts
- [x] Streak tracking with 🔥 badge
- [x] Pomodoro focus timer with live Rich countdown display
- [x] Markdown report export
- [x] One-command setup scripts — `run.sh` (Linux/macOS) + `run.bat` (Windows)
- [x] Evaluation time-bomb — app auto-locks after **20 May 2026**

---

## Dependencies

```
rich          — Terminal UI (tables, panels, live Pomodoro timer, color themes)
click         — CLI framework (commands, options, arguments)
requests      — HTTP client for AI proxy calls + Supabase REST sync
```

**Standard library only** (no extra install needed) for:
`sqlite3`, `threading`, `uuid`, `datetime`, `json`, `os`, `time`, `hashlib`, `hmac`

Install everything at once:

```bash
pip install -r requirements.txt
```

---

## Project Structure

```
taskflow-pro/
├── main.py                 ← CLI entry point (Rich UI, Click commands, Pomodoro)
├── controller.py           ← Business logic + AI orchestration
├── database.py             ← SQLite CRUD + background Supabase sync thread
├── ai_gateway.py           ← Multi-model AI routing via the DevNest proxy
├── requirements.txt        ← Python dependencies
├── run.sh                  ← One-command setup + launch (Linux / macOS)
├── run.bat                 ← One-command setup + launch (Windows)
├── taskflow                ← Short command wrapper (Linux / macOS)
├── taskflow.bat            ← Short command wrapper (Windows CMD)
├── supabase_setup.sql      ← Run once in Supabase SQL Editor
├── tasks.db                ← SQLite database (auto-created, git-ignored)
└── README.md
```

> **Git hygiene:** Only `tasks.db` needs to be in `.gitignore`. There is no `.env` file — the project has nothing sensitive to hide on the client side.

---

## Submission

| Item | Details |
|---|---|
| **GitHub** | Push all files except `tasks.db` — add it to `.gitignore`. No `.env` to worry about |
| **Demo Video** | Show: dashboard open, `add --ai`, `optimize`, `focus`, `analytics`, and `export` commands |
| **Deployment** | App runs locally — the DevNest proxy is already live on Render |

### Demo Script (suggested order)

```cmd
taskflow                               # 1. Dashboard + weather + AI brief
taskflow weather "Shimla"              # 2. Set city (only needed once)
taskflow chat                          # 3. Open AI chat
/add                                   #    Start task creation
/stats                                 #    Check analytics
/exit                                  #    Leave chat
taskflow add --ai                      # 4. Quick NL task add
taskflow optimize                      # 5. Generate AI schedule
taskflow focus <ID>                    # 6. Pomodoro timer
taskflow analytics                     # 7. ASCII charts
taskflow export                        # 8. Export report
```

---

> Built for **DevNest Python Developer Internship — Week 1**
> Proxy server managed by DevNest — already deployed and running.
