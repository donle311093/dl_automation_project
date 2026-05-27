from __future__ import annotations

from typing import Any

from .._vmkit import ensure_vmkit_on_path
from ..base import PlatformPlugin, VMHandle

ensure_vmkit_on_path()


class VspherePlatform(PlatformPlugin):
    def __init__(
        self,
        host: str = "",
        user: str = "",
        password: str = "",
        port: int = 443,
        config_path: str | None = None,
    ) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._port = port
        self._config_path = config_path

    def _manager(self) -> Any:
        from vsphere.vsphere_manager import VSphereManager

        return VSphereManager(
            config_path=self._config_path,
            host=self._host or None,
            user=self._user or None,
            password=self._password or None,
            port=self._port,
        )

    def clone_and_snapshot(self, template: str, snapshot: str, clone_name: str, folder: str) -> VMHandle:
        from core.models import CloneConfigBuilder

        with self._manager() as mgr:
            template_vm = mgr.get_vm(template)
            config = (
                CloneConfigBuilder()
                .name(clone_name)
                .target_folder(folder)
                .snapshot(snapshot)
                .power_on(True)
                .build()
            )
            template_vm.clone_with_config(config)
        return VMHandle(vm_id=clone_name, template=template, platform="vsphere", folder_name=folder)

    def revert_snapshot(self, vm: VMHandle, snapshot: str) -> None:
        with self._manager() as mgr:
            clone = mgr.get_vm(vm.vm_id, folder_name=vm.folder_name or None)
            clone.revert_to_snapshot(snapshot)

    def teardown(self, vm: VMHandle) -> None:
        with self._manager() as mgr:
            # M4: normalise empty string to None, consistent with revert_snapshot
            mgr.delete_vm(vm.folder_name or None, vm.vm_id)
