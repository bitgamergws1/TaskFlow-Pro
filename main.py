"""
main.py -- TaskFlow Pro CLI
Cyberpunk terminal task manager | DevNest Week 1
"""

import sys
import time
import json
import os
import threading
from datetime import date, datetime

import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.columns import Columns
from rich import box

from timezone_utils import get_tz, now_local, today_local, tz_label

# Constants

EXPIRY = date(2026, 5, 20)
console = Console()

PRIORITY_STYLE = {"High": "red",    "Medium": "yellow", "Low": "green"}
STATUS_ICON    = {"pending": "·",   "completed": "✓"}
VALID_PRIORITIES  = ["High", "Medium", "Low"]
VALID_CATEGORIES  = ["Work", "Study", "Personal", "Health", "Finance", "General"]

CITY_FILE = os.path.join(os.path.expanduser("~"), ".taskflow_city")

# Intent display labels for the chat UI
INTENT_ICONS = {
    "create_task":   ("✚", "cyan",    "Creating task"),
    "list_tasks":    ("≡", "white",   "Listing tasks"),
    "search_tasks":  ("⌕", "white",   "Searching tasks"),
    "complete_task": ("✓", "green",   "Completing task"),
    "delete_task":   ("✗", "red",     "Deleting task"),
    "edit_task":     ("✎", "yellow",  "Editing task"),
    "analytics":     ("◈", "cyan",    "Showing analytics"),
    "optimize":      ("*", "yellow", "Optimizing schedule"),
    "chitchat":      ("◦", "dim",     ""),
    "unclear":       ("◦", "dim",     ""),
}

# Live "AI thinking" message pools per intent
_THINKING_MSGS = {
    "create_task": [
        "Parsing your task details...",
        "Extracting name and priority...",
        "Checking for a due date...",
        "Picking the right category...",
        "Filling in any missing fields...",
        "Cross-referencing with your draft...",
        "Validating task structure...",
        "Almost ready to preview...",
        "Putting finishing touches...",
        "One second more...",
    ],
    "complete_task": [
        "Finding that task...",
        "Matching task to your list...",
        "Confirming it's still pending...",
        "Marking as done...",
        "Updating completion timestamp...",
        "Recalculating your streak...",
        "Saving to database...",
        "Syncing progress...",
        "Updating your stats...",
        "Almost done...",
    ],
    "delete_task": [
        "Locating the task...",
        "Verifying task exists...",
        "Moving to recycle bin...",
        "Cleaning up your list...",
        "Updating your task count...",
        "Saving changes...",
        "Almost there...",
        "Wrapping up...",
        "Syncing deletion...",
        "Done in a sec...",
    ],
    "edit_task": [
        "Reading current task details...",
        "Parsing your changes...",
        "Validating field updates...",
        "Applying priority changes...",
        "Updating due date...",
        "Saving updates...",
        "Confirming edit...",
        "Syncing to database...",
        "Almost there...",
        "Finishing up...",
    ],
    "list_tasks": [
        "Fetching your tasks...",
        "Sorting by priority...",
        "Applying filters...",
        "Checking due dates...",
        "Flagging overdue items...",
        "Ordering by urgency...",
        "Loading your list...",
        "Almost ready...",
        "Rendering table...",
        "Here it comes...",
    ],
    "search_tasks": [
        "Scanning your tasks...",
        "Running keyword match...",
        "Checking names and notes...",
        "Fuzzy-matching your query...",
        "Filtering results...",
        "Ranking by relevance...",
        "Almost there...",
        "Compiling matches...",
        "Sorting results...",
        "Done in a sec...",
    ],
    "analytics": [
        "Crunching your numbers...",
        "Counting completed tasks...",
        "Calculating productivity rate...",
        "Computing your streak...",
        "Grouping by category...",
        "Analyzing priority distribution...",
        "Building your stats...",
        "Checking overdue count...",
        "Generating charts...",
        "Almost ready...",
    ],
    "optimize": [
        "Analyzing pending tasks...",
        "Ranking by priority and deadline...",
        "Grouping by category...",
        "Calculating Pomodoro blocks...",
        "Inserting break intervals...",
        "Balancing your energy curve...",
        "Building time blocks...",
        "Optimizing the schedule...",
        "Finalizing your day plan...",
        "Almost done...",
    ],
    "weather": [
        "Detecting your location...",
        "Connecting to weather API...",
        "Fetching current conditions...",
        "Reading temperature data...",
        "Checking humidity levels...",
        "Looking up forecast...",
        "Almost ready...",
        "Packaging weather info...",
        "One more second...",
        "Here it comes...",
    ],
    "general_question": [
        "Thinking about that...",
        "Pulling from knowledge base...",
        "Formulating an answer...",
        "Checking facts...",
        "Searching my knowledge...",
        "Putting together a response...",
        "Almost there...",
        "Refining the answer...",
        "One moment more...",
        "Finishing up...",
    ],
    "chitchat": [
        "Thinking...",
        "One moment...",
        "On it...",
        "Processing...",
        "Almost there...",
        "Cooking up a reply...",
        "Hang tight...",
        "Nearly done...",
        "Just a sec...",
        "Coming right up...",
    ],
    "unclear": [
        "Understanding your request...",
        "Working on it...",
        "Parsing the context...",
        "Matching to a known intent...",
        "Cross-checking history...",
        "Almost have it...",
        "Interpreting your message...",
        "Figuring out what you need...",
        "Nearly there...",
        "One more second...",
    ],
}
_THINKING_GENERIC = [
    "AI is thinking...", "Processing your request...", "Hold on a moment...",
    "Working with your tasks...", "Crafting a response...", "Reading context...",
    "Checking task state...", "Running inference...", "Almost ready...", "One more second...",
]


def _live_thinking_call(fn, intent_name: str = "unclear"):
    """
    Runs `fn()` in a background thread while showing animated cycling
    intent-aware messages in the foreground using Rich Live.
    Shows elapsed time so users know the AI is actively working.
    Returns whatever fn() returns.
    """
    msgs   = _THINKING_MSGS.get(intent_name, _THINKING_GENERIC)
    result = [None]
    exc    = [None]

    def _worker():
        try:
            result[0] = fn()
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    idx      = 0
    spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spin_i   = 0
    start_ts = time.time()

    with Live(console=console, refresh_per_second=8, transient=True) as live:
        while t.is_alive():
            elapsed = int(time.time() - start_ts)
            msg     = msgs[idx % len(msgs)]
            spin    = spinners[spin_i % len(spinners)]
            # Show elapsed after 3s so it's not distracting on fast replies
            timer_str = f"  [dim]{elapsed}s[/dim]" if elapsed >= 3 else ""
            live.update(Panel(
                f"  [dim]{spin}[/dim]  [white]{msg}[/white]{timer_str}",
                title="[dim]AI[/dim]", border_style="dim", padding=(0, 1)
            ))
            time.sleep(0.125)          # 8 fps — smooth spinner
            spin_i += 1
            if spin_i % 12 == 0:       # advance message every ~1.5s (was 3s)
                idx += 1

    t.join()
    if exc[0]:
        raise exc[0]
    return result[0]


