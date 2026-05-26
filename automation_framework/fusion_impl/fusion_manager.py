"""FusionManager — VMware Fusion Pro implementation of IHypervisorManager.

Design Pattern: Facade
- Provides a simple, unified interface over the VMware Fusion Pro REST API.
- Returns FusionVMManager instances (Strategy pattern).

Requires:
    - VMware Fusion Pro 13+ on the target Mac
    - REST API enabled: Fusion → Settings → Advanced → Enable REST API
    - Default API port: 8697
"""

import os
from core.interfaces import IHypervisorManager
from fusion_impl.fusion_client import FusionClient
from fusion_impl.fusion_vm import FusionVMManager


class FusionManager(IHypervisorManager):
    """VMware Fusion Pro implementation of IHypervisorManager.

    Design Pattern: Facade over the VMware Fusion Pro REST API.
    """

    def __init__(self, host: str, port: int = 8697,
                 username: str = "", password: str = "",
                 verify_ssl: bool = False):
        """
        Args:
            host:       IP or hostname of the Mac running VMware Fusion Pro.
            port:       REST API port (default 8697).
            username:   Fusion REST API username.
            password:   Fusion REST API password.
            verify_ssl: Whether to verify SSL certificates.
        """
        self._client = FusionClient(host, port, username, password, verify_ssl)

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

    # --- Internal helpers ---

    def _list_vms(self) -> list:
        """Return all VMs as a list of dicts with id, path, name."""
        raw = self._client.get("/vms")
        vms = []
        for entry in raw:
            vm_id = entry.get("id", "")
            path = entry.get("path", "")
            # Use the directory containing the .vmx file as the display name
            name = os.path.basename(os.path.dirname(path)) if path else vm_id
            vms.append({"id": vm_id, "path": path, "name": name})
        return vms

    def _find_vm(self, vm_name: str) -> dict | None:
        for vm in self._list_vms():
            if vm["name"] == vm_name:
                return vm
        return None

    # --- VM lookup ---

    def get_vm(self, vm_name: str, folder_name: str = None) -> FusionVMManager:
        """Return a FusionVMManager for a specific VM by name."""
        vm = self._find_vm(vm_name)
        if vm is None:
            raise ValueError(f"VM '{vm_name}' not found.")
        return FusionVMManager(self._client, vm["id"], vm_name=vm["name"])

    def find_vm_by_name(self, vm_name: str) -> list:
        """Find all VMs with the given name."""
        return [vm for vm in self._list_vms() if vm["name"] == vm_name]

    def find_vms_in_folder(self, folder_name: str) -> list:
        """Find VMs stored inside a directory path matching folder_name.

        In Fusion, 'folders' are just filesystem directories containing .vmx files.
        """
        return [vm for vm in self._list_vms() if folder_name in vm.get("path", "")]

    # --- Folder (filesystem directories, limited support) ---

    def find_folder(self, folder_name: str):
        """Return unique directory paths that match folder_name."""
        paths = {
            os.path.dirname(vm["path"])
            for vm in self._list_vms()
            if folder_name in vm.get("path", "")
        }
        return sorted(paths) if paths else None

    def delete_folder(self, folder_name: str) -> bool:
        raise NotImplementedError(
            "Folder deletion is not supported via VMware Fusion REST API. "
            "Delete VMs individually with delete_all_vms_in_folder()."
        )

    # --- VM deletion ---

    def delete_vm(self, folder_name: str, vm_name: str) -> bool:
        try:
            vm = self._find_vm(vm_name)
            if vm is None:
                print(f"VM '{vm_name}' not found.")
                return False
            # Power off first if running
            vm_mgr = FusionVMManager(self._client, vm["id"], vm_name=vm_name)
            if vm_mgr.get_power_status() == "Powered On":
                vm_mgr.power_off()
                import time; time.sleep(2)
            self._client.delete(f"/vms/{vm['id']}")
            print(f"VM '{vm_name}' deleted.")
            return True
        except Exception as e:
            print(f"Failed to delete VM '{vm_name}': {e}")
            return False

    def delete_all_vms_in_folder(self, folder_name: str) -> bool:
        vms = self.find_vms_in_folder(folder_name)
        return all(self.delete_vm(folder_name, vm["name"]) for vm in vms)

    # --- Info ---

    def get_all_vm_info(self, properties: list = None) -> list:
        result = []
        for vm in self._list_vms():
            try:
                detail = self._client.get(f"/vms/{vm['id']}")
                power = self._client.get(f"/vms/{vm['id']}/power")
                cpu_info = detail.get("cpu", {})
                result.append({
                    "name":      vm["name"],
                    "id":        vm["id"],
                    "path":      vm.get("path", ""),
                    "num_cpu":   cpu_info.get("processors", "N/A"),
                    "memory_mb": detail.get("memory", "N/A"),
                    "status":    power.get("power_state", "unknown"),
                })
            except Exception as e:
                result.append({"name": vm["name"], "id": vm["id"], "error": str(e)})
        return result

    def get_datastore_info(self) -> dict:
        """Not directly available via Fusion REST API. Returns empty dict."""
        return {}

    def find_datastore(self, datastore_name: str):
        """Not applicable to VMware Fusion."""
        return None
