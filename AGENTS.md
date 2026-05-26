# AGENTS.md

Multi-platform VM management library (vSphere, Proxmox, Fusion Pro, Docker, SSH).  
See [CLAUDE.md](CLAUDE.md) for full setup, architecture, and usage patterns.  
See [ARCHITECTURE.md](ARCHITECTURE.md) for planned CLI + MCP server design.

## Setup

```bash
pip install pyVmomi paramiko proxmoxer requests docker urllib3
pip install robotframework  # for tests
```

## Working Directory

All imports assume `automation_framework/` as the working directory:

```bash
cd automation_framework
python example/example_vm_manager.py
```

## Architecture

Core contracts are in [core/interfaces.py](automation_framework/core/interfaces.py):
- `IHypervisorManager` — platform-level: connect, find VMs, delete, datastore info
- `IVMManager` — single VM: power, snapshots, clone, execute_command, annotations

Every platform ships a paired `*Manager(IHypervisorManager)` + `*VMManager(IVMManager)`.

| Platform | Module | Factory key |
|----------|--------|-------------|
| vSphere | `vsphere/` | `"vsphere"` |
| Proxmox | `proxmox_impl/` | `"proxmox"` |
| Fusion Pro | `fusion_impl/` | `"fusion"` |
| Docker | `docker_impl/docker_vm.py` | not registered — use `DockerVMManager` directly |
| SSH | `ssh/ssh_vm.py` | not registered — use `SSHVMManager` directly |

Docker and SSH implement `IVMManager` **partially** — Docker has no annotations/snapshots/cloning; SSH has no power, snapshots, or annotations.

## Adding a New Platform

1. Create `<platform>_impl/` with `<Platform>Manager(IHypervisorManager)` + `<Platform>VMManager(IVMManager)`.
2. Register it in `HypervisorFactory._REGISTRY` in [core/factory.py](automation_framework/core/factory.py).

## vSphere Credentials

Create `automation_framework/vsphere/.config` (already gitignored):

```ini
[vcenter]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443
```

## Tests

Robot Framework tests require **live infrastructure** — they cannot run offline:

```bash
robot tests/test_ssh_vsphere.robot
robot tests/test_execute_vsphere.robot
```