BANNER = """
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║  ████████╗ █████╗ ███████╗██╗  ██╗    ███████╗██╗      ██████╗ ██╗    ██╗ ║
  ║     ██╔══╝██╔══██╗██╔════╝██║ ██╔╝    ██╔════╝██║     ██╔═══██╗██║    ██║ ║
  ║     ██║   ███████║███████╗█████╔╝     █████╗  ██║     ██║   ██║██║ █╗ ██║ ║
  ║     ██║   ██╔══██║╚════██║██╔═██╗     ██╔══╝  ██║     ██║   ██║██║███╗██║ ║
  ║     ██║   ██║  ██║███████║██║  ██╗    ██║     ███████╗╚██████╔╝╚███╔███╔╝ ║
  ║     ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝ ║
  ║                        P R O  --  Cyber-Sync Edition                      ║
  ╚══════════════════════════════════════════════════════════════════════════╝"""

SLASH_HELP = """
  [bold white]Slash Commands[/bold white]
  [dim]──────────────────────────────────────────────[/dim]
  [cyan]/add[/cyan]              Start guided task creation
  [cyan]/list[/cyan]             Show all tasks
  [cyan]/list pending[/cyan]     Filter by status
  [cyan]/list Work[/cyan]        Filter by category
  [cyan]/done <ID>[/cyan]        Mark task completed
  [cyan]/del <ID>[/cyan]         Delete task
  [cyan]/search <query>[/cyan]   Search tasks
  [cyan]/optimize[/cyan]         Generate AI schedule
  [cyan]/stats[/cyan]            Show analytics
  [cyan]/report[/cyan]           Export Markdown report
  [cyan]/draft[/cyan]            Show current task draft
  [cyan]/clear[/cyan]            Clear current draft
  [cyan]/help[/cyan]             Show this help
  [cyan]/exit[/cyan]             Leave chat
  [dim]──────────────────────────────────────────────[/dim]
  [dim]Or just talk naturally — AI handles the rest.[/dim]
"""


# Guards

def _check_expiry():
    if date.today() > EXPIRY:
        console.print(Panel(
            "[bold red]EVALUATION PERIOD ENDED[/bold red]\n"
            "[dim]This build expired on 20 May 2026. Contact DevNest.[/dim]",
            border_style="red",
        ))
        sys.exit(1)


def _get_ctrl():
    from controller import TaskController
    return TaskController()


# Weather

def _load_city():
    try:
        with open(CITY_FILE) as f:
            return f.read().strip()
    except Exception:
        return None


def _save_city(city: str):
    try:
        with open(CITY_FILE, "w") as f:
            f.write(city.strip())
    except Exception:
        return  # City cache write failure is non-critical


def _detect_city_from_ip():
    try:
        data = requests.get("https://ipinfo.io/json", timeout=3).json()
        return data.get("city")
    except Exception:
        return None


def _fetch_weather(city: str) -> dict | None:
    try:
        resp = requests.get(f"https://wttr.in/{city}?format=j1", timeout=4)
        if resp.status_code != 200:
            return None
        data    = resp.json()
        cur     = data["current_condition"][0]
        desc    = cur["weatherDesc"][0]["value"]
        temp_c  = cur["temp_C"]
        feels   = cur["FeelsLikeC"]
        humid   = cur["humidity"]
        return {"city": city, "temp": temp_c, "feels": feels, "desc": desc, "humidity": humid}
    except Exception:
        return None


def _get_weather_async():
    city = _load_city()
    if not city:
        city = _detect_city_from_ip()
        if city:
            _save_city(city)
    if not city:
        return None
    return _fetch_weather(city)


# Render Helpers

def _print_banner():
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(f"  [dim]{today_local().strftime('%A, %d %B %Y')}  |  {tz_label()}  |  DevNest Week 1[/dim]\n")


def _task_table(tasks, title="Tasks"):
    if not tasks:
        return None
    table = Table(
        title=title,
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        header_style="bold white",
        show_lines=False,
        title_style="bold white",
    )
    table.add_column("ID",       style="dim",    width=10)
    table.add_column("Task",     style="white",  min_width=22)
    table.add_column("Category", style="dim",    width=10)
    table.add_column("Priority", justify="center", width=9)
    table.add_column("Due / Time", justify="center", width=16)
    table.add_column("Remind",   justify="center", width=6)
    table.add_column("Status",   justify="center", width=12)

    today = today_local()
    for t in tasks:
        p_style = PRIORITY_STYLE.get(t["priority"], "white")
        s_icon  = STATUS_ICON.get(t["status"], "?")
        due_str = t.get("due_date") or "[dim]--[/dim]"
        overdue = False

        if t["status"] == "pending" and t.get("due_date"):
            try:
                if date.fromisoformat(t["due_date"]) < today:
                    due_str = f"[red]{t['due_date']}![/red]"
                    overdue = True
            except ValueError:
                due_str = t.get("due_date", "--")  # malformed date — display as-is

        name_str = f"[dim]{t['name']}[/dim]" if t["status"] == "completed" else (
            f"[red]{t['name']}[/red]" if overdue else t["name"]
        )

        due_display = due_str if overdue else (t.get("due_date") or "[dim]--[/dim]")
        if t.get("due_time") and not overdue:
            due_display = f"{t.get('due_date','')} [dim]{t['due_time']}[/dim]"
        recur_icon = {"daily":"↺d","weekly":"↺w","weekdays":"↺wd","monthly":"↺m"}.get(t.get("recurrence","none"), "")
        name_display = f"{name_str} [dim]{recur_icon}[/dim]" if recur_icon else name_str
        remind_str = "[cyan]R[/cyan]" if (t.get("reminder_at") and not t.get("reminder_sent")) else "[dim]--[/dim]"
        table.add_row(
            t["id"],
            name_display,
            t.get("category", "General"),
            f"[{p_style}]{t['priority']}[/{p_style}]",
            due_display,
            remind_str,
            f"[dim]{s_icon} {t['status'].capitalize()}[/dim]",
        )
    return table


def _bar_chart(data: dict, title: str, width: int = 28):
    if not data:
        return
    max_v = max(data.values(), default=1) or 1
    console.print(f"\n  [bold white]{title}[/bold white]")
    for label, val in sorted(data.items(), key=lambda x: -x[1]):
        fill    = int((val / max_v) * width)
        bar     = "█" * fill + "░" * (width - fill)
        console.print(f"  [dim]{label:<14}[/dim] [cyan]{bar}[/cyan] [white]{val}[/white]")


def _render_task_card(t: dict, title="Task"):
    p_style = PRIORITY_STYLE.get(t.get("priority", "Medium"), "white")
    due_line = t.get('due_date') or '--'
    if t.get('due_time'):
        due_line += f"  {t['due_time']}"
    recur = t.get('recurrence', 'none')
    recur_line = recur if recur and recur != 'none' else '--'
    remind_line = t.get('reminder_at') or '--'
    if t.get('reminder_sent'):
        remind_line += '  [dim](sent)[/dim]'
    console.print(Panel(
        f"  [dim]ID[/dim]        [white]{t.get('id', '— not saved yet —')}[/white]\n"
        f"  [dim]Name[/dim]      [bold white]{t['name']}[/bold white]\n"
        f"  [dim]Priority[/dim]  [{p_style}]{t.get('priority','Medium')}[/{p_style}]\n"
        f"  [dim]Category[/dim]  [white]{t.get('category','General')}[/white]\n"
        f"  [dim]Due[/dim]       [white]{due_line}[/white]\n"
        f"  [dim]Recurrence[/dim][white]{recur_line}[/white]\n"
        f"  [dim]Reminder[/dim]  [cyan]{remind_line}[/cyan]\n"
        f"  [dim]Notes[/dim]     [dim]{t.get('notes') or '--'}[/dim]",
        title=f"[bold white]{title}[/bold white]",
        border_style="dim",
        padding=(0, 2),
    ))


