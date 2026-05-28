from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import filelock

__all__ = ["VmPool"]

_LOCK_DIR = Path(tempfile.gettempdir()) / "vmforge_locks"

# Allow only safe filename characters; replace everything else with underscore.
# Covers OS-illegal chars on both Linux and Windows (/ \ : < > | ? *) plus spaces.
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]")


class VmPool:
    """Cross-process file-lock gate that serializes clone operations per template.

    Each pabot worker is a separate OS process, so threading.Semaphore does not
    work across workers.  filelock writes a lock file on disk, which IS visible
    across processes, making it the right primitive here.

    Typical usage — release the lock *after* cloning completes so other workers
    can start their own clones while test execution runs in parallel:

        with VmPool.slot(template):
            vm = platform.clone_and_snapshot(...)
        # lock released here; test execution continues lock-free
    """

    @staticmethod
    def _lock_path(template: str) -> Path:
        _LOCK_DIR.mkdir(exist_ok=True)
        safe = _SAFE_NAME.sub("_", template)
        return _LOCK_DIR / f"{safe}.lock"

    @classmethod
    @contextmanager
    def slot(cls, template: str, timeout: float = -1) -> Iterator[None]:
        """Context manager: hold the per-template lock for the duration of the block.

        Args:
            template: VM template name — used as the lock key.
            timeout:  Seconds to wait before raising filelock.Timeout (-1 = wait forever).
        """
        lock = filelock.FileLock(cls._lock_path(template), timeout=timeout)
        with lock:
            yield

    @classmethod
    def acquire(cls, template: str, timeout: float = -1) -> filelock.FileLock:
        """Acquire the per-template lock and return it.

        The caller is responsible for calling release() when done.
        Prefer the slot() context manager when possible.
        """
        lock = filelock.FileLock(cls._lock_path(template))
        lock.acquire(timeout=timeout)
        return lock

    @classmethod
    def release(cls, lock: filelock.FileLock) -> None:
        """Release a lock previously acquired via acquire()."""
        lock.release()
