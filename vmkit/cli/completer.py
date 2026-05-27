from __future__ import annotations

import logging
from typing import Optional

from prompt_toolkit.completion import Completer, Completion

_log = logging.getLogger(__name__)

MANAGER_CMDS = [
    "list-vms", "list-folders", "search", "info", "snapshots", "datastore-info",
    "health-check", "clone", "bulk", "bulk-clone", "delete-vm", "delete-folder",
    "delete-all-vms", "use", "watch", "test", "diff", "export", "run-script",
    "reconnect", "switch-profile", "help", "exit", "quit",
]

_VM_CMDS = frozenset({
    "use", "info", "snapshots", "clone", "diff", "export", "delete-vm",
})


class VMCompleter(Completer):
    def __init__(self, session) -> None:
        self.session = session
        self._vm_cache: Optional[list] = None

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        word = document.get_word_before_cursor()

        if len(words) <= 1:
            for cmd in MANAGER_CMDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
            return

        if words[0] in _VM_CMDS:
            for name in self._get_vm_names():
                if name.startswith(word):
                    yield Completion(name, start_position=-len(word))

    def _get_vm_names(self) -> list:
        if self._vm_cache is None:
            try:
                vms = self.session.manager.find_vms_in_folder(None) or []
                self._vm_cache = [getattr(v, "name", str(v)) for v in vms]
            except Exception:
                _log.debug("VM name completion failed", exc_info=True)
                # Do not cache on failure so the next keypress retries
        return self._vm_cache or []

    def invalidate_cache(self) -> None:
        self._vm_cache = None