# Dashboard

def _show_dashboard():
    ctrl = _get_ctrl()
    _print_banner()

    import threading as _t
    from ai_gateway import AIGateway as _AIGateway
    _t.Thread(target=_AIGateway.wake_up, daemon=True).start()

    weather_result = [None]
    def _weather_thread():
        weather_result[0] = _get_weather_async()
    wt = threading.Thread(target=_weather_thread, daemon=True)
    wt.start()

    stats = ctrl.get_analytics()
    tasks = ctrl.list_tasks()

    pc     = "green" if stats["productivity"] >= 70 else "yellow" if stats["productivity"] >= 40 else "red"
    streak = f"  {stats['streak']}d" if stats["streak"] >= 3 else f"  {stats['streak']}d"
    stat_panels = [
        Panel(f"[bold white]{stats['total']}[/bold white]\n[dim]Total[/dim]",                     border_style="dim", expand=True),
        Panel(f"[bold green]{stats['completed']}[/bold green]\n[dim]Done[/dim]",                  border_style="dim", expand=True),
        Panel(f"[bold yellow]{stats['pending']}[/bold yellow]\n[dim]Pending[/dim]",               border_style="dim", expand=True),
        Panel(f"[bold red]{stats['overdue']}[/bold red]\n[dim]Overdue[/dim]",                     border_style="dim", expand=True),
        Panel(f"[bold {pc}]{stats['productivity']}%[/bold {pc}]\n[dim]Done rate[/dim]",           border_style="dim", expand=True),
        Panel(f"[bold white]{streak}[/bold white]\n[dim]Streak[/dim]",                            border_style="dim", expand=True),
    ]
    console.print(Columns(stat_panels))

    wt.join(timeout=3)
    wx = weather_result[0]
    if wx:
        console.print(Panel(
            f"  [bold white]{wx['city']}[/bold white]  "
            f"[cyan]{wx['temp']}°C[/cyan]  "
            f"[dim]feels {wx['feels']}°C  |  {wx['desc']}  |  humidity {wx['humidity']}%[/dim]",
            border_style="dim",
            title="[dim]Weather[/dim]",
            padding=(0, 1),
        ))

    console.print()

    if tasks:
        tbl = _task_table(tasks[:12], f"Tasks  ({len(tasks)} total)")
        console.print(tbl)
        if len(tasks) > 12:
            console.print(f"  [dim]... {len(tasks) - 12} more. Use [white]taskflow list[/white] to see all.[/dim]")
    else:
        console.print(Panel(
            "[dim]No tasks yet.  Run [white]taskflow add[/white] to get started.[/dim]",
            border_style="dim",
        ))

    console.print()
    TIPS = [
        "Break big tasks into 25-min Pomodoro blocks — use [white]taskflow focus <ID>[/white]",
        "High priority tasks first, always. Your brain is freshest in the morning.",
        "Name tasks as actions: 'Write report' beats 'Report' every time.",
        "A 3-day streak beats a perfect week you never started.",
        "If it takes < 2 minutes, do it now — don't add it to the list.",
        "Set due dates even for flexible tasks — deadlines create focus.",
        "Group similar tasks by category — context-switching kills momentum.",
        "Complete your hardest task before lunch. Everything else feels easy after.",
        "Pending tasks drain mental energy even when you're not working on them.",
        "Check [white]taskflow analytics[/white] weekly — what gets measured gets done.",
    ]

    import itertools
    mot_result = [None, None]

    def _mot_thread():
        mot_result[0], mot_result[1] = ctrl.get_motivation()

    mt = threading.Thread(target=_mot_thread, daemon=True)
    mt.start()

    tip_cycle = itertools.cycle(TIPS)
    with Live(console=console, refresh_per_second=0.5) as live:
        while mt.is_alive():
            live.update(Panel(
                f"[dim]{next(tip_cycle)}[/dim]",
                title="[dim]TaskFlow AI  ·  loading...[/dim]",
                border_style="dim",
                padding=(0, 2),
            ))
            time.sleep(2.2)

    mt.join()
    msg, mot_err = mot_result

    if msg:
        console.print(Panel(
            f"[italic white]{msg}[/italic white]",
            title="[dim]TaskFlow AI[/dim]",
            border_style="dim",
            padding=(0, 2),
        ))
    elif mot_err:
        console.print(Panel(
            f"[dim]Could not load daily brief — {mot_err}[/dim]",
            title="[dim]TaskFlow AI[/dim]",
            border_style="dim",
            padding=(0, 2),
        ))

    console.print()
    console.print(
        "  [dim]Commands:[/dim]  "
        "[white]add[/white]  [dim]|[/dim]  [white]list[/white]  [dim]|[/dim]  "
        "[white]chat[/white]  [dim]|[/dim]  [white]complete[/white]  [dim]|[/dim]  "
        "[white]optimize[/white]  [dim]|[/dim]  [white]focus[/white]  [dim]|[/dim]  "
        "[white]analytics[/white]  [dim]|[/dim]  [white]export[/white]"
    )


# CLI Group

@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def cli(ctx):
    """TaskFlow Pro -- Smart Productivity CLI by DevNest"""
    _check_expiry()
    if ctx.invoked_subcommand is None:
        _show_dashboard()


# add

