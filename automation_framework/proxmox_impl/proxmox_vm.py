"""ProxmoxVMManager — Proxmox implementation of IVMManager.

Design Pattern: Strategy (concrete strategy for Proxmox platform).
Uses ProxmoxTaskWaiter (Strategy) for async task management.
"""

import time
from core.interfaces import IVMManager
from core.models import CloneConfig
from proxmox_impl.task_waiter import ProxmoxTaskWaiter


class ProxmoxVMManager(IVMManager):
    """IVMManager implementation for Proxmox VE virtual machines.

    Uses the Proxmox REST API via proxmoxer.
    """

    def __init__(self, client, node: str, vmid: int):
        """
        Args:
            client: A connected ProxmoxClient instance.
            node:   Proxmox node name (e.g. 'pve').
            vmid:   VM ID (integer).
        """
        self._api = client.api
        self._node = node
        self._vmid = vmid
        self._vm_api = self._api.nodes(node).qemu(vmid)
        self._task_waiter = ProxmoxTaskWaiter(self._api, node)
        self._logged_in = False
        self._guest_user = None
        self._guest_pass = None

    def _wait(self, upid: str) -> bool:
        return self._task_waiter.wait(upid)

    # --- Power ---

    def get_power_status(self) -> str:
        status = self._vm_api.status.current.get()
        state = status.get("status", "unknown")
        mapping = {
            "running": "Powered On",
            "stopped": "Powered Off",
            "paused":  "Suspended",
        }
        return mapping.get(state, f"Unknown ({state})")

    def power_on(self) -> bool:
        try:
            upid = self._vm_api.status.start.post()
            print(f"Starting VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to power on VM {self._vmid}: {e}")
            return False

    def power_off(self) -> bool:
        try:
            upid = self._vm_api.status.stop.post()
            print(f"Stopping VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to power off VM {self._vmid}: {e}")
            return False

    def suspend(self) -> bool:
        try:
            upid = self._vm_api.status.suspend.post()
            print(f"Suspending VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to suspend VM {self._vmid}: {e}")
            return False

    def reboot(self) -> bool:
        try:
            upid = self._vm_api.status.reboot.post()
            print(f"Rebooting VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to reboot VM {self._vmid}: {e}")
            return False

    def reset(self) -> bool:
        try:
            upid = self._vm_api.status.reset.post()
            print(f"Resetting VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to reset VM {self._vmid}: {e}")
            return False

    # --- Info ---

    def get_vm_info(self) -> dict:
        status = self._vm_api.status.current.get()
        config = self._vm_api.config.get()

        ip = "N/A"
        try:
            agent_net = self._vm_api.agent("network-get-interfaces").get()
            for iface in agent_net.get("result", []):
                for addr in iface.get("ip-addresses", []):
                    if addr.get("ip-address-type") == "ipv4" and addr["ip-address"] != "127.0.0.1":
                        ip = addr["ip-address"]
                        break
                if ip != "N/A":
                    break
        except Exception:
            pass

        return {
            "name": config.get("name", f"VM-{self._vmid}"),
            "vmid": self._vmid,
            "node": self._node,
            "status": status.get("status", "unknown"),
            "num_cpu": config.get("cores", "N/A"),
            "sockets": config.get("sockets", 1),
            "memory_mb": config.get("memory", "N/A"),
            "ip_address": ip,
            "os_type": config.get("ostype", "N/A"),
            "disk": config.get("scsi0", config.get("virtio0", config.get("ide0", "N/A"))),
        }

    def get_guest_tools_status(self) -> str:
        config = self._vm_api.config.get()
        agent_enabled = config.get("agent", "0")
        if str(agent_enabled).split(",")[0] != "1":
            return "QEMU Guest Agent: not enabled in VM config"
        try:
            self._vm_api.agent.ping.post()
            return "QEMU Guest Agent: running"
        except Exception as e:
            return f"QEMU Guest Agent: enabled but not responding ({e})"

    # --- Annotation ---

    def get_annotation(self) -> str:
        config = self._vm_api.config.get()
        return config.get("description", "")

    def set_annotation(self, annotation: str) -> bool:
        try:
            self._vm_api.config.put(description=annotation)
            print(f"Annotation set for VM {self._vmid}.")
            return True
        except Exception as e:
            print(f"Failed to set annotation: {e}")
            return False

    # --- Snapshots ---

    def get_snapshots(self) -> list:
        try:
            snaps = self._vm_api.snapshot.get()
            return [s for s in snaps if s.get("name") != "current"]
        except Exception as e:
            print(f"Failed to list snapshots: {e}")
            return []

    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        try:
            params = {"snapname": name, "description": description}
            if memory:
                params["vmstate"] = 1
            upid = self._vm_api.snapshot.post(**params)
            print(f"Creating snapshot '{name}' for VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return False

    def revert_to_current_snapshot(self) -> bool:
        snaps = self.get_snapshots()
        if not snaps:
            print("No snapshots found.")
            return False
        return self.revert_to_snapshot(snaps[-1]["name"])

    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        try:
            upid = self._vm_api.snapshot(snapshot_name).rollback.post()
            print(f"Reverting VM {self._vmid} to snapshot '{snapshot_name}'...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to revert to snapshot: {e}")
            return False

    def delete_snapshot(self, snapshot_name: str) -> bool:
        try:
            upid = self._vm_api.snapshot(snapshot_name).delete()
            print(f"Deleting snapshot '{snapshot_name}' for VM {self._vmid}...")
            return self._wait(upid)
        except Exception as e:
            print(f"Failed to delete snapshot: {e}")
            return False

    # --- Guest operations ---

    def login(self, username: str, password: str) -> bool:
        try:
            self._vm_api.agent.ping.post()
            self._logged_in = True
            self._guest_user = username
            self._guest_pass = password
            print(f"QEMU Guest Agent is running on VM {self._vmid}. Ready for commands.")
            return True
        except Exception as e:
            print(f"QEMU Guest Agent not available on VM {self._vmid}: {e}")
            return False

    def execute_command(self, command: str, capture_output: bool = True) -> dict:
        if not self._logged_in:
            raise RuntimeError("Must login() first.")
        try:
            result = self._vm_api.agent.exec.post(command=command)
            pid = result.get("pid", -1)

            if not capture_output:
                return {"pid": pid, "exit_code": 0, "stdout": "", "stderr": ""}

            time.sleep(2)
            max_wait = 60
            while max_wait > 0:
                try:
                    status = self._vm_api.agent("exec-status").get(pid=pid)
                    if status.get("exited"):
                        return {
                            "pid": pid,
                            "exit_code": status.get("exitcode", -1),
                            "stdout": status.get("out-data", ""),
                            "stderr": status.get("err-data", ""),
                        }
                except Exception:
                    pass
                time.sleep(2)
                max_wait -= 2

            return {"pid": pid, "exit_code": -1, "stdout": "", "stderr": "Timeout waiting for command"}
        except Exception as e:
            return {"pid": -1, "exit_code": -1, "stdout": "", "stderr": str(e)}

    # --- Clone ---

    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        """Clone the VM.

        Args:
            target_folder_name: Target Proxmox node name (e.g. 'pve').
                                If None, clones on the same node.
        """
        try:
            new_vmid = self._api.cluster.nextid.get()
            target_node = target_folder_name or self._node

            params = {"newid": new_vmid, "name": new_vm_name, "target": target_node}
            if snapshot_name:
                params["snapname"] = snapshot_name
            if datastore_name:
                params["storage"] = datastore_name
            if annotation:
                params["description"] = annotation

            upid = self._vm_api.clone.post(**params)
            print(f"Cloning VM {self._vmid} -> {new_vm_name} (VMID: {new_vmid})...")
            if not self._wait(upid):
                return False

            new_vm_api = self._api.nodes(target_node).qemu(new_vmid)
            config_update = {}
            if num_cpus:
                config_update["cores"] = num_cpus
            if memory_mb:
                config_update["memory"] = memory_mb
            if config_update:
                new_vm_api.config.put(**config_update)
                print(f"Updated clone resources: {config_update}")

            if power_on:
                start_upid = new_vm_api.status.start.post()
                self._wait(start_upid)
                print(f"Clone '{new_vm_name}' started.")

            print(f"Clone '{new_vm_name}' (VMID: {new_vmid}) completed successfully.")
            return True
        except Exception as e:
            print(f"Clone failed: {e}")
            return False

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

    # --- Cleanup ---

    def disconnect(self):
        pass
