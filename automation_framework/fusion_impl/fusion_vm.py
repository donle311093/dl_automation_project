"""FusionVMManager — VMware Fusion Pro implementation of IVMManager.

Design Pattern: Strategy (concrete strategy for VMware Fusion platform).
Uses the VMware Fusion Pro REST API (port 8697).

Requires:
    - VMware Fusion Pro 13+ on the target Mac
    - REST API enabled in Fusion preferences
    - VMware Tools installed in the guest (for execute_command)
"""

import os
import time
from core.interfaces import IVMManager
from core.models import CloneConfig


class FusionVMManager(IVMManager):
    """IVMManager implementation for VMware Fusion Pro virtual machines."""

    def __init__(self, client, vm_id: str, vm_name: str = None):
        """
        Args:
            client:  Connected FusionClient instance.
            vm_id:   Fusion VM ID (opaque string hash).
            vm_name: Display name of the VM (used in log messages).
        """
        self._client = client
        self._vm_id = vm_id
        self._vm_name = vm_name or vm_id
        self._guest_user: str | None = None
        self._guest_pass: str | None = None
        self._guest_os: str | None = None   # "windows" | "linux" | "macos"

    def _p(self, suffix: str = "") -> str:
        """Build path for this VM's API endpoints."""
        return f"/vms/{self._vm_id}{suffix}"

    def _label(self) -> str:
        return f"VM '{self._vm_name}'"

    # --- Power ---

    def get_power_status(self) -> str:
        try:
            result = self._client.get(self._p("/power"))
            state = result.get("power_state", "unknown")
            return {
                "poweredOn":  "Powered On",
                "poweredOff": "Powered Off",
                "suspended":  "Suspended",
                "paused":     "Suspended",
            }.get(state, f"Unknown ({state})")
        except Exception as e:
            return f"Unknown (error: {e})"

    def power_on(self) -> bool:
        try:
            self._client.put(self._p("/power"), "on")
            print(f"{self._label()} powered on.")
            return True
        except Exception as e:
            print(f"Failed to power on {self._label()}: {e}")
            return False

    def power_off(self) -> bool:
        try:
            self._client.put(self._p("/power"), "off")
            print(f"{self._label()} powered off (hard).")
            return True
        except Exception as e:
            print(f"Failed to power off {self._label()}: {e}")
            return False

    def suspend(self) -> bool:
        try:
            self._client.put(self._p("/power"), "suspend")
            print(f"{self._label()} suspended.")
            return True
        except Exception as e:
            print(f"Failed to suspend {self._label()}: {e}")
            return False

    def reboot(self) -> bool:
        """Graceful shutdown → power on."""
        try:
            self._client.put(self._p("/power"), "shutdown")
            print(f"{self._label()} shutdown sent, waiting...")
            time.sleep(5)
            self._client.put(self._p("/power"), "on")
            print(f"{self._label()} rebooted.")
            return True
        except Exception as e:
            print(f"Failed to reboot {self._label()}: {e}")
            return False

    def reset(self) -> bool:
        """Hard power off → power on."""
        try:
            self._client.put(self._p("/power"), "off")
            time.sleep(2)
            self._client.put(self._p("/power"), "on")
            print(f"{self._label()} hard reset.")
            return True
        except Exception as e:
            print(f"Failed to reset {self._label()}: {e}")
            return False

    # --- Info ---

    def get_vm_info(self) -> dict:
        try:
            detail = self._client.get(self._p(""))
            cpu_info = detail.get("cpu", {})

            ip = "N/A"
            try:
                ip_resp = self._client.get(self._p("/ip"))
                ip = ip_resp.get("ip", "N/A")
            except Exception:
                pass

            return {
                "name":      self._vm_name,
                "id":        self._vm_id,
                "path":      detail.get("path", "N/A"),
                "num_cpu":   cpu_info.get("processors", "N/A"),
                "memory_mb": detail.get("memory", "N/A"),
                "ip_address": ip,
                "power_state": self.get_power_status(),
            }
        except Exception as e:
            return {"name": self._vm_name, "id": self._vm_id, "error": str(e)}

    def get_guest_tools_status(self) -> str:
        try:
            result = self._client.get(self._p("/params/toolsinstallstate"))
            state = result.get("value", "unknown")
            return {
                "installed":       "VMware Tools: installed",
                "notInstalled":    "VMware Tools: not installed",
                "upgradeRequired": "VMware Tools: upgrade required",
                "unmanaged":       "VMware Tools: unmanaged",
            }.get(state, f"VMware Tools: {state}")
        except Exception as e:
            return f"VMware Tools: unknown ({e})"

    # --- Annotation ---

    def get_annotation(self) -> str:
        try:
            result = self._client.get(self._p("/params/annotation"))
            return result.get("value", "")
        except Exception:
            return ""

    def set_annotation(self, annotation: str) -> bool:
        try:
            self._client.put(self._p("/params"), {"name": "annotation", "value": annotation})
            return True
        except Exception as e:
            print(f"Failed to set annotation: {e}")
            return False

    # --- Snapshots ---

    def get_snapshots(self) -> list:
        try:
            result = self._client.get(self._p("/snapshots"))
            return result.get("snapshots", [])
        except Exception as e:
            print(f"Failed to get snapshots: {e}")
            return []

    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        try:
            self._client.post(self._p("/snapshots"), {"name": name, "description": description})
            print(f"Snapshot '{name}' created for {self._label()}.")
            return True
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return False

    def revert_to_current_snapshot(self) -> bool:
        snaps = self.get_snapshots()
        if not snaps:
            print("No snapshots found.")
            return False
        return self.revert_to_snapshot(snaps[-1].get("name", ""))

    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        snap_id = self._find_snapshot_id(snapshot_name)
        if snap_id is None:
            print(f"Snapshot '{snapshot_name}' not found.")
            return False
        try:
            self._client.put(self._p(f"/snapshots/{snap_id}"))
            print(f"Reverted {self._label()} to snapshot '{snapshot_name}'.")
            return True
        except Exception as e:
            print(f"Failed to revert: {e}")
            return False

    def delete_snapshot(self, snapshot_name: str) -> bool:
        snap_id = self._find_snapshot_id(snapshot_name)
        if snap_id is None:
            print(f"Snapshot '{snapshot_name}' not found.")
            return False
        try:
            self._client.delete(self._p(f"/snapshots/{snap_id}"))
            print(f"Snapshot '{snapshot_name}' deleted.")
            return True
        except Exception as e:
            print(f"Failed to delete snapshot: {e}")
            return False

    def _find_snapshot_id(self, name: str):
        for snap in self.get_snapshots():
            if snap.get("name") == name:
                return snap.get("id")
        return None

    # --- Guest operations ---

    def login(self, username: str, password: str) -> bool:
        """Store guest credentials and detect guest OS type for execute_command."""
        self._guest_user = username
        self._guest_pass = password

        # Detect guest OS from VMX param
        try:
            result = self._client.get(self._p("/params/guestOS"))
            guest_os = result.get("value", "").lower()
            if "windows" in guest_os:
                self._guest_os = "windows"
            elif "darwin" in guest_os:
                self._guest_os = "macos"
            else:
                self._guest_os = "linux"
        except Exception:
            self._guest_os = "linux"  # safe default

        print(f"Guest credentials stored for {self._label()} (OS: {self._guest_os}).")
        return True

    def execute_command(self, command: str, capture_output: bool = True) -> dict:
        """Execute a command inside the VM via VMware Tools guest operations.

        Requires VMware Tools installed and login() called first.
        Note: Output capture depends on Fusion API version; may return empty strings.
        """
        if not self._guest_user:
            raise RuntimeError("Must call login() first to set guest credentials.")

        # Wrap command in the appropriate shell
        if self._guest_os == "windows":
            program = "cmd.exe"
            arguments = f'/c "{command}"'
        else:
            program = "/bin/bash"
            arguments = f"-c '{command}'"

        try:
            result = self._client.post(self._p("/tools/run"), {
                "username": self._guest_user,
                "password": self._guest_pass,
                "program-path": program,
                "arguments": arguments,
            })
            return {
                "pid":       result.get("pid", -1),
                "exit_code": result.get("exit_code", result.get("exitCode", 0)),
                "stdout":    result.get("stdout", result.get("out-data", "")),
                "stderr":    result.get("stderr", result.get("err-data", "")),
            }
        except Exception as e:
            return {"pid": -1, "exit_code": -1, "stdout": "", "stderr": str(e)}

    # --- Clone ---

    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        """Full clone via Fusion REST API (POST /vms with parentId)."""
        try:
            payload = {"name": new_vm_name, "parentId": self._vm_id}
            if snapshot_name:
                snap_id = self._find_snapshot_id(snapshot_name)
                if snap_id:
                    payload["snapshotId"] = snap_id

            result = self._client.post("/vms", payload)
            new_id = result.get("id")
            print(f"Clone '{new_vm_name}' created (ID: {new_id}).")

            # Update CPU / memory
            config_update = {}
            if num_cpus:
                config_update["cpu"] = {"processors": num_cpus}
            if memory_mb:
                config_update["memory"] = memory_mb
            if config_update:
                self._client.put(f"/vms/{new_id}", config_update)
                print(f"Updated clone resources: {config_update}")

            if annotation:
                self._client.put(f"/vms/{new_id}/params", {"name": "annotation", "value": annotation})

            if power_on:
                self._client.put(f"/vms/{new_id}/power", "on")
                print(f"Clone '{new_vm_name}' started.")

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
