from __future__ import annotations

from typing import Any

from .._vmkit import ensure_vmkit_on_path
from ..base import CommandResult, ExecutorPlugin, VMHandle

ensure_vmkit_on_path()

try:
    from ssh.ssh_vm import SSHVMManager
except ImportError:
    SSHVMManager = None  # type: ignore[assignment]


class SshExecutor(ExecutorPlugin):
    """Runs shell commands on Linux VMs via SSH (paramiko)."""

    def __init__(self, ssh_user: str, ssh_password: str, port: int = 22) -> None:
        self._user = ssh_user
        self._password = ssh_password
        self._port = port

    def run(self, vm: VMHandle, command: str) -> CommandResult:
        if SSHVMManager is None:
            raise RuntimeError(
                "vmkit SSH not available: install paramiko and add vmkit/ to sys.path"
            )
        with SSHVMManager(vm.vm_id, port=self._port) as ssh:
            ssh.login(self._user, self._password)
            result: dict[str, Any] = ssh.execute_command(command)
            return CommandResult(
                stdout=result.get("stdout", ""),
                exit_code=result.get("exit_code", 0),
                stderr=result.get("stderr", ""),
            )
