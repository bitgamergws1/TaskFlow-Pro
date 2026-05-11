"""
main.py — TaskFlow Pro CLI Entry Point
Cyberpunk-themed terminal dashboard powered by Rich
"""

import sys
import time
import os
from datetime import date, datetime

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.columns import Columns
from rich.align import Align
from rich import box

load_dotenv()

EXPIRY = date(2026, 5, 20)
console = Console()

PRIORITY_COLOR = {"High": "bold red", "Medium": "bold yellow", "Low": "bold green"}
STATUS_ICON    = {"pending": "⏳", "completed": "✅"}
VALID_PRIORITIES  = ["High", "Medium", "Low"]
VALID_CATEGORIES  = ["Work", "Study", "Personal", "Health", "Finance", "General"]

BANNER = """\
╔══════════════════════════════════════════════════════════╗
║  ████████╗ █████╗ ███████╗██╗  ██╗    ███████╗██╗      ██████╗ ██╗    ██╗  ║
║     ██╔══╝██╔══██╗██╔════╝██║ ██╔╝    ██╔════╝██║     ██╔═══██╗██║    ██║  ║
║     ██║   ███████║███████╗█████╔╝     █████╗  ██║     ██║   ██║██║ █╗ ██║  ║
║     ██║   ██╔══██║╚════██║██╔═██╗     ██╔══╝  ██║     ██║   ██║██║███╗██║  ║
║     ██║   ██║  ██║███████║██║  ██╗    ██║     ███████╗╚██████╔╝╚███╔███╔╝  ║
║     ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝  ║
║                     P R O  ·  Cyber-Sync Edition                            ║
╚══════════════════════════════════════════════════════════╝"""


# ── Guards ────────────────────────────────────────────────────────────────────

def _check_expiry():
    if date.today() > EXPIRY:
        console.print(Panel(
            "[bold red]⛔  EVALUATION PERIOD ENDED[/bold red]\n"
            "[dim]This build expired on 20 May 2026. Contact DevNest.[/dim]",
            border_style="red",
        ))
        sys.exit(1)


def _get_ctrl():
    from controller import TaskController
    return TaskController()


# ── Render Helpers ────────────────────────────────────────────────────────────

def _print_banner():
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(f"[dim]  📅 {date.today().isoformat()}  |  DevNest Python Internship  |  Week 1[/dim]\n")


