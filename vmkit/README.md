# vmkit

A unified VM management library providing a **consistent API** across **VMware vSphere**, **Proxmox VE**, **VMware Fusion Pro**, **Docker**, and **SSH** — with a full interactive CLI and MCP server built on top.

---

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Guide](#cli-guide)
  - [Quick Start](#quick-start)
  - [Authentication](#authentication)
  - [Interactive REPL](#interactive-repl)
  - [One-shot Mode](#one-shot-mode)
  - [Batch Scripting](#batch-scripting)
  - [Command Reference](#command-reference)
- [MCP Server Guide](#mcp-server-guide)
  - [Setup](#setup)
  - [Connect with Claude Code](#connect-with-claude-code)
  - [Connect with Claude Desktop](#connect-with-claude-desktop)
  - [Available MCP Tools](#available-mcp-tools)
- [Core Library Usage](#core-library-usage)
- [Architecture](#architecture)
- [Supported Operations by Platform](#supported-operations-by-platform)

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Core library dependencies
pip install pyVmomi paramiko proxmoxer requests docker urllib3

# CLI dependencies
pip install prompt_toolkit rich

# MCP server dependencies
pip install mcp

# Optional: YAML output, safer XML parsing
pip install pyyaml defusedxml

# Robot Framework (for the built-in test runner)
pip install robotframework
```

---

## Configuration

### vSphere Credentials File

Create `vmkit/vsphere/.config` (already in `.gitignore`):

```ini
[vcenter]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443
```

### Named Profiles

For multiple environments, save profiles to `~/.vmkit/profiles/<name>.config` (same INI format). Switch with `--profile <name>`.

```bash
mkdir -p ~/.vmkit/profiles
cat > ~/.vmkit/profiles/lab.config << 'EOF'
[vcenter]
host     = 10.0.0.5
user     = admin@vsphere.local
password = LabPassword
port     = 443
EOF
```

### Environment Variables

All credential fields can be supplied via environment variables (highest priority):

| Variable | Description |
|---|---|
| `VSPHERE_HOST` | vCenter hostname or IP |
| `VSPHERE_USER` | vCenter username |
| `VSPHERE_PASS` | vCenter password |
| `VSPHERE_PORT` | vCenter port (default: `443`) |
| `VSPHERE_NO_SSL_VERIFY` | Set to `1` to skip SSL verification |
| `VMK_PROFILE` | Default profile name (used if no `--profile` flag) |

---

## CLI Guide

### Quick Start

```bash
cd vmkit

# Version check
python -m cli --version
# → vmkit 0.1.0

# Interactive REPL (reads credentials from vsphere/.config or prompts)
python -m cli

# One-shot: list VMs as JSON
python -m cli list-vms --output json

# One-shot: get single VM info
python -m cli info "My-VM" --folder "CI Pool" --output json
```

---

### Authentication

The CLI resolves credentials in this priority order on startup:

```
1. Environment variables  VSPHERE_HOST / VSPHERE_USER / VSPHERE_PASS
2. --profile flag         ~/.vmkit/profiles/<name>.config
3. VMK_PROFILE env var     same path as above
4. Local config file      vmkit/vsphere/.config
5. Interactive prompt     typed at startup (optionally saved)
```

**Examples:**

```bash
# Use environment variables (CI/CD)
export VSPHERE_HOST=vcenter.corp.com
export VSPHERE_USER=svc-automation@vsphere.local
export VSPHERE_PASS=secret
python -m cli list-vms --output json

# Use a named profile
python -m cli --profile prod

# Disable SSL verification (self-signed certs)
python -m cli --no-verify-ssl

# Debug mode (full tracebacks on errors)
python -m cli --debug
```

---

### Interactive REPL

The CLI has three nested REPL levels:

```
Manager REPL    vsphere>
  └─ VM REPL    vsphere/vm[MyVM]>
       └─ Shell REPL  vsphere/vm[MyVM]/shell>
```

#### Starting the REPL

```bash
python -m cli                          # default: vsphere
python -m cli --platform vsphere
python -m cli --output json            # all output as JSON
python -m cli --profile lab --debug
```

On start you will see:
```
Connected to vcenter.corp.com [vsphere]. Type 'help' for commands.
vsphere>
```

#### Manager REPL — VM List & Search

```
vsphere> list-vms
vsphere> list-vms --folder "CI Pool"
vsphere> list-vms --folder "CI Pool" --limit 20 --offset 40
vsphere> search win10
vsphere> info "Windows 10 64bit" --folder "Templates"
vsphere> datastore-info
```

#### Manager REPL — Health Check

```
vsphere> health-check
vsphere> health-check --folder "CI Pool"
```

Output columns: `name`, `power`, `tools`, `healthy`

#### Manager REPL — Snapshot List

```
vsphere> snapshots "Windows 10 64bit"
vsphere> snapshots "Windows 10 64bit" --folder "Templates"
```

#### Manager REPL — Clone a VM

```
vsphere> clone "base-win10" "clone-01" --target-folder "CI Pool"
vsphere> clone "base-win10" "clone-02" \
    --folder "Templates" \
    --target-folder "CI Pool" \
    --snapshot "clean-state" \
    --cpus 4 \
    --memory 8192 \
    --power-on
```

#### Manager REPL — Bulk Operations

```
# Power on / off all VMs in a folder
vsphere> bulk start  --folder "CI Pool" --force
vsphere> bulk stop   --folder "CI Pool" --force

# Snapshot / revert all VMs
vsphere> bulk snapshot --folder "CI Pool" --snapshot-name "pre-test" --force
vsphere> bulk revert   --folder "CI Pool" --force

# Clone a template N times
vsphere> bulk-clone "base-win10" --count 5 --prefix "ci" --target-folder "CI Pool" --force
# creates: ci-01, ci-02, ci-03, ci-04, ci-05
```

#### Manager REPL — Delete Operations

```
vsphere> delete-vm   "old-clone" --folder "CI Pool"
vsphere> delete-vm   "old-clone" --folder "CI Pool" --force   # skip confirm
vsphere> delete-folder "Temp"
vsphere> delete-all-vms --folder "CI Pool" --force
```

#### Manager REPL — Diff & Export

```
# Show differing fields between two VMs
vsphere> diff "vm-a" "vm-b" --folder "CI Pool"

# Export VM config to file
vsphere> export "Windows 10 64bit" --format json
vsphere> export "Windows 10 64bit" --format yaml --output /tmp/vm-config.yaml
```

#### Manager REPL — Watch (auto-refresh)

```
# Refresh health-check every 5 seconds
vsphere> watch health-check --folder "CI Pool"
vsphere> watch --interval 10 list-vms --folder "CI Pool"
```

Only read-only commands are allowed in `watch`: `list-vms`, `list-folders`, `search`, `info`, `snapshots`, `datastore-info`, `health-check`.

#### Manager REPL — Test Runner

```
vsphere> test list tests/
vsphere> test run tests/test_ssh_vsphere.robot
vsphere> test run tests/ --tag smoke --tag regression
vsphere> test run tests/ --suite "SSH Tests" --timeout 120
vsphere> test report
vsphere> test report --output-xml tests/output.xml
```

#### Manager REPL — Session Management

```
vsphere> reconnect                    # re-establish connection (clears VM cache)
vsphere> switch-profile prod          # switch to a different credentials profile
vsphere> run-script deploy.af         # run a batch command script
vsphere> help                         # show all commands
vsphere> exit
```

---

#### Entering the VM REPL

```
vsphere> use "Windows 10 64bit"
vsphere> use "Windows 10 64bit" --folder "CI Pool"
```

Prompt changes to `vsphere/vm[Windows 10 64bit]>`

#### VM REPL — Power & Status

```
vsphere/vm[MyVM]> status
vsphere/vm[MyVM]> start
vsphere/vm[MyVM]> stop
vsphere/vm[MyVM]> stop --force         # skip confirm
vsphere/vm[MyVM]> restart
vsphere/vm[MyVM]> reset --force
vsphere/vm[MyVM]> suspend
vsphere/vm[MyVM]> info
vsphere/vm[MyVM]> health
vsphere/vm[MyVM]> tools-status
```

#### VM REPL — Wait Commands (useful in scripts)

```
vsphere/vm[MyVM]> wait-for-status on  --timeout 120 --interval 5
vsphere/vm[MyVM]> wait-for-status off --timeout 60
vsphere/vm[MyVM]> wait-for-tools      --timeout 300 --interval 10
```

#### VM REPL — Snapshot Operations

```
vsphere/vm[MyVM]> snapshots
vsphere/vm[MyVM]> snapshot create "before-patch"
vsphere/vm[MyVM]> snapshot create "pre-deploy" --description "Before v2.1 deploy"
vsphere/vm[MyVM]> snapshot revert "before-patch"
vsphere/vm[MyVM]> snapshot revert                  # revert to current snapshot
vsphere/vm[MyVM]> snapshot delete "old-snap"
```

#### VM REPL — Clone from VM Context

```
vsphere/vm[MyVM]> clone "MyVM-clone-01" --target-folder "CI Pool"
vsphere/vm[MyVM]> clone "MyVM-clone-02" --snapshot "clean" --cpus 2 --memory 4096 --power-on
```

#### VM REPL — Annotation

```
vsphere/vm[MyVM]> annotation get
vsphere/vm[MyVM]> annotation set "Owned by QA team — do not delete"
```

#### VM REPL — Guest OS Login & Shell

```
vsphere/vm[MyVM]> login administrator
# → Password: (hidden input)
# → Enters Shell REPL automatically on success
```

Prompt changes to `vsphere/vm[MyVM]/shell>`

```
vsphere/vm[MyVM]/shell> ipconfig
vsphere/vm[MyVM]/shell> dir C:\
vsphere/vm[MyVM]/shell> exit     # back to VM REPL
```

You can also run one-off guest commands without entering the Shell REPL:

```
vsphere/vm[MyVM]> run ipconfig /all
vsphere/vm[MyVM]> run dir C:\Users
```

`run` requires a prior `login` call in the same session.

#### Navigation

```
vsphere/vm[MyVM]> back            # return to Manager REPL
vsphere/vm[MyVM]> exit            # same as back
```

---

### One-shot Mode

Pass commands directly after the global flags to run non-interactively and exit. Exit codes: `0` = success, `1` = error, `2` = usage error, `3` = auth/connection error.

```bash
# List all VMs as JSON (suitable for scripting / CI)
python -m cli list-vms --output json
python -m cli list-vms --folder "CI Pool" --output json

# Search
python -m cli search win10 --output json

# Get VM info
python -m cli info "Windows 10 64bit" --folder "Templates" --output json

# Clone
python -m cli clone "base-win10" "ci-build-01" \
    --folder "Templates" \
    --target-folder "CI Pool" \
    --snapshot "clean-state" \
    --power-on

# VM subcommands via one-shot
python -m cli vm "ci-build-01" --folder "CI Pool" status
python -m cli vm "ci-build-01" --folder "CI Pool" start
python -m cli vm "ci-build-01" --folder "CI Pool" snapshot create "post-deploy"
python -m cli vm "ci-build-01" --folder "CI Pool" wait-for-status on --timeout 120
python -m cli vm "ci-build-01" --folder "CI Pool" wait-for-tools --timeout 300

# Health check
python -m cli health-check --folder "CI Pool" --output json

# Datastore info
python -m cli datastore-info --output json

# Test runner (non-interactive)
python -m cli test run tests/ --tag smoke
python -m cli test report --output json

# Check exit code in shell scripts
python -m cli info "MyVM" --output json; echo "exit: $?"
```

---

### Batch Scripting

Create a `.af` script file (one command per line, `#` for comments):

```bash
# deploy.af — provision a test environment

# Clone template
clone "base-win10" "test-env-01" --target-folder "CI Pool" --snapshot "clean" --power-on

# Enter VM and wait
use "test-env-01" --folder "CI Pool"
wait-for-status on --timeout 120
wait-for-tools --timeout 300
snapshot create "post-provision"
back

# Provision second VM
clone "base-win10" "test-env-02" --target-folder "CI Pool" --snapshot "clean" --power-on
```

Run the script inside the REPL:

```
vsphere> run-script /path/to/deploy.af
```

---

### Command Reference

#### Global Flags

| Flag | Default | Description |
|---|---|---|
| `--platform` | `vsphere` | Hypervisor: `vsphere`, `proxmox`, `fusion` |
| `--profile` | — | Credentials profile name |
| `--output` | `table` | Output format: `table`, `json`, `yaml` |
| `--no-verify-ssl` | — | Skip SSL certificate check |
| `--debug` | — | Show full tracebacks |
| `--no-log` | — | Disable audit log writes |
| `--version` | — | Print version and exit |

#### Manager REPL Commands

| Command | Arguments | Description |
|---|---|---|
| `list-vms` | `[--folder F] [--limit N] [--offset N]` | List VMs |
| `search` | `<keyword>` | Search VMs by name |
| `info` | `<vm> [--folder F]` | VM configuration details |
| `snapshots` | `<vm> [--folder F]` | List snapshots |
| `datastore-info` | — | Storage usage |
| `health-check` | `[--folder F]` | Power + tools status |
| `clone` | `<vm> <new_name> [options]` | Clone a VM |
| `bulk` | `start\|stop\|snapshot\|revert --folder F` | Bulk action |
| `bulk-clone` | `<template> --count N [--prefix P]` | Clone template N times |
| `delete-vm` | `<vm> --folder F [--force]` | Delete a VM |
| `delete-folder` | `<folder> [--force]` | Delete a folder |
| `delete-all-vms` | `--folder F [--force]` | Delete all VMs in folder |
| `use` | `<vm> [--folder F]` | Enter VM REPL |
| `diff` | `<vm1> <vm2> [--folder F]` | Compare VM configs |
| `export` | `<vm> [--format json\|yaml] [--output F]` | Export VM info |
| `watch` | `[--interval N] <command>` | Auto-refresh a command |
| `test` | `list\|run\|report [options]` | Robot Framework runner |
| `run-script` | `<path>` | Run a batch script |
| `reconnect` | — | Reconnect to hypervisor |
| `switch-profile` | `<name>` | Switch credentials profile |
| `help` | — | Show help |
| `exit` / `quit` | — | Exit |

#### VM REPL Commands

| Command | Arguments | Description |
|---|---|---|
| `status` | — | Power state |
| `start` | — | Power on |
| `stop` | `[--force]` | Power off |
| `restart` | — | Guest OS reboot |
| `reset` | `[--force]` | Hard reset |
| `suspend` | — | Suspend |
| `info` | — | VM details |
| `health` | — | Power + tools summary |
| `tools-status` | — | VMware Tools status |
| `annotation` | `get\|set [value]` | Read / write annotation |
| `snapshots` | — | List snapshots |
| `snapshot` | `create\|revert\|delete <name>` | Snapshot operations |
| `clone` | `<new_name> [options]` | Clone this VM |
| `wait-for-status` | `on\|off [--timeout N]` | Poll until power state |
| `wait-for-tools` | `[--timeout N]` | Poll until tools ready |
| `login` | `<user> [password]` | Authenticate to guest |
| `run` | `<command>` | Execute guest command |
| `back` / `exit` | — | Return to Manager REPL |

---

## MCP Server Guide

The MCP server exposes VM management as tools callable by any MCP-compatible AI assistant (Claude Code, Claude Desktop, etc.).

### Setup

Install the MCP package:

```bash
pip install mcp
```

Set required environment variables (the server reads credentials on first tool call):

```bash
export VSPHERE_HOST=vcenter.corp.com
export VSPHERE_USER=administrator@vsphere.local
export VSPHERE_PASS=YourPassword
export VSPHERE_PORT=443              # optional, default 443
export VSPHERE_NO_SSL_VERIFY=1       # optional, skip SSL check

# Guest OS commands (optional — used by execute_command tool)
export VM_USER=Administrator
export VM_PASS=GuestPassword
```

Test that the server starts cleanly:

```bash
cd vmkit
python -m mcp_server
# Server starts in stdio mode, waiting for MCP client connections
```

---

### Connect with Claude Code

Add the server to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "vmkit": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/dl_automation_project/vmkit",
      "env": {
        "VSPHERE_HOST": "vcenter.corp.com",
        "VSPHERE_USER": "administrator@vsphere.local",
        "VSPHERE_PASS": "YourPassword",
        "VSPHERE_NO_SSL_VERIFY": "1"
      }
    }
  }
}
```

Or add to user-level `~/.claude/settings.json` to make it available in all projects.

Reload Claude Code (or run `/mcp`) to pick up the new server. You can then ask Claude directly:

```
List all VMs in folder "CI Pool"
Clone "base-win10" to "test-01" in folder "CI Pool"
Check health of all VMs in "Production"
Create a snapshot called "pre-deploy" on "prod-server-01"
Run the smoke tests in tests/
```

---

### Connect with Claude Desktop

Edit the Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vmkit": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:\\path\\to\\dl_automation_project\\vmkit",
      "env": {
        "VSPHERE_HOST": "vcenter.corp.com",
        "VSPHERE_USER": "administrator@vsphere.local",
        "VSPHERE_PASS": "YourPassword",
        "VSPHERE_NO_SSL_VERIFY": "1",
        "VM_USER": "Administrator",
        "VM_PASS": "GuestPassword"
      }
    }
  }
}
```

Restart Claude Desktop. The tools appear automatically when Claude detects a relevant request.

---

### Available MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `list_vms` | `folder?` | List VMs, optionally filtered by folder |
| `get_vm_info` | `vm_name`, `folder?` | Full VM configuration and runtime state |
| `get_power_status` | `vm_name`, `folder?` | Current power state |
| `power_on` | `vm_name`, `folder?` | Power on a VM |
| `power_off` | `vm_name`, `folder?` | Power off a VM |
| `restart_vm` | `vm_name`, `folder?` | Reboot guest OS |
| `list_snapshots` | `vm_name`, `folder?` | List all snapshots |
| `create_snapshot` | `vm_name`, `snap_name`, `description?`, `folder?` | Create a snapshot |
| `revert_snapshot` | `vm_name`, `snap_name?`, `folder?` | Revert (current snapshot if name omitted) |
| `delete_snapshot` | `vm_name`, `snap_name`, `folder?` | Delete a snapshot |
| `clone_vm` | `vm_name`, `new_name`, `target_folder`, `folder?`, `snapshot?`, `cpus?`, `memory_mb?`, `power_on?` | Clone a VM |
| `execute_command` | `vm_name`, `command`, `folder?` | Run a command in the guest OS |
| `health_check` | `folder?` | Power + tools status for all VMs in a folder |
| `get_datastore_info` | — | Storage capacity and usage statistics |
| `run_tests` | `test_path`, `tags?`, `variables?` | Run Robot Framework tests |

**Security notes:**
- `execute_command` reads `VM_USER` and `VM_PASS` from the server environment — credentials are never passed as tool parameters.
- All tools return `{"error": "<message>"}` on failure instead of raising exceptions, so the AI assistant always gets a usable response.

---

## Core Library Usage

### Factory Pattern

```python
from core.factory import HypervisorFactory

# vSphere (reads vsphere/.config by default)
with HypervisorFactory.create("vsphere") as mgr:
    vm = mgr.get_vm("Windows 10 64bit", folder_name="CI Pool")
    print(vm.get_power_status())

# vSphere with explicit credentials
with HypervisorFactory.create("vsphere", {
    "host": "vcenter.corp.com",
    "user": "admin@vsphere.local",
    "password": "secret",
}) as mgr:
    vms = mgr.find_vms_in_folder("CI Pool")

# Proxmox
with HypervisorFactory.create("proxmox", {
    "host": "10.0.0.1",
    "user": "root@pam",
    "password": "secret",
}) as mgr:
    vm = mgr.get_vm("VM 100", "pve-node")
    print(vm.get_vm_info())

# VMware Fusion Pro (Mac)
with HypervisorFactory.create("fusion", {
    "host":     "192.168.1.100",
    "port":     8697,
    "username": "admin",
    "password": "secret",
}) as mgr:
    vm = mgr.get_vm("Ubuntu 22.04")
    print(vm.get_power_status())
```

### Builder Pattern — Clone

```python
from core.models import CloneConfigBuilder
from vsphere.vsphere_manager import VSphereManager

config = (
    CloneConfigBuilder()
    .target_folder("CI Pool")
    .name("win10-test-01")
    .snapshot("clean-state")
    .datastore("SSD-DS")
    .annotation("CI build — auto-provisioned")
    .cpus(4)
    .memory_mb(8192)
    .power_on(True)
    .build()
)

with VSphereManager() as vsphere:
    vm = vsphere.get_vm("base-win10", folder_name="Templates")
    vm.clone_with_config(config)
```

### Direct Usage — SSH

```python
from ssh.ssh_vm import SSHVMManager

with SSHVMManager("10.0.0.50") as vm:
    vm.login("dev", "dev")
    result = vm.execute_command("df -h")
    print(result["stdout"])
```

### Direct Usage — Docker

```python
from docker_impl.docker_vm import DockerVMManager

with DockerVMManager("my-container") as vm:
    vm.login("", "")
    result = vm.execute_command("whoami")
    print(result["stdout"])
```

---

## Architecture

### Design Patterns

| Pattern | Where Used | Purpose |
|---|---|---|
| **Strategy** | `IVMManager` / `IHypervisorManager` | Uniform interface; each platform is a swappable concrete strategy |
| **Facade** | `VSphereManager`, `ProxmoxManager`, `FusionManager` | Hides complex hypervisor APIs behind a clean interface |
| **Adapter** | `DockerVMManager`, `SSHVMManager` | Adapts Docker/SSH protocols to `IVMManager` |
| **Factory** | `HypervisorFactory` | Centralises creation by platform name |
| **Builder** | `CloneConfigBuilder` / `CloneConfig` | Fluent construction of clone parameters |

### Package Structure

```
vmkit/
├── core/                        # Shared abstractions
│   ├── interfaces.py            #   IVMManager, IHypervisorManager
│   ├── models.py                #   CloneConfig + CloneConfigBuilder
│   └── factory.py               #   HypervisorFactory
│
├── vsphere/                     # VMware vSphere
│   ├── vsphere_manager.py
│   ├── vsphere_vm.py
│   ├── vcenter_client.py
│   └── .config                  #   vCenter credentials (gitignored)
│
├── proxmox_impl/                # Proxmox VE
│   ├── proxmox_manager.py
│   ├── proxmox_vm.py
│   └── task_waiter.py
│
├── fusion_impl/                 # VMware Fusion Pro (Mac)
│   ├── fusion_manager.py
│   ├── fusion_vm.py
│   └── fusion_client.py
│
├── docker_impl/                 # Docker
│   └── docker_vm.py
│
├── ssh/                         # SSH direct access
│   ├── ssh_client.py
│   └── ssh_vm.py
│
├── cli/                         # Interactive CLI + one-shot mode
│   ├── main.py                  #   Entry point, argparse
│   ├── auth.py                  #   Credential resolution chain
│   ├── session.py               #   SessionState dataclass + safe_call
│   ├── repl_manager.py          #   Manager REPL
│   ├── repl_vm.py               #   VM REPL
│   ├── repl_shell.py            #   Shell REPL
│   ├── oneshot.py               #   Non-interactive dispatcher
│   ├── batch.py                 #   .af script runner
│   ├── completer.py             #   Tab completion
│   └── output.py                #   Rich table/JSON/YAML rendering + audit log
│
├── mcp_server/                  # MCP server (stdio transport)
│   ├── server.py                #   FastMCP entry point
│   └── tools.py                 #   Tool registrations
│
└── tests/
    ├── unit/                    #   pytest unit tests (no vSphere required)
    └── *.robot                  #   Robot Framework integration tests
```

---

## Supported Operations by Platform

| Operation | vSphere | Proxmox | Fusion | Docker | SSH |
|---|:---:|:---:|:---:|:---:|:---:|
| `get_power_status` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `power_on` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `power_off` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `suspend` | ✅ | ✅ | ✅ | ✅ (pause) | ❌ |
| `reboot` | ✅ | ✅ | ✅ | ✅ (restart) | ✅ |
| `reset` | ✅ | ✅ | ✅ | ✅ (kill+start) | ✅ (reboot) |
| `get_vm_info` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_guest_tools_status` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_annotation` | ✅ | ✅ | ✅ | ✅ (labels) | ❌ |
| `set_annotation` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `get_snapshots` | ✅ | ✅ | ✅ | ✅ (images) | ❌ |
| `create_snapshot` | ✅ | ✅ | ✅ | ✅ (commit) | ❌ |
| `revert_to_snapshot` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `delete_snapshot` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `login` | ✅ | ✅ (agent) | ✅ | ✅ | ✅ (SSH) |
| `execute_command` | ✅ | ✅ (agent) | ✅ (Tools) | ✅ (exec) | ✅ |
| `clone` | ✅ | ✅ | ✅ | ✅ (commit+run) | ❌ |
