from __future__ import annotations

from ..base import PlatformPlugin, VMHandle


class SshDirectPlatform(PlatformPlugin):
    """Platform for pre-provisioned Linux hosts — template is the host IP/hostname.

    No hypervisor is involved, so clone/revert/teardown are intentional no-ops.
    """

    def clone_and_snapshot(self, template: str, snapshot: str, clone_name: str, folder: str) -> VMHandle:
        return VMHandle(vm_id=template, template=template, platform="ssh_direct")

    def revert_snapshot(self, vm: VMHandle, snapshot: str) -> None:
        # Intentional no-op: pre-provisioned hosts have no hypervisor snapshot support.
        pass

    def teardown(self, vm: VMHandle) -> None:
        # Intentional no-op: nothing was provisioned, so nothing to clean up.
        pass
