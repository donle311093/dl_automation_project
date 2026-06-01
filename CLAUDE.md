# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A unified multi-platform VM management library providing a consistent API across VMware vSphere, Proxmox VE, VMware Fusion Pro, Docker, and SSH. All code lives under `vmkit/`.

## Setup

```bash
pip install pyVmomi paramiko proxmoxer requests docker urllib3
# For tests:
pip install robotframework
```

No build system — pure Python, no compilation step.

## Running Code

```bash
cd vmkit

# Run any example
python example/example_vm_manager.py
python example/example_clone_vm.py

# Run Robot Framework tests (requires real vSphere/SSH targets)
robot tests/test_ssh_vsphere.robot
robot tests/test_execute_vsphere.robot

# Root-level IP utility (Windows only)
python check_ip.py 192.168.1.1
```

## Architecture

### Core Abstractions (`core/`)

- **`interfaces.py`** — `IVMManager` (single VM ops: power, snapshots, clone, execute_command, annotations) and `IHypervisorManager` (platform-level: connect, find VMs, delete folders, get datastore info)
- **`factory.py`** — `HypervisorFactory.create(platform, config)` returns a concrete `IHypervisorManager`; registered platforms: `"vsphere"`, `"proxmox"`, `"fusion"`
- **`models.py`** — `CloneConfig` (dataclass) and `CloneConfigBuilder` (fluent builder) for VM cloning parameters

### Platform Implementations

Each platform follows the same structure: a `*Manager` class (implements `IHypervisorManager`) + a `*VMManager` class (implements `IVMManager`).

| Platform | Module | Notes |
|----------|--------|-------|
| vSphere | `vsphere/` | 15 files; credentials from `vsphere/.config` (INI, gitignored) |
| Proxmox | `proxmox_impl/` | REST API; includes `ProxmoxTaskWaiter` for async UPID polling |
| Fusion Pro | `fusion_impl/` | REST API on Mac port 8697; requires Fusion Pro 13+ |
| Docker | `docker_impl/docker_vm.py` | Not in factory registry; use `DockerVMManager` directly |
| SSH | `ssh/` | Not in factory registry; use `SSHVMManager` directly |

### Design Patterns in Use

- **Strategy** — `IVMManager` / `IHypervisorManager` with platform-specific implementations
- **Facade** — `VSphereManager`, `ProxmoxManager`, `FusionManager` wrap complex APIs
- **Adapter** — `DockerVMManager`, `SSHVMManager` adapt non-standard APIs to `IVMManager`
- **Factory** — `HypervisorFactory` for centralized manager creation
- **Builder** — `CloneConfigBuilder` → `CloneConfig`

### Partial Support

Docker and SSH do not implement the full `IVMManager` interface:
- Docker: no annotations, no revert-to-snapshot, no traditional cloning
- SSH: no `power_on`, no snapshots, no annotations

## vSphere Configuration

Create `vmkit/vsphere/.config` (already gitignored):
```ini
[vcenter]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443
```

## Typical Usage Patterns

```python
# Factory pattern (vSphere, Proxmox, Fusion)
from core.factory import HypervisorFactory

with HypervisorFactory.create("vsphere") as mgr:
    vm = mgr.get_vm("VM Name", folder_name="Folder")
    print(vm.get_power_status())

# Builder pattern for cloning
from core.models import CloneConfigBuilder

config = (
    CloneConfigBuilder()
    .target_folder("CI Pool")
    .name("clone-01")
    .snapshot("base")
    .cpus(4).memory_mb(4096).power_on(True)
    .build()
)
vm.clone_with_config(config)

# Direct SSH (not in factory)
from ssh.ssh_vm import SSHVMManager

with SSHVMManager("10.0.0.50") as vm:
    vm.login("user", "pass")
    result = vm.execute_command("df -h")
```
