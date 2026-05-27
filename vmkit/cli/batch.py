from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from cli.output import print_error, print_warning

if TYPE_CHECKING:
    from cli.repl_manager import ManagerREPL


class ScriptError(Exception):
    pass


def run_script(path: str, repl: "ManagerREPL") -> None:
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise ScriptError(f"Script not found: {path}")
    except OSError as e:
        raise ScriptError(f"Could not read script: {e}") from e

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        print_warning(f"[{i}] {line}")
        try:
            tokens = shlex.split(line)
            repl.dispatch(tokens)
        except SystemExit:
            raise
        except Exception as e:
            raise ScriptError(f"Line {i} failed: {e}") from e
