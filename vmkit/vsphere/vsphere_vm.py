"""VSphereVMManager — vSphere implementation of IVMManager.

Design Pattern: Strategy (concrete strategy for vSphere platform).
"""

from vsphere.find_vm import find_vm_inside_folder, find_all_vm_by_name
from vsphere.power_status import PowerManager
from vsphere.annotation import get_annotation, set_annotation
from vsphere.snapshot import SnapshotManager
from vsphere.vm_info import get_vm_info, get_vmtools_status
from vsphere.login import login_to_vm
from vsphere.execute_command import execute_command
from vsphere.clone_vm import clone_vm
from core.interfaces import IVMManager
from core.models import CloneConfig


class VSphereVMManager(IVMManager):
    """IVMManager implementation for VMware vSphere virtual machines."""

    def __init__(self, client, vm_name: str, folder_name: str = None):
        self.client = client
        self.user_login = None
        self.pass_login = None

        if folder_name:
            self.vm = find_vm_inside_folder(client, folder_name, vm_name)
        else:
            results = find_all_vm_by_name(client, vm_name)
            if len(results) > 1:
                names = ", ".join(
                    r["folder"].name if r.get("folder") else "(unknown)" for r in results
                )
                raise ValueError(
                    f"VM '{vm_name}' found in multiple folders: {names}. "
                    f"Use --folder to specify one."
                )
            self.vm = results[0]["vm"] if results else None

        self._power = PowerManager(self.vm) if self.vm else None
        self._snapshot = SnapshotManager(self.vm) if self.vm else None

    def _require_vm(self):
        if not self.vm:
            raise ValueError("VM not found.")

    # --- Power ---

    def get_power_status(self) -> str:
        self._require_vm()
        return self._power.status()

    def power_on(self) -> bool:
        self._require_vm()
        return self._power.power_on()

    def power_off(self) -> bool:
        self._require_vm()
        return self._power.power_off()

    def suspend(self) -> bool:
        self._require_vm()
        return self._power.suspend()

    def reboot(self) -> bool:
        self._require_vm()
        return self._power.reboot()

    def reset(self) -> bool:
        self._require_vm()
        return self._power.reset()

    # --- Annotation ---

    def get_annotation(self) -> str:
        self._require_vm()
        return get_annotation(self.vm)

    def set_annotation(self, annotation: str) -> bool:
        self._require_vm()
        return set_annotation(self.vm, annotation)

    # --- Snapshots ---

    def get_snapshots(self) -> list:
        self._require_vm()
        return self._snapshot.list_all_snapshots()

    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        self._require_vm()
        return self._snapshot.create_snapshot(name, description, memory, quiesce)

    def revert_to_current_snapshot(self) -> bool:
        self._require_vm()
        return self._snapshot.revert_to_current_snapshot()

    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        self._require_vm()
        return self._snapshot.revert_to_snapshot(snapshot_name)

    def delete_snapshot(self, snapshot_name: str) -> bool:
        self._require_vm()
        return self._snapshot.delete_snapshot(snapshot_name)

    # --- Info ---

    def get_vm_info(self) -> dict:
        self._require_vm()
        return get_vm_info(self.vm)

    def get_guest_tools_status(self) -> str:
        self._require_vm()
        return get_vmtools_status(self.vm)

    # --- Guest operations ---

    def login(self, username: str, password: str) -> bool:
        self._require_vm()
        self.user_login = username
        self.pass_login = password
        return login_to_vm(self.client, self.vm, username, password)

    def execute_command(self, command: str, capture_output: bool = True, verbose: bool = False) -> dict:
        self._require_vm()
        if not self.user_login or not self.pass_login:
            raise ValueError("Must log in before executing commands.")
        return execute_command(
            self.client, self.vm,
            self.user_login, self.pass_login,
            command, capture_output, verbose=verbose,
        )

    # --- Clone ---

    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        self._require_vm()
        return clone_vm(
            self.client, self.vm,
            target_folder_name, new_vm_name,
            snapshot_name, datastore_name, annotation,
            num_cpus, memory_mb, power_on,
        )

    def clone_with_config(self, config: CloneConfig) -> bool:
        """Clone the VM using a CloneConfig object (Builder Pattern integration)."""
        return self.clone(
            target_folder_name=config.target_folder_name,
            new_vm_name=config.new_vm_name,
            snapshot_name=config.snapshot_name,
            datastore_name=config.datastore_name,
            annotation=config.annotation,
            num_cpus=config.num_cpus,
            memory_mb=config.memory_mb,
            power_on=config.power_on,
        )
