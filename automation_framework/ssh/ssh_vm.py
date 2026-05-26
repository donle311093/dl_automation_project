"""SSHVMManager — SSH implementation of IVMManager.

Design Pattern: Adapter
- Adapts the SSH protocol to the uniform IVMManager interface.
- Direct SSH access to any machine; treats the remote machine as a "VM".

Supports:    login, execute_command, get_vm_info, power_off/reboot.
Unsupported: snapshot, clone, suspend, annotations (requires a hypervisor).
"""

from core.interfaces import IVMManager
from ssh.ssh_client import SSHClient


class SSHVMManager(IVMManager):
    """IVMManager implementation using SSH for direct machine access."""

    def __init__(self, host: str, port: int = 22):
        self.host = host
        self.port = port
        self._ssh = SSHClient(host, port)
        self._os_type = None  # 'linux', 'macos', or 'windows'

    def _require_login(self):
        if not self._ssh.is_connected:
            raise RuntimeError("Not logged in. Call login() first.")

    def _detect_os(self):
        result = self._ssh.execute("uname -s")
        if result["exit_code"] == 0:
            os_name = result["stdout"].strip().lower()
            self._os_type = "macos" if "darwin" in os_name else "linux"
        else:
            self._os_type = "windows"

    # --- Power ---

    def get_power_status(self) -> str:
        if self._ssh.is_connected:
            return "Powered On"
        return "Unknown (SSH unreachable)"

    def power_on(self) -> bool:
        print(f"Cannot power on {self.host} via SSH. Use Wake-on-LAN or manual start.")
        return False

    def power_off(self) -> bool:
        self._require_login()
        cmd = "shutdown /s /t 0" if self._os_type == "windows" else "sudo shutdown -h now"
        result = self._ssh.execute(cmd)
        if result["exit_code"] == 0:
            print(f"Shutdown command sent to {self.host}.")
            return True
        print(f"Shutdown failed: {result['stderr']}")
        return False

    def suspend(self) -> bool:
        raise NotImplementedError("Suspend is not supported via SSH.")

    def reboot(self) -> bool:
        self._require_login()
        cmd = "shutdown /r /t 0" if self._os_type == "windows" else "sudo reboot"
        result = self._ssh.execute(cmd)
        if result["exit_code"] == 0:
            print(f"Reboot command sent to {self.host}.")
            return True
        print(f"Reboot failed: {result['stderr']}")
        return False

    def reset(self) -> bool:
        print("Hard reset not available via SSH. Using reboot instead.")
        return self.reboot()

    # --- Info ---

    def get_vm_info(self) -> dict:
        self._require_login()
        info = {"host": self.host, "os_type": self._os_type}

        if self._os_type == "windows":
            r = self._ssh.execute("hostname")
            info["hostname"] = r["stdout"].strip() if r["exit_code"] == 0 else "N/A"

            r = self._ssh.execute("wmic cpu get NumberOfCores /value")
            for line in r["stdout"].splitlines():
                if "NumberOfCores" in line:
                    info["num_cpu"] = line.split("=")[1].strip()
                    break

            r = self._ssh.execute("wmic OS get TotalVisibleMemorySize /value")
            for line in r["stdout"].splitlines():
                if "TotalVisibleMemorySize" in line:
                    info["memory_mb"] = int(line.split("=")[1].strip()) // 1024
                    break

            info["ip_address"] = self.host
        else:
            r = self._ssh.execute("hostname")
            info["hostname"] = r["stdout"].strip() if r["exit_code"] == 0 else "N/A"

            r = self._ssh.execute("nproc")
            info["num_cpu"] = r["stdout"].strip() if r["exit_code"] == 0 else "N/A"

            r = self._ssh.execute("free -m | awk '/Mem:/ {print $2}'")
            info["memory_mb"] = r["stdout"].strip() if r["exit_code"] == 0 else "N/A"

            r = self._ssh.execute("cat /etc/os-release 2>/dev/null | head -1")
            info["os_info"] = r["stdout"].strip() if r["exit_code"] == 0 else "N/A"

            info["ip_address"] = self.host

        return info

    def get_guest_tools_status(self) -> str:
        return "SSH Connected" if self._ssh.is_connected else "SSH Disconnected"

    # --- Annotation ---

    def get_annotation(self) -> str:
        raise NotImplementedError("Annotations are not supported via SSH.")

    def set_annotation(self, annotation: str) -> bool:
        raise NotImplementedError("Annotations are not supported via SSH.")

    # --- Snapshots ---

    def get_snapshots(self) -> list:
        raise NotImplementedError("Snapshots are not supported via SSH.")

    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        raise NotImplementedError("Snapshots are not supported via SSH.")

    def revert_to_current_snapshot(self) -> bool:
        raise NotImplementedError("Snapshots are not supported via SSH.")

    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        raise NotImplementedError("Snapshots are not supported via SSH.")

    def delete_snapshot(self, snapshot_name: str) -> bool:
        raise NotImplementedError("Snapshots are not supported via SSH.")

    # --- Guest operations ---

    def login(self, username: str, password: str) -> bool:
        try:
            self._ssh.connect(username, password)
            self._detect_os()
            print(f"SSH login to {self.host} successful (OS: {self._os_type}).")
            return True
        except Exception as e:
            print(f"SSH login to {self.host} failed: {e}")
            return False

    def execute_command(self, command: str, capture_output: bool = True) -> dict:
        self._require_login()
        result = self._ssh.execute(command)
        result["pid"] = -1
        return result

    # --- Clone ---

    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        raise NotImplementedError("Clone is not supported via SSH.")

    # --- Cleanup ---

    def disconnect(self):
        self._ssh.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
