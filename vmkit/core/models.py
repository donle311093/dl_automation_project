"""CloneConfig — Builder Pattern for VM clone parameters.

Design Pattern: Builder
- CloneConfig holds all clone parameters with sensible defaults.
- CloneConfigBuilder provides a fluent interface for constructing CloneConfig objects,
  making complex clone operations readable and avoiding telescoping constructor problems.

Usage:
    config = (
        CloneConfigBuilder()
        .target_folder("My Folder")
        .name("cloned-vm")
        .snapshot("base-snapshot")
        .datastore("SSD-Datastore")
        .annotation("Cloned for testing")
        .cpus(4)
        .memory_mb(4096)
        .power_on(True)
        .build()
    )

    vm_manager.clone_with_config(config)
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CloneConfig:
    """Immutable configuration for a VM clone operation."""

    target_folder_name: str
    new_vm_name: str
    snapshot_name: Optional[str] = None
    datastore_name: Optional[str] = None
    annotation: Optional[str] = None
    num_cpus: Optional[int] = None
    memory_mb: Optional[int] = None
    power_on: bool = False

    def to_dict(self) -> dict:
        """Convert to a plain dictionary (useful for logging / API calls)."""
        return {
            "target_folder_name": self.target_folder_name,
            "new_vm_name": self.new_vm_name,
            "snapshot_name": self.snapshot_name,
            "datastore_name": self.datastore_name,
            "annotation": self.annotation,
            "num_cpus": self.num_cpus,
            "memory_mb": self.memory_mb,
            "power_on": self.power_on,
        }


class CloneConfigBuilder:
    """Fluent builder for CloneConfig.

    Design Pattern: Builder
    Separates the construction of CloneConfig from its representation.
    """

    def __init__(self):
        self._target_folder_name: str = ""
        self._new_vm_name: str = ""
        self._snapshot_name: Optional[str] = None
        self._datastore_name: Optional[str] = None
        self._annotation: Optional[str] = None
        self._num_cpus: Optional[int] = None
        self._memory_mb: Optional[int] = None
        self._power_on: bool = False

    def target_folder(self, folder_name: str) -> "CloneConfigBuilder":
        self._target_folder_name = folder_name
        return self

    def name(self, vm_name: str) -> "CloneConfigBuilder":
        self._new_vm_name = vm_name
        return self

    def snapshot(self, snapshot_name: str) -> "CloneConfigBuilder":
        self._snapshot_name = snapshot_name
        return self

    def datastore(self, datastore_name: str) -> "CloneConfigBuilder":
        self._datastore_name = datastore_name
        return self

    def annotation(self, annotation: str) -> "CloneConfigBuilder":
        self._annotation = annotation
        return self

    def cpus(self, num_cpus: int) -> "CloneConfigBuilder":
        self._num_cpus = num_cpus
        return self

    def memory_mb(self, memory_mb: int) -> "CloneConfigBuilder":
        self._memory_mb = memory_mb
        return self

    def power_on(self, power_on: bool = True) -> "CloneConfigBuilder":
        self._power_on = power_on
        return self

    def build(self) -> CloneConfig:
        """Build and return an immutable CloneConfig.

        Raises:
            ValueError: If required fields are missing.
        """
        if not self._target_folder_name:
            raise ValueError("target_folder_name is required.")
        if not self._new_vm_name:
            raise ValueError("new_vm_name is required.")

        return CloneConfig(
            target_folder_name=self._target_folder_name,
            new_vm_name=self._new_vm_name,
            snapshot_name=self._snapshot_name,
            datastore_name=self._datastore_name,
            annotation=self._annotation,
            num_cpus=self._num_cpus,
            memory_mb=self._memory_mb,
            power_on=self._power_on,
        )
