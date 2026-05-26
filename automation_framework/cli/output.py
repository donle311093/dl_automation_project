import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table

_console = Console()
_err_console = Console(stderr=True)


def render(data, fmt="table", headers=None):
    if fmt == "json":
        _console.print_json(json.dumps(data, default=str))
    elif fmt == "yaml":
        try:
            import yaml
            _console.print(yaml.dump(data, default_flow_style=False))
        except ImportError:
            _console.print("[yellow]PyYAML not installed, falling back to JSON[/yellow]")
            _console.print_json(json.dumps(data, default=str))
    else:
        _render_table(data, headers)


def _render_table(data, headers=None):
    table = Table(show_header=True, header_style="bold cyan")

    if isinstance(data, list):
        if not data:
            _console.print("[dim]No results.[/dim]")
            return
        if isinstance(data[0], dict):
            cols = headers or list(data[0].keys())
            for col in cols:
                table.add_column(str(col))
            for row in data:
                table.add_row(*[str(row.get(c, "")) for c in cols])
        else:
            table.add_column(headers[0] if headers else "Value")
            for item in data:
                table.add_row(str(item))
    elif isinstance(data, dict):
        table.add_column("Key")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(str(k), str(v))
    else:
        _console.print(str(data))
        return

    _console.print(table)


@contextmanager
def spinner(label):
    start = time.monotonic()
    spinner_obj = Spinner("dots", text=label)
    with Live(spinner_obj, console=_console, refresh_per_second=10):
        try:
            yield
        finally:
            elapsed = time.monotonic() - start
    _console.print(f"[dim]{label} — done in {elapsed:.1f}s[/dim]")


def confirm(msg) -> bool:
    try:
        answer = input(f"{msg} [y/N] ").strip().lower()
        return answer == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def print_success(msg):
    _console.print(f"[green]{msg}[/green]")


def print_error(msg):
    _err_console.print(f"[red]{msg}[/red]")


def print_warning(msg):
    _console.print(f"[yellow]{msg}[/yellow]")


def audit(session, action, detail, status="OK"):
    if session.no_log:
        return
    log_dir = Path.home() / ".automation_framework"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "audit.log"
    ts = datetime.now(timezone.utc).isoformat()
    platform = getattr(session, "platform", "unknown")
    with open(log_path, "a") as f:
        f.write(f"{ts} | {platform} | {action} | {detail} | {status}\n")
