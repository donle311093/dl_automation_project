from __future__ import annotations

import base64
from typing import Any

from .._vmkit import ensure_vmkit_on_path
from ..base import CommandResult, ExecutorPlugin, VMHandle

ensure_vmkit_on_path()

try:
    from vsphere.vsphere_manager import VSphereManager
except ImportError:
    VSphereManager = None  # type: ignore[assignment]


def _encode_command(command: str) -> str:
    """Wrap command using PowerShell -EncodedCommand to prevent shell injection."""
    encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    return f"powershell -NonInteractive -EncodedCommand {encoded}"


class PowershellExecutor(ExecutorPlugin):
    """Runs PowerShell commands on Windows VMs via vSphere GuestOps."""

    def __init__(
        self,
        guest_user: str,
        guest_password: str,
        vcenter_host: str = "",
        vcenter_user: str = "",
        vcenter_password: str = "",
        vcenter_port: int = 443,
        vcenter_config_path: str | None = None,
    ) -> None:
        self._guest_user = guest_user
        self._guest_password = guest_password
        self._vcenter_host = vcenter_host
        self._vcenter_user = vcenter_user
        self._vcenter_password = vcenter_password
        self._vcenter_port = vcenter_port
        self._vcenter_config_path = vcenter_config_path

    def run(self, vm: VMHandle, command: str) -> CommandResult:
        if VSphereManager is None:
            raise RuntimeError(
                "vmkit vsphere not available: install pyvmomi and add vmkit/ to sys.path"
            )
        with VSphereManager(
            config_path=self._vcenter_config_path,
            host=self._vcenter_host or None,
            user=self._vcenter_user or None,
            password=self._vcenter_password or None,
            port=self._vcenter_port,
        ) as mgr:
            vm_obj = mgr.get_vm(vm.vm_id, folder_name=vm.folder_name or None)
            vm_obj.login(self._guest_user, self._guest_password)
            result: dict[str, Any] = vm_obj.execute_command(_encode_command(command))
            return CommandResult(
                stdout=result.get("stdout", ""),
                exit_code=result.get("exit_code", 0),
                stderr=result.get("stderr", ""),
            )
