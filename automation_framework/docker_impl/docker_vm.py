"""DockerVMManager — Docker implementation of IVMManager.

Design Pattern: Adapter
- Adapts the Docker SDK container API to the uniform IVMManager interface.
- Treats a Docker container as a "VM": start/stop → power on/off,
  pause/unpause → suspend, docker commit → snapshot, docker run → clone.
"""

from docker_impl import DockerClient
from core.interfaces import IVMManager
from core.models import CloneConfig


class DockerVMManager(IVMManager):
    """IVMManager implementation for Docker containers.

    Treats a Docker container like a VM.

    Supports: login (connect), execute_command, get_vm_info, power operations,
              snapshots (via docker commit/tag).
    Not supported: suspend (pause/unpause used instead), clone (partial via commit),
                   annotations.
    """

    def __init__(self, container_name_or_id: str, base_url: str = None):
        """
        Args:
            container_name_or_id: Name or ID of the Docker container.
            base_url:             Docker daemon URL. None = local socket.
        """
        self._docker = None
        self._container_name = container_name_or_id
        self._container = None
        self._logged_in = False

        try:
            self._docker = DockerClient(base_url)
            self._container = self._docker.client.containers.get(container_name_or_id)
        except Exception as e:
            print(f"Failed to connect to Docker or find container '{container_name_or_id}': {e}")

    def _require_container(self):
        if not self._docker:
            raise ValueError(f"Docker daemon unreachable for container '{self._container_name}'.")
        if not self._container:
            raise ValueError(f"Container '{self._container_name}' not found.")

    def _refresh(self):
        if self._container:
            self._container.reload()

    # --- Power ---

    def get_power_status(self) -> str:
        self._require_container()
        self._refresh()
        mapping = {
            "running":    "Powered On",
            "exited":     "Powered Off",
            "paused":     "Suspended",
            "created":    "Powered Off",
            "restarting": "Rebooting",
        }
        return mapping.get(self._container.status, f"Unknown ({self._container.status})")

    def power_on(self) -> bool:
        self._require_container()
        try:
            self._container.start()
            print(f"Container '{self._container_name}' started.")
            return True
        except Exception as e:
            print(f"Failed to start container: {e}")
            return False

    def power_off(self) -> bool:
        self._require_container()
        try:
            self._container.stop()
            print(f"Container '{self._container_name}' stopped.")
            return True
        except Exception as e:
            print(f"Failed to stop container: {e}")
            return False

    def suspend(self) -> bool:
        """Pause the container (Docker equivalent of suspend)."""
        self._require_container()
        try:
            self._container.pause()
            print(f"Container '{self._container_name}' paused.")
            return True
        except Exception as e:
            print(f"Failed to pause container: {e}")
            return False

    def reboot(self) -> bool:
        self._require_container()
        try:
            self._container.restart()
            print(f"Container '{self._container_name}' restarted.")
            return True
        except Exception as e:
            print(f"Failed to restart container: {e}")
            return False

    def reset(self) -> bool:
        """Kill and re-start the container (hard reset)."""
        self._require_container()
        try:
            self._container.kill()
            self._container.start()
            print(f"Container '{self._container_name}' killed and restarted.")
            return True
        except Exception as e:
            print(f"Failed to reset container: {e}")
            return False

    # --- Info ---

    def get_vm_info(self) -> dict:
        self._require_container()
        self._refresh()
        attrs = self._container.attrs
        config = attrs.get("Config", {})
        host_config = attrs.get("HostConfig", {})
        network = attrs.get("NetworkSettings", {})

        ip = "N/A"
        networks = network.get("Networks", {})
        if networks:
            first_net = next(iter(networks.values()))
            ip = first_net.get("IPAddress", "N/A")

        nano_cpus = host_config.get("NanoCpus", 0)
        memory_bytes = host_config.get("Memory", 0)

        return {
            "name":      self._container.name,
            "id":        self._container.short_id,
            "status":    self._container.status,
            "image":     config.get("Image", "N/A"),
            "ip_address": ip,
            "num_cpu":   nano_cpus / 1e9 if nano_cpus else "unlimited",
            "memory_mb": memory_bytes // (1024 * 1024) if memory_bytes else "unlimited",
            "platform":  attrs.get("Platform", "N/A"),
        }

    def get_guest_tools_status(self) -> str:
        self._require_container()
        self._refresh()
        return f"Container status: {self._container.status}"

    # --- Annotation ---

    def get_annotation(self) -> str:
        self._require_container()
        labels = self._container.labels or {}
        return labels.get("annotation", "")

    def set_annotation(self, annotation: str) -> bool:
        raise NotImplementedError(
            "Cannot set annotation on a running container. "
            "Set labels at container creation time."
        )

    # --- Snapshots (via docker commit) ---

    def get_snapshots(self) -> list:
        self._require_container()
        images = self._docker.client.images.list(name=f"{self._container_name}_snapshot")
        return [
            {"name": tag, "id": img.short_id}
            for img in images
            for tag in img.tags
        ]

    def create_snapshot(self, name: str, description: str = "", memory: bool = False, quiesce: bool = False) -> bool:
        self._require_container()
        try:
            tag = name.replace(" ", "_").lower()
            self._container.commit(
                repository=f"{self._container_name}_snapshot",
                tag=tag,
                message=description,
            )
            print(f"Snapshot '{name}' created for container '{self._container_name}'.")
            return True
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return False

    def revert_to_current_snapshot(self) -> bool:
        raise NotImplementedError(
            "Docker does not support reverting to a snapshot. "
            "Create a new container from the committed image instead."
        )

    def revert_to_snapshot(self, snapshot_name: str) -> bool:
        raise NotImplementedError(
            "Docker does not support reverting to a snapshot. "
            "Create a new container from the committed image instead."
        )

    def delete_snapshot(self, snapshot_name: str) -> bool:
        self._require_container()
        try:
            tag = snapshot_name.replace(" ", "_").lower()
            self._docker.client.images.remove(f"{self._container_name}_snapshot:{tag}")
            print(f"Snapshot '{snapshot_name}' deleted.")
            return True
        except Exception as e:
            print(f"Failed to delete snapshot: {e}")
            return False

    # --- Guest operations ---

    def login(self, username: str, password: str) -> bool:
        self._require_container()
        self._refresh()
        if self._container.status != "running":
            print(f"Container '{self._container_name}' is not running. Starting...")
            self.power_on()
            self._refresh()
        self._logged_in = True
        print(f"Connected to container '{self._container_name}'.")
        return True

    def execute_command(self, command: str, capture_output: bool = True) -> dict:
        self._require_container()
        try:
            result = self._container.exec_run(command, demux=True)
            stdout = result.output[0].decode("utf-8", errors="replace") if result.output[0] else ""
            stderr = result.output[1].decode("utf-8", errors="replace") if result.output[1] else ""
            return {
                "pid":       -1,
                "exit_code": result.exit_code,
                "stdout":    stdout,
                "stderr":    stderr,
            }
        except Exception as e:
            return {"pid": -1, "exit_code": -1, "stdout": "", "stderr": str(e)}

    # --- Clone ---

    def clone(self, target_folder_name: str, new_vm_name: str,
              snapshot_name: str = None, datastore_name: str = None,
              annotation: str = None, num_cpus: int = None,
              memory_mb: int = None, power_on: bool = False) -> bool:
        """Clone by committing the container and creating a new one from the image."""
        self._require_container()
        try:
            image = self._container.commit(repository=new_vm_name, tag="latest")
            print(f"Committed container as image '{new_vm_name}:latest'.")

            kwargs = {"name": new_vm_name, "detach": True}
            if num_cpus:
                kwargs["nano_cpus"] = int(num_cpus * 1e9)
            if memory_mb:
                kwargs["mem_limit"] = f"{memory_mb}m"
            if annotation:
                kwargs["labels"] = {"annotation": annotation}

            if power_on:
                self._docker.client.containers.run(image.id, **kwargs)
                print(f"Clone '{new_vm_name}' created and started.")
            else:
                self._docker.client.containers.create(image.id, **kwargs)
                print(f"Clone '{new_vm_name}' created (not started).")

            return True
        except Exception as e:
            print(f"Clone failed: {e}")
            return False

    def clone_with_config(self, config: CloneConfig) -> bool:
        """Clone the container using a CloneConfig object (Builder Pattern integration)."""
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
        if self._docker:
            self._docker.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
