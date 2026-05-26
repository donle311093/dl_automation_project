"""VSphereManager — vSphere implementation of IHypervisorManager.

Design Pattern: Facade
- Provides a simple, unified interface over the complex vSphere/pyVmomi API.
- Delegates to focused vsphere.* modules for each operation.
"""

from vsphere.vcenter_client import VCenterClient
from vsphere.find_folder import find_folder
from vsphere.find_vm import find_all_vm_inside_folder, find_all_vm_by_name
from vsphere.delete_folder import delete_folder
from vsphere.delete_vm import delete_vm_inside_folder, delete_all_vm_inside_folder, delete_all_vm_by_name
from vsphere.vm_info import get_all_vm_info
from vsphere.datastore_info import get_datastore_info
from vsphere.datastore import find_datastore_by_name
from vsphere.vsphere_vm import VSphereVMManager
from core.interfaces import IHypervisorManager


class VSphereManager(IHypervisorManager):
    """vSphere implementation of IHypervisorManager.

    Design Pattern: Facade over the vSphere/pyVmomi subsystem.
    """

    def __init__(self, config_path: str = None, host: str = None, user: str = None,
                 password: str = None, port: int = 443, ssl_verify: bool = False):
        self._client = VCenterClient(
            config_path=config_path,
            host=host, user=user, password=password,
            port=port, ssl_verify=ssl_verify,
        )

    def connect(self):
        self._client.connect()
        return self

    def disconnect(self):
        self._client.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # --- VM lookup ---

    def get_vm(self, vm_name: str, folder_name: str = None) -> VSphereVMManager:
        """Return a VSphereVMManager for a specific VM."""
        return VSphereVMManager(self._client, vm_name, folder_name)

    def find_vm_by_name(self, vm_name: str) -> list:
        """Find all VMs with the given name across all folders."""
        return find_all_vm_by_name(self._client, vm_name)

    def find_vms_in_folder(self, folder_name: str) -> list:
        """Find all VMs inside a specific folder."""
        return find_all_vm_inside_folder(self._client, folder_name)

    # --- Folder ---

    def find_folder(self, folder_name: str):
        """Find a folder by name."""
        return find_folder(self._client, folder_name)

    def delete_folder(self, folder_name: str) -> bool:
        """Delete a folder by name."""
        return delete_folder(self._client, folder_name)

    # --- VM deletion ---

    def delete_vm(self, folder_name: str, vm_name: str) -> bool:
        """Delete a specific VM in a folder."""
        return delete_vm_inside_folder(self._client, folder_name, vm_name)

    def delete_all_vms_in_folder(self, folder_name: str) -> bool:
        """Delete all VMs inside a folder."""
        return delete_all_vm_inside_folder(self._client, folder_name)

    def delete_all_vms_by_name(self, vm_name: str) -> bool:
        """Delete all VMs with the given name across all folders."""
        return delete_all_vm_by_name(self._client, vm_name)

    # --- Info ---

    def get_all_vm_info(self, properties: list = None) -> list:
        """Collect properties for all VMs using the PropertyCollector."""
        return get_all_vm_info(self._client, properties)

    def get_datastore_info(self) -> dict:
        """Return datastore info for all ESXi hosts."""
        return get_datastore_info(self._client)

    def find_datastore(self, datastore_name: str):
        """Find a datastore by name."""
        return find_datastore_by_name(self._client, datastore_name)
