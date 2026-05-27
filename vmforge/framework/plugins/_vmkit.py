import sys
from pathlib import Path


def ensure_vmkit_on_path() -> None:
    """Add vmkit/ to sys.path so vmkit modules are importable.

    Called once at import time by each plugin that wraps a vmkit class.
    Idempotent — skipped if already present.
    """
    vmkit = str(Path(__file__).parents[3] / "vmkit")
    if vmkit not in sys.path:
        sys.path.insert(0, vmkit)
