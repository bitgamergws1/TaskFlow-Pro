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

# ── Constants ─────────────────────────────────────────────────────────────────

EXPIRY = date(2026, 5, 20)
console = Console()

PRIORITY_STYLE = {"High": "red",    "Medium": "yellow", "Low": "green"}
STATUS_ICON    = {"pending": "·",   "completed": "✓"}
VALID_PRIORITIES  = ["High", "Medium", "Low"]
VALID_CATEGORIES  = ["Work", "Study", "Personal", "Health", "Finance", "General"]

CITY_FILE = os.path.join(os.path.expanduser("~"), ".taskflow_city")

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


# ── Guards ────────────────────────────────────────────────────────────────────

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


# ── Weather ───────────────────────────────────────────────────────────────────

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
        pass


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
    """Returns weather dict or None, using stored city or IP detection."""
    city = _load_city()
    if not city:
        city = _detect_city_from_ip()
        if city:
            _save_city(city)
    if not city:
        return None
    return _fetch_weather(city)


# ── Render Helpers ────────────────────────────────────────────────────────────

def _print_banner():
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(f"  [dim]{date.today().strftime('%A, %d %B %Y')}  |  DevNest Internship  |  Week 1[/dim]\n")


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
    table.add_column("Task",     style="white",  min_width=24)
    table.add_column("Category", style="dim",    width=12)
    table.add_column("Priority", justify="center", width=9)
    table.add_column("Due",      justify="center", width=13)
    table.add_column("Status",   justify="center", width=12)

    today = date.today()
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
                pass

        name_str = f"[dim]{t['name']}[/dim]" if t["status"] == "completed" else (
            f"[red]{t['name']}[/red]" if overdue else t["name"]
        )

        table.add_row(
            t["id"],
            name_str,
            t.get("category", "General"),
            f"[{p_style}]{t['priority']}[/{p_style}]",
            due_str if overdue else (t.get("due_date") or "[dim]--[/dim]"),
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
    console.print(Panel(
        f"  [dim]ID[/dim]       [white]{t['id']}[/white]\n"
        f"  [dim]Name[/dim]     [bold white]{t['name']}[/bold white]\n"
        f"  [dim]Priority[/dim] [{p_style}]{t.get('priority','Medium')}[/{p_style}]\n"
        f"  [dim]Category[/dim] [white]{t.get('category','General')}[/white]\n"
        f"  [dim]Due[/dim]      [white]{t.get('due_date') or '--'}[/white]\n"
        f"  [dim]Notes[/dim]    [dim]{t.get('notes') or '--'}[/dim]",
        title=f"[bold white]{title}[/bold white]",
        border_style="dim",
        padding=(0, 2),
    ))


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _show_dashboard():
    ctrl = _get_ctrl()
    _print_banner()

    # Ping proxy early so Render's AI backend warms up in background
    import threading as _t
    from ai_gateway import AIGateway as _AIGateway
    _t.Thread(target=_AIGateway.wake_up, daemon=True).start()

    # Fetch weather in background
    weather_result = [None]
    def _weather_thread():
        weather_result[0] = _get_weather_async()
    wt = threading.Thread(target=_weather_thread, daemon=True)
    wt.start()

    stats = ctrl.get_analytics()
    tasks = ctrl.list_tasks()

    # ── Stats row ──────────────────────────────────────────────────────────
    pc     = "green" if stats["productivity"] >= 70 else "yellow" if stats["productivity"] >= 40 else "red"
    streak = f"  {stats['streak']}d 🔥" if stats["streak"] >= 3 else f"  {stats['streak']}d"
    stat_panels = [
        Panel(f"[bold white]{stats['total']}[/bold white]\n[dim]Total[/dim]",                     border_style="dim", expand=True),
        Panel(f"[bold green]{stats['completed']}[/bold green]\n[dim]Done[/dim]",                  border_style="dim", expand=True),
        Panel(f"[bold yellow]{stats['pending']}[/bold yellow]\n[dim]Pending[/dim]",               border_style="dim", expand=True),
        Panel(f"[bold red]{stats['overdue']}[/bold red]\n[dim]Overdue[/dim]",                     border_style="dim", expand=True),
        Panel(f"[bold {pc}]{stats['productivity']}%[/bold {pc}]\n[dim]Done rate[/dim]",           border_style="dim", expand=True),
        Panel(f"[bold white]{streak}[/bold white]\n[dim]Streak[/dim]",                            border_style="dim", expand=True),
    ]
    console.print(Columns(stat_panels))

    # ── Weather (wait up to 3s) ────────────────────────────────────────────
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

    # ── Task table ─────────────────────────────────────────────────────────
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

    # ── AI motivation — loads in background, tips animate meanwhile ────────
    console.print()
    TIPS = [
        "💡  Break big tasks into 25-min Pomodoro blocks — use [white]taskflow focus <ID>[/white]",
        "🎯  High priority tasks first, always. Your brain is freshest in the morning.",
        "📋  Name tasks as actions: 'Write report' beats 'Report' every time.",
        "🔥  A 3-day streak beats a perfect week you never started.",
        "⚡  If it takes < 2 minutes, do it now — don't add it to the list.",
        "📅  Set due dates even for flexible tasks — deadlines create focus.",
        "🗂️  Group similar tasks by category — context-switching kills momentum.",
        "✅  Complete your hardest task before lunch. Everything else feels easy after.",
        "🧠  Pending tasks drain mental energy even when you're not working on them.",
        "📊  Check [white]taskflow analytics[/white] weekly — what gets measured gets done.",
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


# ── CLI Group ─────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def cli(ctx):
    """TaskFlow Pro -- Smart Productivity CLI by DevNest"""
    _check_expiry()
    if ctx.invoked_subcommand is None:
        _show_dashboard()


# ── add ───────────────────────────────────────────────────────────────────────

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
        name     = Prompt.ask("[white]Task name[/white]")
        category = Prompt.ask("[white]Category[/white]", choices=VALID_CATEGORIES, default="General")
        priority = Prompt.ask("[white]Priority[/white]", choices=VALID_PRIORITIES, default="Medium")
        due_date = Prompt.ask("[white]Due date (YYYY-MM-DD)[/white]", default="")
        notes    = Prompt.ask("[white]Notes[/white]", default="")

        due_date = due_date.strip() or None
        notes    = notes.strip() or None
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError:
                console.print("[red]Invalid date. Use YYYY-MM-DD.[/red]")
                return

        task_id, _ = ctrl.add_manual(name, category, priority, due_date, notes)
        _render_task_card(
            {"id": task_id, "name": name, "priority": priority,
             "category": category, "due_date": due_date, "notes": notes},
            title="Task Added",
        )


# ── list ──────────────────────────────────────────────────────────────────────

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


# ── complete ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def complete(task_id):
    """Mark a task as completed."""
    ctrl = _get_ctrl()
    ok, err = ctrl.complete_task(task_id.upper())
    if ok:
        console.print(f"  [green]✓[/green] [white]{task_id.upper()}[/white] marked as done.")
    else:
        console.print(f"  [red]Error:[/red] {err}")


# ── delete ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def delete(task_id):
    """Soft-delete a task."""
    ctrl = _get_ctrl()
    ok, err = ctrl.delete_task(task_id.upper())
    if ok:
        console.print(f"  [dim]Moved {task_id.upper()} to recycle bin.  Use [white]taskflow restore {task_id.upper()}[/white] to undo.[/dim]")
    else:
        console.print(f"  [red]Error:[/red] {err}")


# ── restore ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def restore(task_id):
    """Restore a task from the recycle bin."""
    ctrl = _get_ctrl()
    ok, err = ctrl.restore_task(task_id.upper())
    if ok:
        console.print(f"  [green]Restored[/green] {task_id.upper()}.")
    else:
        console.print(f"  [red]Error:[/red] {err}")


# ── bin ───────────────────────────────────────────────────────────────────────

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


# ── edit ──────────────────────────────────────────────────────────────────────

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

    name     = Prompt.ask(f"Name     [dim][{task['name']}][/dim]",              default="")
    category = Prompt.ask(f"Category [dim][{task['category']}][/dim]",          choices=VALID_CATEGORIES + [""], default="")
    priority = Prompt.ask(f"Priority [dim][{task['priority']}][/dim]",          choices=VALID_PRIORITIES + [""], default="")
    due_date = Prompt.ask(f"Due date [dim][{task.get('due_date','--')}][/dim]", default="")
    notes    = Prompt.ask(f"Notes    [dim][{task.get('notes','--')}][/dim]",    default="")

    updates = {}
    if name.strip():     updates["name"]     = name.strip()
    if category.strip(): updates["category"] = category.strip()
    if priority.strip(): updates["priority"] = priority.strip()
    if due_date.strip():
        try:
            date.fromisoformat(due_date.strip())
            updates["due_date"] = due_date.strip()
        except ValueError:
            console.print("[red]Invalid date -- skipped.[/red]")
    if notes.strip(): updates["notes"] = notes.strip()

    if not updates:
        console.print("[dim]No changes.[/dim]")
        return
    ok, err = ctrl.edit_task(task_id.upper(), **updates)
    console.print("  [green]Updated.[/green]" if ok else f"  [red]Error:[/red] {err}")


# ── search ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query")
def search(query):
    """Search tasks."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_tasks(search=query)
    if not tasks:
        console.print(f"  [dim]No results for '{query}'.[/dim]")
        return
    console.print(_task_table(tasks, f"Search: '{query}'"))
    console.print(f"  [dim]{len(tasks)} result(s)[/dim]")


# ── weather ───────────────────────────────────────────────────────────────────

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


# ── chat ──────────────────────────────────────────────────────────────────────

@cli.command()
def chat():
    """AI chat -- create, search, edit tasks through natural conversation."""
    ctrl    = _get_ctrl()
    history = []   # [{role, content}]
    draft   = {}   # partial task being built: {name, priority, due_date, category, notes}

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
        """Handle slash commands. Returns True if handled, False if unknown."""
        nonlocal draft
        parts = cmd.strip().split(None, 1)
        slash = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        if slash in ("/exit", "/quit", "/q"):
            console.print("  [dim]Chat closed.[/dim]")
            return None   # signal to exit loop

        elif slash == "/help":
            console.print(SLASH_HELP)

        elif slash == "/draft":
            _show_draft()

        elif slash == "/clear":
            draft = {}
            console.print("  [dim]Draft cleared.[/dim]\n")

        elif slash == "/list":
            # /list pending | /list Work | /list
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

        elif slash in ("/done", "/complete"):
            if not arg:
                console.print("  [red]Usage:[/red] /done <ID>\n")
            else:
                ok, err = ctrl.complete_task(arg.upper())
                console.print(f"  [green]✓ {arg.upper()} done.[/green]\n" if ok else f"  [red]{err}[/red]\n")

        elif slash in ("/del", "/delete"):
            if not arg:
                console.print("  [red]Usage:[/red] /del <ID>\n")
            else:
                ok, err = ctrl.delete_task(arg.upper())
                console.print(f"  [dim]Deleted {arg.upper()}.[/dim]\n" if ok else f"  [red]{err}[/red]\n")

        elif slash in ("/search", "/find"):
            if not arg:
                console.print("  [red]Usage:[/red] /search <query>\n")
            else:
                tasks = ctrl.list_tasks(search=arg)
                console.print(_task_table(tasks, f"'{arg}' ({len(tasks)})") if tasks else "  [dim]No results.[/dim]")
                console.print()

        elif slash in ("/stats", "/analytics"):
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

        elif slash == "/optimize":
            with console.status("[dim]Building schedule...[/dim]", spinner="dots"):
                sched, err = ctrl.optimize_schedule()
            if err:
                console.print(f"  [red]{err}[/red]\n")
            else:
                console.print(Panel(sched, title="[dim]AI Schedule[/dim]", border_style="dim", padding=(1, 2)))
            console.print()

        elif slash == "/report":
            fn = ctrl.export_report()
            console.print(f"  [dim]Report saved:[/dim] [white]{fn}[/white]\n")

        elif slash in ("/add", "/task", "/newtask"):
            draft = {}
            console.print("  [dim]Draft cleared. Tell me about the task you want to add.[/dim]\n")

        else:
            console.print(f"  [dim]Unknown command [white]{slash}[/white]. Type [white]/help[/white] for the list.[/dim]\n")

        return True

    # ── Main chat loop ─────────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n  [dim]Chat closed.[/dim]")
            break

        if not user_input:
            continue

        # ── Slash command? ─────────────────────────────────────────────────
        if user_input.startswith("/"):
            result = _handle_slash(user_input[1:])   # strip the leading /
            if result is None:   # exit signal
                break
            continue

        # ── AI turn ────────────────────────────────────────────────────────
        with console.status("[dim]Thinking... (30–90s, auto-retries on slow start)[/dim]", spinner="dots"):
            reply, action, err = ctrl.chat(user_input, history=history, draft=draft)

        if err:
            console.print(Panel(
                f"[yellow]⚠  {err}[/yellow]",
                title="[dim]AI[/dim]",
                border_style="yellow",
                padding=(0, 2),
            ))
            console.print()
            continue

        # Update history
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": reply or ""})
        if len(history) > 20:
            history = history[-20:]

        # Print AI reply
        if reply:
            console.print(Panel(
                f"[white]{reply}[/white]",
                title="[dim]AI[/dim]",
                border_style="dim",
                padding=(0, 2),
            ))

        if not action:
            console.print()
            continue

        # ── Dispatch action ────────────────────────────────────────────────
        result_type, result_data, action_err, draft = ctrl.handle_chat_action(action, current_draft=draft)

        if action_err:
            console.print(f"  [red]{action_err}[/red]\n")
            continue

        if result_type == "draft_updated":
            # Silent — draft is updated, conversation continues
            if draft:
                collected = "  ".join(f"[dim]{k}[/dim] [white]{v}[/white]" for k, v in draft.items() if v)
                console.print(f"  [dim]Draft:[/dim] {collected}\n")

        elif result_type == "confirm_preview":
            # AI wants to confirm before saving
            _render_task_card(result_data, title="Preview — save this task?")
            if Confirm.ask("  Save?"):
                task_id, _ = ctrl.add_manual(
                    name=result_data.get("name"),
                    category=result_data.get("category", "General"),
                    priority=result_data.get("priority", "Medium"),
                    due_date=result_data.get("due_date"),
                    notes=result_data.get("notes"),
                )
                draft = {}   # clear
                console.print(f"  [green]✓[/green] Saved as [white]{task_id}[/white]\n")
            else:
                console.print("  [dim]Skipped. Draft kept — keep adding details or /clear to abandon.[/dim]\n")

        elif result_type == "task_created":
            _render_task_card(result_data, title="Task Created")
            console.print()

        elif result_type == "task_list":
            tasks = result_data
            if not tasks:
                console.print("  [dim]No tasks found.[/dim]")
            else:
                console.print(_task_table(tasks, f"Results ({len(tasks)})"))
            console.print()

        elif result_type == "task_edited":
            _render_task_card(result_data, title="Updated")
            console.print()

        elif result_type == "task_completed":
            t = result_data
            console.print(f"  [green]✓[/green] [dim]{t['name']}[/dim] [white]({t['id']})[/white] done.\n")

        elif result_type == "task_deleted":
            console.print(f"  [dim]Moved {result_data['id']} to recycle bin.[/dim]\n")

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
            console.print()

        elif result_type == "draft_cleared":
            console.print("  [dim]Draft cleared.[/dim]\n")


# ── optimize ──────────────────────────────────────────────────────────────────

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


# ── focus ─────────────────────────────────────────────────────────────────────

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


# ── analytics ─────────────────────────────────────────────────────────────────

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


# ── export ────────────────────────────────────────────────────────────────────

@cli.command()
def export():
    """Export tasks to a Markdown report."""
    ctrl     = _get_ctrl()
    filename = ctrl.export_report()
    console.print(Panel(
        f"[green]Report saved[/green]\n[dim]{filename}[/dim]",
        border_style="dim",
    ))


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
