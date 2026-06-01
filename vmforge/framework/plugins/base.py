from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VMHandle:
    vm_id: str       # clone VM name (vsphere) or host IP (ssh_direct)
    template: str    # source template name
    platform: str    # "vsphere" | "ssh_direct"
    folder_name: str = ""


@dataclass
class CommandResult:
    stdout: str
    exit_code: int
    stderr: str = ""


class PlatformPlugin(ABC):
    @abstractmethod
    def clone_and_snapshot(self, template: str, snapshot: str, clone_name: str, folder: str) -> VMHandle: ...

    @abstractmethod
    def revert_snapshot(self, vm: VMHandle, snapshot: str) -> None: ...

    @abstractmethod
    def teardown(self, vm: VMHandle) -> None: ...


class ExecutorPlugin(ABC):
    @abstractmethod
    def run(self, vm: VMHandle, command: str) -> CommandResult: ...