@cli.command()
@click.option("--ai", "use_ai", is_flag=True, help="Parse task from natural language")
def add(use_ai):
    """Add a new task."""
    ctrl = _get_ctrl()

    if use_ai:
        text = Prompt.ask("[cyan]Describe your task[/cyan]")
        with console.status("[dim]AI is parsing...[/dim]", spinner="dots"):
            task_id, parsed, err = ctrl.add_ai(text)
        if err:
            console.print(f"[red]AI error:[/red] {err}")
            if not Confirm.ask("Add manually instead?"):
                return
            use_ai = False
        else:
            _render_task_card({**parsed, "id": task_id}, title="Task Added")
            return

    if not use_ai:
        name = Prompt.ask("[white]Task name[/white]")

        # Case-insensitive category prompt
        _cat_map = {c.lower(): c for c in VALID_CATEGORIES}
        while True:
            _cat_raw = Prompt.ask(
                f"[white]Category[/white] [dim][{'/'.join(VALID_CATEGORIES)}][/dim]",
                default="General",
            ).strip()
            category = _cat_map.get(_cat_raw.lower())
            if category:
                break
            console.print(f"  [red]Invalid.[/red] Choose: {', '.join(VALID_CATEGORIES)}")

        # Case-insensitive priority prompt
        _pri_map = {p.lower(): p for p in VALID_PRIORITIES}
        while True:
            _pri_raw = Prompt.ask(
                f"[white]Priority[/white] [dim][{'/'.join(VALID_PRIORITIES)}][/dim]",
                default="Medium",
            ).strip()
            priority = _pri_map.get(_pri_raw.lower())
            if priority:
                break
            console.print(f"  [red]Invalid.[/red] Choose: {', '.join(VALID_PRIORITIES)}")
        due_date = Prompt.ask("[white]Due date (YYYY-MM-DD)[/white]", default="")
        due_time = Prompt.ask("[white]Due time (HH:MM, optional)[/white]", default="")
        notes    = Prompt.ask("[white]Notes[/white]", default="")

        # Validate date/time FIRST (before reminder prompt)
        due_date = due_date.strip() or None
        due_time = due_time.strip() or None
        notes    = notes.strip() or None

        if due_date:
            try:
                parsed_due = date.fromisoformat(due_date)
                if parsed_due < today_local():
                    console.print(f"  [yellow]⚠ '{due_date}' is in the past.[/yellow]")
                    if not Confirm.ask("  Save anyway?", default=False):
                        console.print("  [dim]Task not saved. Fix the date and try again.[/dim]")
                        return
            except ValueError:
                console.print("[red]Invalid date. Use YYYY-MM-DD.[/red]")
                return

        if due_time:
            try:
                datetime.strptime(due_time, "%H:%M")
            except ValueError:
                console.print("[red]Invalid time. Use HH:MM (e.g. 08:30).[/red]")
                return

        # Reminder (only offered when due datetime is in the future)
        reminder_at = None
        _now = now_local()

        # Build a full due datetime for comparison
        _due_dt = None
        if due_date:
            try:
                _d = date.fromisoformat(due_date)
                _t = datetime.strptime(due_time, "%H:%M").time() if due_time else None
                _due_dt = datetime.combine(_d, _t, tzinfo=get_tz()) if _t else datetime(_d.year, _d.month, _d.day, 23, 59, tzinfo=get_tz())
            except (ValueError, TypeError):
                _due_dt = None  # malformed date/time — skip reminder suggestion

        _due_is_future = (_due_dt is not None and _due_dt > _now)
        _no_due        = (due_date is None)

        if _due_is_future or _no_due:
            if Confirm.ask("  Set a reminder?", default=False):
                # Smart suggestion: 30 min before due, or tomorrow 09:00 if no due date
                if _due_is_future:
                    from datetime import timedelta as _td
                    _suggest_dt = _due_dt - _td(minutes=30)
                    if _suggest_dt <= _now:
                        _suggest_dt = _due_dt
                    suggestion = _suggest_dt.strftime("%Y-%m-%d %H:%M")
                else:
                    from datetime import timedelta as _td
                    suggestion = (now_local().replace(hour=9, minute=0, second=0, microsecond=0) + _td(days=1)).strftime("%Y-%m-%d %H:%M")

                while True:
                    r_input = Prompt.ask(
                        "[white]Remind at (YYYY-MM-DD HH:MM)[/white]",
                        default=suggestion,
                    ).strip()
                    if not r_input:
                        console.print("  [dim]Reminder skipped.[/dim]")
                        break
                    try:
                        r_dt = datetime.strptime(r_input, "%Y-%m-%d %H:%M").replace(tzinfo=get_tz())
                        if r_dt <= _now:
                            console.print(
                                f"  [red]✗ '{r_input}' is already in the past — reminder won't fire.[/red]"
                            )
                            if not Confirm.ask("  Enter a different time?", default=True):
                                console.print("  [dim]Reminder skipped.[/dim]")
                                break
                            continue
                        if _due_is_future and r_dt > _due_dt:
                            console.print(
                                f"  [yellow]⚠ Reminder is set AFTER the due time.[/yellow]"
                            )
                            if not Confirm.ask("  Keep this reminder time?", default=False):
                                continue
                        reminder_at = r_input
                        break
                    except ValueError:
                        console.print("  [red]Invalid format. Use YYYY-MM-DD HH:MM (e.g. 2026-05-20 09:00)[/red]")
        else:
            console.print("  [dim]Reminder skipped — due date/time is already in the past.[/dim]")

        # Recurrence
        recurrence = "none"
        if Confirm.ask("  Does this task repeat?", default=False):
            recurrence = Prompt.ask(
                "[white]Recurrence[/white]",
                choices=["daily", "weekly", "weekdays", "monthly"],
                default="daily",
            )
            recurrence_end = Prompt.ask(
                "[white]Repeat until (YYYY-MM-DD, optional)[/white]", default=""
            ).strip() or None
        else:
            recurrence_end = None

        task_id, _ = ctrl.add_manual(
            name, category, priority, due_date, notes,
            due_time=due_time, reminder_at=reminder_at,
            recurrence=recurrence, recurrence_end_date=recurrence_end,
        )
        _render_task_card(
            {
                "id": task_id, "name": name, "priority": priority,
                "category": category, "due_date": due_date, "due_time": due_time,
                "notes": notes, "reminder_at": reminder_at,
                "reminder_sent": 0, "recurrence": recurrence,
                "recurrence_end_date": recurrence_end,
            },
            title="Task Added",
        )


# list

@cli.command(name="list")
@click.option("--status",   "-s", default=None, type=click.Choice(["pending", "completed"]))
@click.option("--category", "-c", default=None, type=click.Choice(VALID_CATEGORIES))
@click.option("--priority", "-p", default=None, type=click.Choice(VALID_PRIORITIES))
def list_tasks(status, category, priority):
    """List all tasks."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_tasks(status=status, category=category)
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        return
    title = "All Tasks"
    if status:   title += f"  [{status}]"
    if category: title += f"  [{category}]"
    if priority: title += f"  [{priority}]"
    console.print(_task_table(tasks, title))
    console.print(f"  [dim]{len(tasks)} task(s)[/dim]")


# complete

@cli.command()
@click.argument("task_id", required=False)
def complete(task_id):
    """Mark a task as completed.  Run without ID to pick from a list."""
    ctrl = _get_ctrl()
    if not task_id:
        tasks = ctrl.list_tasks(status="pending")
        if not tasks:
            console.print("  [dim]No pending tasks.[/dim]")
            return
        console.print(_task_table(tasks, "Pending Tasks"))
        task_id = Prompt.ask("  [white]Task ID to complete[/white]").strip()
    task_id = task_id.lstrip("-").upper()
    if not task_id:
        console.print("  [red]No task ID provided.[/red]")
        return
    task, _ = ctrl.get_task(task_id)
    if task and task.get("status") == "completed":
        console.print(f"  [yellow]⚠[/yellow] [white]{task['name']}[/white] [dim]({task_id})[/dim] is already completed.")
        return
    ok, err = ctrl.complete_task(task_id)
    if ok:
        task, _ = ctrl.get_task(task_id)
        name = task["name"] if task else task_id
        console.print(f"  [green]✓[/green] [bold white]{name}[/bold white] [dim]({task_id})[/dim] — done!")
    else:
        console.print(f"  [red]Error:[/red] {err}")
        console.print(f"  [dim]Tip: run [white]taskflow list[/white] to see valid IDs.[/dim]")


# delete

@cli.command()
@click.argument("task_id", required=False)
def delete(task_id):
    """Soft-delete a task (moves to recycle bin).  Run without ID to pick from a list."""
    ctrl = _get_ctrl()
    if not task_id:
        tasks = ctrl.list_tasks(status="pending")
        if not tasks:
            console.print("  [dim]No tasks to delete.[/dim]")
            return
        console.print(_task_table(tasks, "Tasks"))
        task_id = Prompt.ask("  [white]Task ID to delete[/white]").strip()
    task_id = task_id.lstrip("-").upper()
    if not task_id:
        console.print("  [red]No task ID provided.[/red]")
        return
    task, err = ctrl.get_task(task_id)
    if err or not task:
        console.print(f"  [red]Task not found:[/red] {task_id}")
        console.print(f"  [dim]Run [white]taskflow list[/white] to see valid IDs.[/dim]")
        return
    if not Confirm.ask(f"  Delete [white]{task['name']}[/white] [dim]({task_id})[/dim]?", default=False):
        console.print("  [dim]Cancelled.[/dim]")
        return
    ok, err = ctrl.delete_task(task_id)
    if ok:
        console.print(f"  [dim]Moved [white]{task['name']}[/white] [dim]({task_id})[/dim] to recycle bin.[/dim]")
        console.print(f"  [dim]Undo: [white]taskflow restore {task_id}[/white][/dim]")
    else:
        console.print(f"  [red]Error:[/red] {err}")


# restore

@cli.command()
@click.argument("task_id", required=False)
def restore(task_id):
    """Restore a task from the recycle bin.  Run without ID to pick from the bin."""
    ctrl = _get_ctrl()
    if not task_id:
        tasks = ctrl.list_bin()
        if not tasks:
            console.print("  [dim]Recycle bin is empty.[/dim]")
            return
        console.print(_task_table(tasks, "Recycle Bin"))
        task_id = Prompt.ask("  [white]Task ID to restore[/white]").strip()
    task_id = task_id.lstrip("-").upper()
    if not task_id:
        console.print("  [red]No task ID provided.[/red]")
        return
    ok, err = ctrl.restore_task(task_id)
    if ok:
        task, _ = ctrl.get_task(task_id)
        name = task["name"] if task else task_id
        console.print(f"  [green]✓ Restored:[/green] [bold white]{name}[/bold white] [dim]({task_id})[/dim]")
    else:
        console.print(f"  [red]Error:[/red] {err}")
        console.print(f"  [dim]Run [white]taskflow bin[/white] to see what's in the recycle bin.[/dim]")


# bin

@cli.command(name="bin")
def recycle_bin():
    """View recycle bin."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_bin()
    if not tasks:
        console.print("[dim]Recycle bin is empty.[/dim]")
        return
    console.print(_task_table(tasks, "Recycle Bin"))
    console.print("  [dim]Use [white]taskflow restore <ID>[/white] to recover.[/dim]")