def _task_table(tasks, title="Tasks"):
    if not tasks:
        return None
    table = Table(
        title=title,
        box=box.DOUBLE_EDGE,
        border_style="cyan",
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("ID",       style="dim",         width=10)
    table.add_column("Task",     style="white",        min_width=22)
    table.add_column("Category", style="blue",         width=12)
    table.add_column("Priority", justify="center",     width=10)
    table.add_column("Due Date", justify="center",     width=12)
    table.add_column("Status",   justify="center",     width=14)

    today = date.today()
    for t in tasks:
        p_color  = PRIORITY_COLOR.get(t["priority"], "white")
        s_icon   = STATUS_ICON.get(t["status"], "❓")
        due      = t.get("due_date") or "[dim]—[/dim]"
        overdue  = False

        if t["status"] == "pending" and t.get("due_date"):
            try:
                if date.fromisoformat(t["due_date"]) < today:
                    due = f"[bold red]{t['due_date']} ⚠[/bold red]"
                    overdue = True
            except ValueError:
                pass

        table.add_row(
            t["id"],
            f"[bold red]{t['name']}[/bold red]" if overdue else t["name"],
            t.get("category", "General"),
            f"[{p_color}]{t['priority']}[/{p_color}]",
            due if overdue else (t.get("due_date") or "[dim]—[/dim]"),
            f"{s_icon} {t['status'].capitalize()}",
        )
    return table


def _bar_chart(data: dict, title: str, color: str = "cyan", width: int = 30):
    if not data:
        return
    max_v = max(data.values(), default=1) or 1
    console.print(f"\n  [bold white]{title}[/bold white]")
    for label, val in sorted(data.items(), key=lambda x: -x[1]):
        bar_len = int((val / max_v) * width)
        bar     = "█" * bar_len + "░" * (width - bar_len)
        pct     = f"{val / max_v * 100:.0f}%"
        console.print(f"  [dim]{label:<14}[/dim] [{color}]{bar}[/{color}] [white]{val}[/white] [dim]{pct}[/dim]")


# ── CLI Group ─────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def cli(ctx):
    """TaskFlow Pro — Smart Productivity CLI by DevNest"""
    _check_expiry()
    if ctx.invoked_subcommand is None:
        _show_dashboard()


# ── Dashboard (default view) ──────────────────────────────────────────────────

def _show_dashboard():
    ctrl = _get_ctrl()
    _print_banner()

    stats = ctrl.get_analytics()
    tasks = ctrl.list_tasks()

    # Stats row
    streak_badge = f"🔥 {stats['streak']}-day streak!" if stats["streak"] >= 3 else f"📅 {stats['streak']} day(s)"
    info_panels  = [
        Panel(f"[bold cyan]{stats['total']}[/bold cyan]\n[dim]Total[/dim]",        border_style="cyan",   expand=True),
        Panel(f"[bold green]{stats['completed']}[/bold green]\n[dim]Done[/dim]",   border_style="green",  expand=True),
        Panel(f"[bold yellow]{stats['pending']}[/bold yellow]\n[dim]Pending[/dim]",border_style="yellow", expand=True),
        Panel(f"[bold red]{stats['overdue']}[/bold red]\n[dim]Overdue[/dim]",      border_style="red",    expand=True),
        Panel(f"[bold magenta]{stats['productivity']}%[/bold magenta]\n[dim]Done %[/dim]", border_style="magenta", expand=True),
        Panel(f"[bold white]{streak_badge}[/bold white]\n[dim]Streak[/dim]",       border_style="white",  expand=True),
    ]
    console.print(Columns(info_panels))
    console.print()

    # Task table
    if tasks:
        table = _task_table(tasks[:15], "Recent Tasks (top 15)")
        console.print(table)
        if len(tasks) > 15:
            console.print(f"[dim]  ... and {len(tasks) - 15} more. Run [bold]taskflow list[/bold] to see all.[/dim]")
    else:
        console.print(Panel("[dim]No tasks yet. Run [bold cyan]taskflow add[/bold cyan] to get started.[/dim]", border_style="dim"))

    # Daily motivation
    console.print()
    with console.status("[cyan]Getting your daily boost from Deepshi...[/cyan]", spinner="dots"):
        msg, err = ctrl.get_motivation()
    if msg:
        console.print(Panel(f"[italic yellow]{msg}[/italic yellow]", title="[bold cyan]🤖 Deepshi Says[/bold cyan]", border_style="cyan"))
    console.print()
    console.print("[dim]Commands: add | list | complete | delete | optimize | focus | analytics | export | bin[/dim]")


# ── add ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--ai", "use_ai", is_flag=True, help="Parse task using Claude AI")
def add(use_ai):
    """Add a new task (manual or AI-powered)."""
    ctrl = _get_ctrl()

    if use_ai:
        text = Prompt.ask("[cyan]Describe your task in natural language[/cyan]")
        with console.status("[cyan]Claude is parsing your task...[/cyan]", spinner="dots"):
            task_id, parsed, err = ctrl.add_ai(text)
        if err:
            console.print(f"[red]AI Error:[/red] {err}")
            if not Confirm.ask("Add manually instead?"):
                return
            use_ai = False
        else:
            console.print(Panel(
                f"[green]✅ Task added:[/green] [white]{parsed['name']}[/white]\n"
                f"Priority: [yellow]{parsed.get('priority','Medium')}[/yellow]  |  "
                f"Category: [blue]{parsed.get('category','General')}[/blue]  |  "
                f"Due: [cyan]{parsed.get('due_date') or '—'}[/cyan]\n"
                f"ID: [bold]{task_id}[/bold]",
                border_style="green",
            ))
            return

    if not use_ai:
        name     = Prompt.ask("[cyan]Task name[/cyan]")
        category = Prompt.ask("[cyan]Category[/cyan]", choices=VALID_CATEGORIES, default="General")
        priority = Prompt.ask("[cyan]Priority[/cyan]", choices=VALID_PRIORITIES, default="Medium")
        due_date = Prompt.ask("[cyan]Due date (YYYY-MM-DD)[/cyan]", default="")
        notes    = Prompt.ask("[cyan]Notes (optional)[/cyan]", default="")

        due_date = due_date.strip() or None
        notes    = notes.strip() or None

        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError:
                console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")
                return

        task_id, _ = ctrl.add_manual(name, category, priority, due_date, notes)
        console.print(Panel(
            f"[green]✅ Task added[/green] | ID: [bold]{task_id}[/bold]\n"
            f"[white]{name}[/white] · {priority} · {category}",
            border_style="green",
        ))


# ── list ──────────────────────────────────────────────────────────────────────

@cli.command(name="list")
@click.option("--status",   "-s", default=None, type=click.Choice(["pending", "completed"]))
@click.option("--category", "-c", default=None, type=click.Choice(VALID_CATEGORIES))
@click.option("--priority", "-p", default=None, type=click.Choice(VALID_PRIORITIES))
def list_tasks(status, category, priority):
    """List all tasks with optional filters."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_tasks(status=status, category=category)

    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]

    if not tasks:
        console.print("[yellow]No tasks match the given filters.[/yellow]")
        return

    title = "All Tasks"
    if status:   title += f" [{status}]"
    if category: title += f" [{category}]"
    if priority: title += f" [{priority}]"

    console.print(_task_table(tasks, title))
    console.print(f"\n[dim]Total: {len(tasks)} task(s)[/dim]")


# ── complete ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def complete(task_id):
    """Mark a task as completed."""
    ctrl = _get_ctrl()
    ok, err = ctrl.complete_task(task_id.upper())
    if ok:
        console.print(f"[bold green]✅ Task [white]{task_id.upper()}[/white] marked as completed![/bold green]")
    else:
        console.print(f"[red]Error:[/red] {err}")


# ── delete ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def delete(task_id):
    """Soft-delete a task (moves to recycle bin)."""
    ctrl = _get_ctrl()
    ok, err = ctrl.delete_task(task_id.upper())
    if ok:
        console.print(f"[yellow]🗑  Task [white]{task_id.upper()}[/white] moved to recycle bin. Use [bold]taskflow restore {task_id.upper()}[/bold] to undo.[/yellow]")
    else:
        console.print(f"[red]Error:[/red] {err}")


# ── restore ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def restore(task_id):
    """Restore a task from the recycle bin."""
    ctrl = _get_ctrl()
    ok, err = ctrl.restore_task(task_id.upper())
    if ok:
        console.print(f"[green]♻️  Task [white]{task_id.upper()}[/white] restored successfully.[/green]")
    else:
        console.print(f"[red]Error:[/red] {err}")


# ── bin ───────────────────────────────────────────────────────────────────────

@cli.command(name="bin")
def recycle_bin():
    """View deleted tasks (recycle bin)."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_bin()
    if not tasks:
        console.print("[dim]Recycle bin is empty.[/dim]")
        return
    console.print(_task_table(tasks, "🗑  Recycle Bin"))
    console.print(f"[dim]Use [bold]taskflow restore <ID>[/bold] to recover a task.[/dim]")


# ── edit ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
def edit(task_id):
    """Interactively edit a task."""
    ctrl = _get_ctrl()
    task, err = ctrl.get_task(task_id.upper())
    if err:
        console.print(f"[red]Error:[/red] {err}")
        return

    console.print(Panel(
        f"Editing [bold]{task['name']}[/bold]\n"
        f"[dim]Leave blank to keep current value[/dim]",
        border_style="cyan",
    ))

    name     = Prompt.ask(f"Name     [dim][{task['name']}][/dim]",     default="")
    category = Prompt.ask(f"Category [dim][{task['category']}][/dim]", choices=VALID_CATEGORIES + [""], default="")
    priority = Prompt.ask(f"Priority [dim][{task['priority']}][/dim]", choices=VALID_PRIORITIES + [""], default="")
    due_date = Prompt.ask(f"Due Date [dim][{task.get('due_date','—')}][/dim]", default="")
    notes    = Prompt.ask(f"Notes    [dim][{task.get('notes','—')}][/dim]",    default="")

    updates = {}
    if name.strip():     updates["name"]     = name.strip()
    if category.strip(): updates["category"] = category.strip()
    if priority.strip(): updates["priority"] = priority.strip()
    if due_date.strip():
        try:
            date.fromisoformat(due_date.strip())
            updates["due_date"] = due_date.strip()
        except ValueError:
            console.print("[red]Invalid date — skipped.[/red]")
    if notes.strip(): updates["notes"] = notes.strip()

    if not updates:
        console.print("[dim]No changes made.[/dim]")
        return

    ok, err = ctrl.edit_task(task_id.upper(), **updates)
    if ok:
        console.print(f"[green]✅ Task updated.[/green]")
    else:
        console.print(f"[red]Error:[/red] {err}")


# ── search ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query")
def search(query):
    """Search tasks by name, notes, or category."""
    ctrl  = _get_ctrl()
    tasks = ctrl.list_tasks(search=query)
    if not tasks:
        console.print(f"[yellow]No tasks found for '[white]{query}[/white]'.[/yellow]")
        return
    console.print(_task_table(tasks, f"Search: '{query}'"))
    console.print(f"[dim]{len(tasks)} result(s)[/dim]")


# ── optimize ──────────────────────────────────────────────────────────────────

@cli.command()
def optimize():
    """AI-powered full-day schedule optimizer (Deepshi R2)."""
    ctrl = _get_ctrl()
    console.print(Panel(
        "[cyan]Sending your tasks to Deepshi R2 for analysis...[/cyan]\n"
        "[dim]This may take 20-40 seconds.[/dim]",
        border_style="cyan",
    ))
    with console.status("[cyan]🧠 Deepshi is building your schedule...[/cyan]", spinner="aesthetic"):
        schedule, err = ctrl.optimize_schedule()

    if err:
        console.print(f"[red]Optimizer error:[/red] {err}")
        return
    if not schedule:
        console.print("[yellow]No schedule generated. Try again.[/yellow]")
        return

    console.print(Panel(
        schedule,
        title="[bold cyan]⚡ AI-Optimized Daily Schedule[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


# ── focus (Pomodoro) ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
@click.option("--minutes", "-m", default=25, show_default=True, help="Pomodoro duration in minutes")
def focus(task_id, minutes):
    """Start a Pomodoro focus timer for a specific task."""
    ctrl = _get_ctrl()
    task, err = ctrl.get_task(task_id.upper())
    if err:
        console.print(f"[red]Error:[/red] {err}")
        return
    if task["status"] == "completed":
        console.print("[yellow]This task is already completed.[/yellow]")
        return

    total = minutes * 60
    console.print(Panel(
        f"[bold green]🍅 Starting Pomodoro for:[/bold green]\n\n"
        f"  [bold white]{task['name']}[/bold white]\n"
        f"  [dim]{task.get('category','General')} · {task['priority']} priority[/dim]\n\n"
        f"[dim]Duration: {minutes} minutes | Press Ctrl+C to exit[/dim]",
        border_style="green",
        title="Focus Mode",
    ))
    time.sleep(1.5)

    try:
        start_time = time.time()
        with Live(console=console, refresh_per_second=1) as live:
            for elapsed in range(total + 1):
                remaining = total - elapsed
                mins, secs = divmod(remaining, 60)
                done_blocks = int((elapsed / total) * 40)
                prog_bar    = "█" * done_blocks + "░" * (40 - done_blocks)
                pct         = int(elapsed / total * 100)

                panel_content = (
                    f"\n  [bold cyan]🍅 POMODORO FOCUS MODE[/bold cyan]\n\n"
                    f"  Task: [bold white]{task['name']}[/bold white]\n"
                    f"  [dim]{task.get('category','General')} · {task['priority']}[/dim]\n\n"
                    f"  [bold {'green' if pct > 75 else 'yellow' if pct > 40 else 'cyan'}]{mins:02d}:{secs:02d}[/bold {'green' if pct > 75 else 'yellow' if pct > 40 else 'cyan'}] remaining\n\n"
                    f"  [cyan]{prog_bar}[/cyan] {pct}%\n\n"
                    f"  [dim]Ctrl+C to exit • Stay focused 💪[/dim]\n"
                )
                live.update(Panel(panel_content, border_style="green", title=f"Focus: {task['name'][:30]}"))
                if remaining == 0:
                    break
                time.sleep(1)

        console.print(Panel(
            f"[bold green]🔔 Pomodoro Complete![/bold green]\n\n"
            f"Task: [white]{task['name']}[/white]\n\n"
            f"[dim]Take a 5-minute break, then come back stronger.[/dim]",
            border_style="green",
        ))
        if Confirm.ask("Mark this task as completed?"):
            ctrl.complete_task(task_id.upper())
            console.print("[bold green]✅ Task completed![/bold green]")

    except KeyboardInterrupt:
        elapsed_m = int((time.time() - start_time) / 60)
        console.print(f"\n[yellow]Focus session ended after ~{elapsed_m} min.[/yellow]")


# ── analytics ─────────────────────────────────────────────────────────────────

@cli.command()
def analytics():
    """Show detailed productivity analytics with ASCII charts."""
    ctrl  = _get_ctrl()
    stats = ctrl.get_analytics()

    console.print(Panel(
        "[bold cyan]📊 TaskFlow Pro Analytics[/bold cyan]",
        border_style="cyan",
    ))

    # Summary numbers
    prod_color = "green" if stats["productivity"] >= 70 else "yellow" if stats["productivity"] >= 40 else "red"
    console.print(f"""
  [bold]Overview[/bold]
  ─────────────────────────────────
  Total tasks     : [white]{stats['total']}[/white]
  Completed       : [green]{stats['completed']}[/green]
  Pending         : [yellow]{stats['pending']}[/yellow]
  Overdue         : [red]{stats['overdue']}[/red]
  Productivity    : [{prod_color}]{stats['productivity']}%[/{prod_color}]
  Day streak      : [magenta]{stats['streak']} 🔥[/magenta]
""")

    # Completed vs Pending chart
    _bar_chart(
        {"Completed": stats["completed"], "Pending": stats["pending"], "Overdue": stats["overdue"]},
        "Status Breakdown",
        color="cyan",
    )

    # Priority chart
    if stats["by_priority"]:
        priority_colored = {}
        for p, v in stats["by_priority"].items():
            c = {"High": "red", "Medium": "yellow", "Low": "green"}.get(p, "white")
            priority_colored[p] = v
        _bar_chart(stats["by_priority"], "By Priority", color="magenta")

    # Category chart
    if stats["by_category"]:
        _bar_chart(stats["by_category"], "By Category", color="blue")

    console.print()


# ── export ────────────────────────────────────────────────────────────────────

@cli.command()
def export():
    """Export all tasks to a Markdown report file."""
    ctrl     = _get_ctrl()
    filename = ctrl.export_report()
    console.print(Panel(
        f"[green]✅ Report exported![/green]\n\n"
        f"File: [bold cyan]{filename}[/bold cyan]",
        border_style="green",
    ))


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
