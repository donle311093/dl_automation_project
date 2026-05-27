"""Core interfaces (Abstract Base Classes) for VM and Hypervisor management.

Design Pattern: Strategy / Template Method
- IVMManager defines the contract for managing a single VM.
- IHypervisorManager defines the contract for platform-level hypervisor management.
All concrete implementations (VSphere, Proxmox, Docker, SSH) implement these interfaces.
"""

from abc import ABC, abstractmethod


class IVMManager(ABC):
    """Interface for managing a single VM across different platforms.

    Implement this for each hypervisor (vSphere, Proxmox, etc.).
    """

    # --- Power ---

    @abstractmethod
    def get_power_status(self) -> str:
        """Return the power status of the VM."""
        ...

    @abstractmethod
    def power_on(self) -> bool:
        """Power on the VM."""
        ...

    @abstractmethod
    def power_off(self) -> bool:
        """Power off the VM."""
        ...

    @abstractmethod
    def suspend(self) -> bool:
        """Suspend the VM."""
        ...

    @abstractmethod
    def reboot(self) -> bool:
        """Reboot the VM (guest OS level)."""
        ...

    @abstractmethod
    def reset(self) -> bool:
        """Hard reset the VM."""
        ...

    # --- Info ---

    @abstractmethod
    def get_vm_info(self) -> dict:
        """Return a dictionary with basic information about the VM."""
        ...

    @abstractmethod
    def get_guest_tools_status(self) -> str:
        """Return the guest tools/agent status (e.g. VMware Tools, QEMU Guest Agent)."""
        ...

    # --- Annotation ---

    @abstractmethod
    def get_annotation(self) -> str:
        """Return the annotation/note of the VM."""
        ...

    @abstractmethod
    def set_annotation(self, annotation: str) -> bool:
        """Set the annotation/note of the VM."""
        ...

    # --- Snapshots ---

    @abstractmethod
    def get_snapshots(self) -> list:
        """Return a list of all snapshots."""
        ...

    @abstractmethod
    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        """Create a new snapshot."""
        ...

    @abstractmethod
    def revert_to_current_snapshot(self) -> bool:
        """Revert to the current/latest snapshot."""
        ...

    @abstractmethod
    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        """Revert to a specific snapshot by name."""
        ...

    @abstractmethod
    def delete_snapshot(self, snapshot_name: str) -> bool:
        """Delete a specific snapshot by name."""
        ...

    # --- Guest operations ---

    @abstractmethod
    def login(self, username: str, password: str) -> bool:
        """Authenticate to the guest OS."""
        ...

    @abstractmethod
    def execute_command(self, command: str, capture_output: bool = True) -> dict:
        """Execute a command inside the guest OS.

        Returns:
            A dict with keys: pid, exit_code, stdout, stderr.
        """
        ...

    # --- Clone ---

    @abstractmethod
    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        """Clone the VM to a target folder."""
        ...


class IHypervisorManager(ABC):
    """Interface for platform-level hypervisor management.

    Implement this for each hypervisor (vSphere, Proxmox, etc.).
    """

    @abstractmethod
    def connect(self):
        """Connect to the hypervisor."""
        ...

    @abstractmethod
    def disconnect(self):
        """Disconnect from the hypervisor."""
        ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # --- VM lookup ---

    @abstractmethod
    def get_vm(self, vm_name: str, folder_name: str = None) -> IVMManager:
        """Return a VM manager for a specific VM."""
        ...

    @abstractmethod
    def find_vm_by_name(self, vm_name: str) -> list:
        """Find all VMs with the given name."""
        ...

    @abstractmethod
    def find_vms_in_folder(self, folder_name: str) -> list:
        """Find all VMs inside a specific folder/group."""
        ...

    # --- Folder/Group ---

    @abstractmethod
    def find_folder(self, folder_name: str):
        """Find a folder/group by name."""
        ...

    @abstractmethod
    def delete_folder(self, folder_name: str) -> bool:
        """Delete a folder/group by name."""
        ...

    # --- VM deletion ---

    @abstractmethod
    def delete_vm(self, folder_name: str, vm_name: str) -> bool:
        """Delete a specific VM in a folder."""
        ...

    @abstractmethod
    def delete_all_vms_in_folder(self, folder_name: str) -> bool:
        """Delete all VMs inside a folder."""
        ...

    # --- Info ---

    @abstractmethod
    def get_all_vm_info(self, properties: list = None) -> list:
        """Return info for all VMs."""
        ...

    @abstractmethod
    def get_datastore_info(self) -> dict:
        """Return storage/datastore info."""
        ...

    @abstractmethod
    def find_datastore(self, datastore_name: str):
        """Find a datastore/storage by name."""
        ...