# edit

@cli.command()
@click.argument("task_id")
def edit(task_id):
    """Interactively edit a task."""
    ctrl = _get_ctrl()
    task, err = ctrl.get_task(task_id.upper())
    if err:
        console.print(f"  [red]Error:[/red] {err}")
        return

    console.print(Panel(
        f"Editing [bold white]{task['name']}[/bold white]\n[dim]Leave blank to keep current value.[/dim]",
        border_style="dim",
    ))

    _cat_map = {c.lower(): c for c in VALID_CATEGORIES}
    _pri_map = {p.lower(): p for p in VALID_PRIORITIES}

    _cur_remind = task.get("reminder_at") or "--"
    if task.get("reminder_sent"):
        _cur_remind += " (already sent)"

    name      = Prompt.ask(f"  Name      [dim][{task['name']}][/dim]",    default="").strip()
    cat_raw   = Prompt.ask(f"  Category  [dim][{task['category']}][/dim]", default="").strip()
    pri_raw   = Prompt.ask(f"  Priority  [dim][{task['priority']}][/dim]", default="").strip()
    due_date  = Prompt.ask(f"  Due date  [dim][{task.get('due_date','--')}][/dim]", default="").strip()
    due_time  = Prompt.ask(f"  Due time  [dim][{task.get('due_time','--')}][/dim]", default="").strip()
    remind_in = Prompt.ask(f"  Reminder  [dim][{_cur_remind}][/dim]", default="").strip()
    notes     = Prompt.ask(f"  Notes     [dim][{task.get('notes','--')}][/dim]", default="").strip()

    updates = {}
    if name:
        updates["name"] = name

    if cat_raw:
        cat_norm = _cat_map.get(cat_raw.lower())
        if cat_norm:
            updates["category"] = cat_norm
        else:
            console.print(f"  [yellow]Invalid category '{cat_raw}' — skipped. Valid: {', '.join(VALID_CATEGORIES)}[/yellow]")

    if pri_raw:
        pri_norm = _pri_map.get(pri_raw.lower())
        if pri_norm:
            updates["priority"] = pri_norm
        else:
            console.print(f"  [yellow]Invalid priority '{pri_raw}' — skipped. Valid: {', '.join(VALID_PRIORITIES)}[/yellow]")

    # Resolve effective due date+time after any edits (needed for reminder check)
    _eff_due_date = due_date if due_date else task.get("due_date")
    _eff_due_time = due_time if due_time else task.get("due_time")

    if due_date:
        try:
            parsed_d = date.fromisoformat(due_date)
            if parsed_d < today_local():
                console.print(f"  [yellow]⚠ '{due_date}' is in the past.[/yellow]")
                if not Confirm.ask("  Save anyway?", default=False):
                    console.print("  [dim]Due date change skipped.[/dim]")
                    due_date = ""
                    _eff_due_date = task.get("due_date")
            if due_date:
                updates["due_date"] = due_date
        except ValueError:
            console.print("  [red]Invalid date format — skipped. Use YYYY-MM-DD.[/red]")

    if due_time:
        try:
            datetime.strptime(due_time, "%H:%M")
            updates["due_time"] = due_time
        except ValueError:
            console.print("  [red]Invalid time format — skipped. Use HH:MM (e.g. 14:30).[/red]")

    # Reminder validation
    if remind_in:
        _now = now_local()
        try:
            r_dt = datetime.strptime(remind_in, "%Y-%m-%d %H:%M")
            if r_dt <= _now:
                console.print(
                    f"  [red]✗ '{remind_in}' is in the past — reminder won't fire. Skipped.[/red]"
                )
            else:
                # Warn if reminder is after due datetime
                if _eff_due_date:
                    try:
                        _d = date.fromisoformat(_eff_due_date)
                        _t_obj = datetime.strptime(_eff_due_time, "%H:%M").time() if _eff_due_time else None
                        _due_dt = datetime.combine(_d, _t_obj, tzinfo=get_tz()) if _t_obj else datetime(_d.year, _d.month, _d.day, 23, 59, tzinfo=get_tz())
                        if r_dt > _due_dt:
                            console.print(f"  [yellow]⚠ Reminder is set AFTER the due time.[/yellow]")
                            if not Confirm.ask("  Keep this reminder time?", default=False):
                                remind_in = ""
                    except (ValueError, TypeError):
                        pass  # effective due datetime unparseable — skip after-due warning
                if remind_in:
                    updates["reminder_at"]   = remind_in
                    updates["reminder_sent"] = 0   # reset so it fires again
        except ValueError:
            console.print("  [red]Invalid reminder format — skipped. Use YYYY-MM-DD HH:MM[/red]")

    if notes:
        updates["notes"] = notes

    if not updates:
        console.print("  [dim]No changes made.[/dim]")
        return
    ok, err = ctrl.edit_task(task_id.upper(), **updates)
    if ok:
        task, _ = ctrl.get_task(task_id.upper())
        if task:
            _render_task_card(task, title="Updated")
    else:
        console.print(f"  [red]Error:[/red] {err}")


# search

@cli.command()
@click.argument("query", required=False)
def search(query):
    """Search tasks by name, category, or notes.  Run without query to be prompted."""
    ctrl = _get_ctrl()
    if not query:
        query = Prompt.ask("  [white]Search query[/white]").strip()
    if not query:
        console.print("  [red]No query provided.[/red]")
        return
    tasks = ctrl.list_tasks(search=query)
    if not tasks:
        console.print(f"  [dim]No tasks matching '[white]{query}[/white]'.[/dim]")
        console.print(f"  [dim]Search checks task name, category, and notes.[/dim]")
        return
    console.print(_task_table(tasks, f"Search: '{query}'"))
    console.print(f"  [dim]{len(tasks)} result(s)[/dim]")


