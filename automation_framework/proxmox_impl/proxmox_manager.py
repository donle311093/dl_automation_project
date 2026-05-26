"""ProxmoxManager — Proxmox VE implementation of IHypervisorManager.

Design Pattern: Facade + Factory integration
- Facade over the Proxmox REST API.
- Returns ProxmoxVMManager instances (Strategy pattern).
- Uses ProxmoxTaskWaiter (Strategy) for async task management.
"""

from core.interfaces import IHypervisorManager
from proxmox_impl.proxmox_client import ProxmoxClient
from proxmox_impl.proxmox_vm import ProxmoxVMManager
from proxmox_impl.task_waiter import ProxmoxTaskWaiter


class ProxmoxManager(IHypervisorManager):
    """Proxmox VE implementation of IHypervisorManager.

    Design Pattern: Facade over the Proxmox REST API subsystem.
    """

    def __init__(self, host: str, user: str, password: str, port: int = 8006, verify_ssl: bool = False):
        self._client = ProxmoxClient(host, user, password, port, verify_ssl)

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

    @property
    def _api(self):
        return self._client.api

    def _get_nodes(self) -> list:
        return [n["node"] for n in self._api.nodes.get()]

    def _find_vm(self, vm_name: str, node_name: str = None):
        """Return (node, vmid) for the first matching VM, or (None, None)."""
        nodes = [node_name] if node_name else self._get_nodes()
        for node in nodes:
            try:
                for vm in self._api.nodes(node).qemu.get():
                    if vm.get("name") == vm_name:
                        return node, vm["vmid"]
            except Exception:
                continue
        return None, None

    def _delete_vm_by_id(self, node: str, vmid: int) -> bool:
        """Stop (if running) and delete a VM by node/VMID."""
        try:
            vm_api = self._api.nodes(node).qemu(vmid)
            status = vm_api.status.current.get()
            waiter = ProxmoxTaskWaiter(self._api, node)
            if status.get("status") == "running":
                waiter.wait(vm_api.status.stop.post())
            waiter.wait(vm_api.delete())
            print(f"VM {vmid} deleted on node '{node}'.")
            return True
        except Exception as e:
            print(f"Failed to delete VM {vmid}: {e}")
            return False

    # --- VM lookup ---

    def get_vm(self, vm_name: str, folder_name: str = None) -> ProxmoxVMManager:
        """Return a ProxmoxVMManager for a VM by name.

        Args:
            vm_name:     VM name to find.
            folder_name: Proxmox node name (optional, auto-detected if None).
        """
        node, vmid = self._find_vm(vm_name, node_name=folder_name)
        if node is None:
            raise ValueError(f"VM '{vm_name}' not found.")
        return ProxmoxVMManager(self._client, node, vmid)

    def find_vm_by_name(self, vm_name: str) -> list:
        """Find all VMs with the given name across all nodes."""
        results = []
        for node in self._get_nodes():
            for vm in self._api.nodes(node).qemu.get():
                if vm.get("name") == vm_name:
                    results.append({
                        "name": vm.get("name"),
                        "vmid": vm.get("vmid"),
                        "node": node,
                        "status": vm.get("status"),
                    })
        return results

    def find_vms_in_folder(self, folder_name: str) -> list:
        """Find all VMs on a specific Proxmox node."""
        vms = []
        try:
            for vm in self._api.nodes(folder_name).qemu.get():
                vms.append({
                    "name": vm.get("name"),
                    "vmid": vm.get("vmid"),
                    "node": folder_name,
                    "status": vm.get("status"),
                })
        except Exception as e:
            print(f"Failed to list VMs on node '{folder_name}': {e}")
        return vms

    # --- Folder/Group (Proxmox: pools) ---

    def find_folder(self, folder_name: str):
        """Find a Proxmox resource pool by name."""
        try:
            for pool in self._api.pools.get():
                if pool.get("poolid") == folder_name:
                    return pool
        except Exception as e:
            print(f"Failed to find pool '{folder_name}': {e}")
        return None

    def delete_folder(self, folder_name: str) -> bool:
        """Delete a Proxmox resource pool."""
        try:
            self._api.pools(folder_name).delete()
            print(f"Pool '{folder_name}' deleted.")
            return True
        except Exception as e:
            print(f"Failed to delete pool '{folder_name}': {e}")
            return False

    # --- VM deletion ---

    def delete_vm(self, folder_name: str, vm_name: str) -> bool:
        node, vmid = self._find_vm(vm_name, node_name=folder_name)
        if node is None:
            print(f"VM '{vm_name}' not found on node '{folder_name}'.")
            return False
        return self._delete_vm_by_id(node, vmid)

    def delete_all_vms_in_folder(self, folder_name: str) -> bool:
        vms = self.find_vms_in_folder(folder_name)
        return all(self._delete_vm_by_id(vm["node"], vm["vmid"]) for vm in vms)

    # --- Info ---

    def get_all_vm_info(self, properties: list = None) -> list:
        all_vms = []
        for node in self._get_nodes():
            for vm in self._api.nodes(node).qemu.get():
                all_vms.append({
                    "name": vm.get("name"),
                    "vmid": vm.get("vmid"),
                    "node": node,
                    "status": vm.get("status"),
                    "mem": vm.get("maxmem", 0),
                    "cpu": vm.get("cpus", 0),
                    "uptime": vm.get("uptime", 0),
                })
        return all_vms

    def get_datastore_info(self) -> dict:
        storage_info = {}
        for node in self._get_nodes():
            storages = self._api.nodes(node).storage.get()
            storage_info[node] = [
                {
                    "storage": s.get("storage"),
                    "type": s.get("type"),
                    "total": s.get("total", 0),
                    "used": s.get("used", 0),
                    "avail": s.get("avail", 0),
                    "active": s.get("active", 0),
                    "content": s.get("content", ""),
                }
                for s in storages
            ]
        return storage_info

    def find_datastore(self, datastore_name: str):
        for node in self._get_nodes():
            for s in self._api.nodes(node).storage.get():
                if s.get("storage") == datastore_name:
                    return {"node": node, **s}
        return None