# weather

@cli.command()
@click.argument("city", required=False)
def weather(city):
    """Show weather. Optionally set your city: taskflow weather "Shimla"."""
    if city:
        _save_city(city)
        console.print(f"  [dim]City set to [white]{city}[/white]. Dashboard will show weather from next launch.[/dim]")
    target = city or _load_city()
    if not target:
        target = _detect_city_from_ip()
        if target:
            _save_city(target)
    if not target:
        console.print("  [dim]Could not detect city. Run [white]taskflow weather \"Your City\"[/white] to set it.[/dim]")
        return
    with console.status(f"[dim]Fetching weather for {target}...[/dim]", spinner="dots"):
        wx = _fetch_weather(target)
    if not wx:
        console.print(f"  [red]Could not fetch weather for {target}.[/red]")
        return
    console.print(Panel(
        f"  [bold white]{wx['city']}[/bold white]\n\n"
        f"  [cyan]{wx['temp']}°C[/cyan]  [dim]feels like {wx['feels']}°C[/dim]\n"
        f"  [white]{wx['desc']}[/white]\n"
        f"  [dim]Humidity: {wx['humidity']}%[/dim]",
        title="[dim]Weather[/dim]",
        border_style="dim",
        padding=(0, 2),
    ))


# Reminder Daemon

def _reminder_daemon(ctrl, console_ref):
    """
    Background thread: checks every 30s for tasks whose reminder_at has passed.
    Prints a bold bell notification to the terminal and marks reminder as sent.
    Runs as daemon=True so it dies automatically when the main process exits.
    """
    import time as _time
    while True:
        try:
            due = ctrl.get_due_reminders()
            for task in due:
                due_part = ""
                if task.get("due_date"):
                    due_part = f"  [dim]{task['due_date']}"
                    if task.get("due_time"):
                        due_part += f" {task['due_time']}"
                    due_part += "[/dim]"
                console_ref.print(
                    f"\n  [bold cyan]REMINDER:[/bold cyan] "
                    f"[bold white]{task['name']}[/bold white]"
                    + due_part
                    + f"  [dim]({task['category']} · {task['priority']})[/dim]"
                )
                ctrl.mark_reminder_sent(task["id"])
        except Exception:
            # daemon must not crash the main process
            pass
        _time.sleep(30)


# chat

@cli.command()
def chat():
    """AI chat -- create, search, edit tasks through natural conversation."""
    ctrl    = _get_ctrl()
    history = []
    draft   = {}
 # Detect location once for weather queries
    _user_location = _load_city() or _detect_city_from_ip()
    # Start reminder daemon — checks every 30s for due reminders
    import threading as _rt
    _rt.Thread(target=_reminder_daemon, args=(ctrl, console), daemon=True).start()

    console.print(Panel(
        "[bold white]TaskFlow AI Chat[/bold white]\n\n"
        "[dim]Talk naturally in any language. AI remembers your task draft mid-conversation.\n"
        "Type [white]/help[/white] for slash commands or [white]/exit[/white] to leave.[/dim]",
        border_style="dim",
        padding=(0, 2),
    ))
    console.print()

    def _show_draft():
        if not draft:
            console.print("  [dim]No task draft in progress.[/dim]\n")
        else:
            fields = "\n".join(f"  [dim]{k:<10}[/dim] [white]{v}[/white]" for k, v in draft.items() if v)
            console.print(Panel(fields, title="[dim]Current Draft[/dim]", border_style="dim", padding=(0, 2)))
            console.print()

    def _handle_slash(cmd: str) -> bool:
        nonlocal draft
        parts = cmd.strip().split(None, 1)
        slash = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        if slash in ("exit", "quit", "q"):
            console.print("  [dim]Chat closed.[/dim]")
            return None

        elif slash == "help":
            console.print(SLASH_HELP)

        elif slash == "draft":
            _show_draft()

        elif slash == "clear":
            draft = {}
            console.print("  [dim]Draft cleared.[/dim]\n")

        elif slash == "list":
            status_map = {"pending": "pending", "done": "completed", "completed": "completed"}
            cat_map    = {c.lower(): c for c in VALID_CATEGORIES}
            s = c = None
            if arg:
                al = arg.lower()
                if al in status_map:  s = status_map[al]
                elif al in cat_map:   c = cat_map[al]
            tasks = ctrl.list_tasks(status=s, category=c)
            if not tasks:
                console.print("  [dim]No tasks found.[/dim]\n")
            else:
                console.print(_task_table(tasks, f"Tasks ({len(tasks)})"))
            console.print()

        elif slash in ("done", "complete"):
            if not arg:
                console.print("  [red]Usage:[/red] /done <ID>\n")
            else:
                ok, err = ctrl.complete_task(arg.upper())
                console.print(f"  [green]✓ {arg.upper()} done.[/green]\n" if ok else f"  [red]{err}[/red]\n")

        elif slash in ("del", "delete"):
            if not arg:
                console.print("  [red]Usage:[/red] /del <ID>\n")
            else:
                ok, err = ctrl.delete_task(arg.upper())
                console.print(f"  [dim]Deleted {arg.upper()}.[/dim]\n" if ok else f"  [red]{err}[/red]\n")

        elif slash in ("search", "find"):
            if not arg:
                console.print("  [red]Usage:[/red] /search <query>\n")
            else:
                tasks = ctrl.list_tasks(search=arg)
                console.print(_task_table(tasks, f"'{arg}' ({len(tasks)})") if tasks else "  [dim]No results.[/dim]")
                console.print()

        elif slash in ("stats", "analytics"):
            s  = ctrl.get_analytics()
            pc = "green" if s["productivity"] >= 70 else "yellow" if s["productivity"] >= 40 else "red"
            console.print(Panel(
                f"  [dim]Total[/dim]        [white]{s['total']}[/white]\n"
                f"  [dim]Completed[/dim]    [green]{s['completed']}[/green]\n"
                f"  [dim]Pending[/dim]      [yellow]{s['pending']}[/yellow]\n"
                f"  [dim]Overdue[/dim]      [red]{s['overdue']}[/red]\n"
                f"  [dim]Rate[/dim]         [{pc}]{s['productivity']}%[/{pc}]\n"
                f"  [dim]Streak[/dim]       [white]{s['streak']}d[/white]",
                title="[dim]Analytics[/dim]", border_style="dim", padding=(0, 2),
            ))
            console.print()

        elif slash == "optimize":
            with console.status("[dim]Building schedule...[/dim]", spinner="dots"):
                sched, err = ctrl.optimize_schedule()
            if err:
                console.print(f"  [red]{err}[/red]\n")
            else:
                console.print(Panel(sched, title="[dim]AI Schedule[/dim]", border_style="dim", padding=(1, 2)))
            console.print()

        elif slash == "report":
            fn = ctrl.export_report()
            console.print(f"  [dim]Report saved:[/dim] [white]{fn}[/white]\n")

        elif slash in ("add", "task", "newtask"):
            draft = {}
            console.print("  [dim]Draft cleared. Tell me about the task you want to add.[/dim]\n")

        else:
            console.print(f"  [dim]Unknown command [white]/{slash}[/white]. Type [white]/help[/white] for the list.[/dim]\n")

        return True

    # Main chat loop
    while True:
        try:
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n  [dim]Chat closed.[/dim]")
            break

        if not user_input:
            continue

        # Slash command?
        if user_input.startswith("/"):
            result = _handle_slash(user_input[1:])
            if result is None:
                break
            continue

        # ══════════════════════════════════════════════════════════════════
        # Step 0: Prompt Enhancement (resolve pronouns/shortcuts)
        # ══════════════════════════════════════════════════════════════════
        enhanced_input = user_input
        if history or draft:
            with console.status("[dim]Clarifying your message...[/dim]", spinner="dots"):
                enhanced_input = ctrl.enhance_prompt(user_input, history=history, draft=draft)
            if enhanced_input != user_input:
                console.print(f"  [dim]→ {enhanced_input}[/dim]")

        # ══════════════════════════════════════════════════════════════════
        # Step 1: Multi-Agent Decomposition
        # Splits complex prompts into ordered sub-tasks.
        # Single intent → 1 item; compound prompt → 2+ items.
        # ══════════════════════════════════════════════════════════════════
        with console.status("[dim]Understanding your request...[/dim]", spinner="dots"):
            sub_tasks = ctrl.ai.decompose_prompt(enhanced_input, history=history)

        if len(sub_tasks) > 1:
            console.print(
                f"  [dim cyan]{len(sub_tasks)} tasks detected — processing in order[/dim cyan]"
            )

        # ══════════════════════════════════════════════════════════════════
        # Step 2–4: Process each sub-task
        # ══════════════════════════════════════════════════════════════════
        for task_idx, sub in enumerate(sub_tasks):
            sub_msg    = sub["sub_message"]
            sub_intent = sub["intent"]

            # Show sub-task header when there are multiple
            if len(sub_tasks) > 1:
                console.print(f"\n  [dim]── [{task_idx + 1}/{len(sub_tasks)}][/dim] [white]{sub_msg}[/white]")

            # Intent Classification
            with console.status("[dim]Classifying intent...[/dim]", spinner="dots"):
                intent_info = ctrl.classify_intent(sub_msg, history=history)

            # Override with decomposer's intent if classifier says "unclear"
            if intent_info.get("intent") == "unclear" and sub_intent != "unclear":
                intent_info["intent"] = sub_intent

            intent_name  = intent_info.get("intent", "unclear")
            icon, color, display = INTENT_ICONS.get(intent_name, ("◦", "dim", ""))
            if intent_name not in ("chitchat", "unclear") and display:
                console.print(f"  [dim]{icon}[/dim] [dim]Detected:[/dim] [{color}]{display}[/{color}]")

            # Main AI call — live animated thinking display
            def _do_chat(_sub_msg=sub_msg, _intent_info=intent_info):
                return ctrl.chat(
                    _sub_msg,
                    history=history,
                    draft=draft,
                    intent_info=_intent_info,
                    location=_user_location,
                )

            reply, action, err = _live_thinking_call(_do_chat, intent_name)

            if err:
                console.print(Panel(
                    f"[yellow]⚠  {err}[/yellow]",
                    title="[dim]AI[/dim]", border_style="yellow", padding=(0, 2),
                ))
                console.print()
                continue

            # Update history (use original user_input for first sub-task only)
            history.append({"role": "user",      "content": sub_msg})
            history.append({"role": "assistant", "content": reply or ""})
            if len(history) > 20:
                history = history[-20:]

            # Print AI reply
            if reply:
                console.print(Panel(
                    f"[white]{reply}[/white]",
                    title="[dim]AI[/dim]", border_style="dim", padding=(0, 2),
                ))

            if not action:
                # Intent-based action fallbacks
                # AI gave a text reply but forgot to emit TASKFLOW_ACTION.
                # Synthesize the correct action based on detected intent.

                if intent_name == "complete_task":
                    fallback_tid = (intent_info.get("entities") or {}).get("task_id", "").strip().upper()
                    if fallback_tid:
                        ok, err_fb = ctrl.complete_task(fallback_tid)
                        if ok:
                            task_fb, _ = ctrl.get_task(fallback_tid)
                            name_fb = task_fb["name"] if task_fb else fallback_tid
                            console.print(f"  [green]✓[/green] [dim]{name_fb}[/dim] [white]({fallback_tid})[/white] done.\n")
                        else:
                            console.print(f"  [red]{err_fb}[/red]\n")
                        continue

                elif intent_name == "list_tasks":
                    tasks = ctrl.list_tasks()
                    if not tasks:
                        console.print("  [dim]No tasks found.[/dim]\n")
                    else:
                        console.print(_task_table(tasks, f"Tasks ({len(tasks)})"))
                    console.print()
                    continue

                elif intent_name == "search_tasks":
                    kw = (intent_info.get("entities") or {}).get("keyword", "").strip()
                    tasks = ctrl.list_tasks(search=kw) if kw else ctrl.list_tasks()
                    if not tasks:
                        console.print("  [dim]No tasks found.[/dim]\n")
                    else:
                        console.print(_task_table(tasks, f"Search ({len(tasks)})"))
                    console.print()
                    continue

                elif intent_name == "analytics":
                    s  = ctrl.get_analytics()
                    pc = "green" if s["productivity"] >= 70 else "yellow" if s["productivity"] >= 40 else "red"
                    console.print(Panel(
                        f"  [dim]Total[/dim]     [white]{s['total']}[/white]   "
                        f"[dim]Done[/dim] [green]{s['completed']}[/green]   "
                        f"[dim]Pending[/dim] [yellow]{s['pending']}[/yellow]   "
                        f"[dim]Overdue[/dim] [red]{s['overdue']}[/red]   "
                        f"[dim]Rate[/dim] [{pc}]{s['productivity']}%[/{pc}]   "
                        f"[dim]Streak[/dim] [white]{s['streak']}d[/white]",
                        title="[dim]Analytics[/dim]", border_style="dim", padding=(0, 1),
                    ))
                    if s.get("by_status"):   _bar_chart(s["by_status"],   "Status")
                    if s.get("by_priority"): _bar_chart(s["by_priority"], "Priority")
                    if s.get("by_category"): _bar_chart(s["by_category"], "Category")
                    console.print()
                    continue

                console.print()
                continue

            # Action validation
            action_name = action.get("action") if action else None
            is_match, _ = ctrl.validate_action(intent_name, action_name)
            if not is_match:
                console.print(
                    f"  [dim yellow]⚠ Intent mismatch: expected [white]{intent_name}[/white]"
                    f" but AI triggered [white]{action_name}[/white][/dim yellow]"
                )

            # Dispatch action
            result_type, result_data, action_err, draft = ctrl.handle_chat_action(
                action, current_draft=draft
            )

            if action_err:
                console.print(f"  [red]{action_err}[/red]\n")
                continue

            # Render result
            if result_type == "draft_updated":
                if draft:
                    collected = "  ".join(
                        f"[dim]{k}[/dim] [white]{v}[/white]" for k, v in draft.items() if v
                    )
                    console.print(f"  [dim]Draft →[/dim] {collected}\n")

            elif result_type == "confirm_preview":
                _render_task_card(result_data, title="Preview — save this task?")
                if Confirm.ask("  Save?"):
                    task_id, _ = ctrl.add_manual(
                        name=result_data.get("name"),
                        category=result_data.get("category", "General"),
                        priority=result_data.get("priority", "Medium"),
                        due_date=result_data.get("due_date"),
                        notes=result_data.get("notes"),
                    )
                    draft = {}
                    console.print(f"  [green]✓[/green] Saved as [white]{task_id}[/white]\n")
                else:
                    console.print("  [dim]Skipped. Draft kept — /clear to abandon.[/dim]\n")

            elif result_type == "task_created":
                _render_task_card(result_data, title="Task Created")
                console.print()

            elif result_type == "task_list":
                tasks = result_data
                if not tasks:
                    console.print("  [dim]No tasks found.[/dim]")
                else:
                    label = "Search Results" if action_name == "search_tasks" else "Tasks"
                    console.print(_task_table(tasks, f"{label} ({len(tasks)})"))
                console.print()

            elif result_type == "task_edited":
                _render_task_card(result_data, title="Updated")
                console.print()

            elif result_type == "task_completed":
                t = result_data
                console.print(f"  [green]✓[/green] [dim]{t['name']}[/dim] [white]({t['id']})[/white] done.\n")

            elif result_type == "task_deleted":
                console.print(f"  [dim]Moved {result_data['id']} to recycle bin.[/dim]\n")

            elif result_type == "reminder_set":
                t = result_data
                remind_time = t.get("reminder_at", "")
                console.print(f"  [cyan]Reminder set:[/cyan] [white]{t['name']}[/white] at [cyan]{remind_time}[/cyan]\n")

            elif result_type == "analytics":
                s  = result_data
                pc = "green" if s["productivity"] >= 70 else "yellow" if s["productivity"] >= 40 else "red"
                console.print(Panel(
                    f"  [dim]Total[/dim]     [white]{s['total']}[/white]   "
                    f"[dim]Done[/dim] [green]{s['completed']}[/green]   "
                    f"[dim]Pending[/dim] [yellow]{s['pending']}[/yellow]   "
                    f"[dim]Overdue[/dim] [red]{s['overdue']}[/red]   "
                    f"[dim]Rate[/dim] [{pc}]{s['productivity']}%[/{pc}]   "
                    f"[dim]Streak[/dim] [white]{s['streak']}d[/white]",
                    title="[dim]Analytics[/dim]", border_style="dim", padding=(0, 1),
                ))
                if s.get("by_status"):
                    _bar_chart(s["by_status"], "Status")
                if s.get("by_priority"):
                    _bar_chart(s["by_priority"], "Priority")
                if s.get("by_category"):
                    _bar_chart(s["by_category"], "Category")
                console.print()

            elif result_type == "draft_cleared":
                console.print("  [dim]Draft cleared.[/dim]\n")


# optimize

@cli.command()
def optimize():
    """AI-powered full-day schedule optimizer."""
    ctrl = _get_ctrl()
    console.print(Panel(
        "[dim]Analyzing your pending tasks...[/dim]\n[dim]This may take 20-40 seconds.[/dim]",
        border_style="dim",
    ))
    with console.status("[dim]Building schedule...[/dim]", spinner="dots"):
        schedule, err = ctrl.optimize_schedule()
    if err:
        console.print(f"  [red]Error:[/red] {err}")
        return
    if not schedule:
        console.print("  [dim]No schedule generated. Try again.[/dim]")
        return
    console.print(Panel(
        schedule,
        title="[bold white]AI Schedule[/bold white]",
        border_style="dim",
        padding=(1, 2),
    ))


# focus

@cli.command()
@click.argument("task_id")
@click.option("--minutes", "-m", default=25, show_default=True, help="Duration in minutes")
def focus(task_id, minutes):
    """Pomodoro focus timer for a task."""
    ctrl = _get_ctrl()
    task, err = ctrl.get_task(task_id.upper())
    if err:
        console.print(f"  [red]Error:[/red] {err}")
        return
    if task["status"] == "completed":
        console.print("  [dim]Task already completed.[/dim]")
        return

    total = minutes * 60
    console.print(Panel(
        f"[bold white]Focus: {task['name']}[/bold white]\n"
        f"[dim]{task.get('category','General')} · {task['priority']} priority · {minutes} min[/dim]\n\n"
        f"[dim]Ctrl+C to stop early.[/dim]",
        border_style="dim",
    ))
    time.sleep(1)

    try:
        start = time.time()
        with Live(console=console, refresh_per_second=1) as live:
            for elapsed in range(total + 1):
                remaining        = total - elapsed
                m, s             = divmod(remaining, 60)
                done_blocks      = int((elapsed / total) * 36)
                bar              = "█" * done_blocks + "░" * (36 - done_blocks)
                pct              = int(elapsed / total * 100)
                time_color       = "green" if pct > 75 else "yellow" if pct > 40 else "cyan"
                live.update(Panel(
                    f"\n  [bold white]{task['name']}[/bold white]\n"
                    f"  [dim]{task.get('category','General')} · {task['priority']}[/dim]\n\n"
                    f"  [bold {time_color}]{m:02d}:{s:02d}[/bold {time_color}]  remaining\n\n"
                    f"  [dim]{bar}[/dim]  [white]{pct}%[/white]\n",
                    border_style="dim",
                    title="[dim]Pomodoro[/dim]",
                ))
                if remaining == 0:
                    break
                time.sleep(1)

        console.print(Panel(
            f"[bold white]Done![/bold white]\n\n"
                f"[dim]{task['name']} — {minutes} min focused.[/dim]\n\n"
            f"[dim]Take a 5-minute break.[/dim]",
            border_style="dim",
        ))
        if Confirm.ask("  Mark task as completed?"):
            ctrl.complete_task(task_id.upper())
            console.print(f"  [green]✓[/green] {task['name']} completed.")

    except KeyboardInterrupt:
        elapsed_m = int((time.time() - start) / 60)
        console.print(f"\n  [dim]Stopped after ~{elapsed_m} min.[/dim]")


# analytics

@cli.command()
def analytics():
    """Productivity analytics with ASCII charts."""
    ctrl  = _get_ctrl()
    stats = ctrl.get_analytics()

    console.print(Panel("[bold white]Analytics[/bold white]", border_style="dim"))

    pc = "green" if stats["productivity"] >= 70 else "yellow" if stats["productivity"] >= 40 else "red"
    console.print(f"""
  [dim]Total tasks[/dim]    [white]{stats['total']}[/white]
  [dim]Completed[/dim]      [green]{stats['completed']}[/green]
  [dim]Pending[/dim]        [yellow]{stats['pending']}[/yellow]
  [dim]Overdue[/dim]        [red]{stats['overdue']}[/red]
  [dim]Productivity[/dim]   [{pc}]{stats['productivity']}%[/{pc}]
  [dim]Day streak[/dim]     [white]{stats['streak']}[/white]
""")
    if stats.get("by_status"):
        _bar_chart(stats["by_status"], "Status")
    if stats.get("by_priority"):
        _bar_chart(stats["by_priority"], "Priority")
    if stats.get("by_category"):
        _bar_chart(stats["by_category"], "Category")
    console.print()


# export

@cli.command()
def export():
    """Export tasks to a Markdown report."""
    ctrl     = _get_ctrl()
    filename = ctrl.export_report()
    console.print(Panel(
        f"[green]Report saved[/green]\n[dim]{filename}[/dim]",
        border_style="dim",
    ))


# Entry

if __name__ == "__main__":
    cli()
