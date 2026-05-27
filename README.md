# dl_automation_project

A two-layer VM automation platform: a low-level multi-hypervisor library (**vmkit**) and a high-level test orchestration framework (**VMForge**) built on top of it.

---

## Repository Layout

```
dl_automation_project/
├── vmkit/                  # Multi-platform VM management library (implemented)
├── vmforge/                # Test automation orchestration framework (in design)
├── vuln_automation/        # Legacy Ruby project — reference/migration source
├── DESIGN_PLAN.md          # VMForge design decisions and JSON schema
├── ARCHITECTURE.md         # VMForge technical architecture
└── IMPLEMENT_PLAN.md       # VMForge 8-phase implementation plan
```

---

## vmkit — VM Management Library

A unified Python API for managing VMs across VMware vSphere, Proxmox VE, VMware Fusion Pro, Docker, and SSH. Used as the backend by VMForge.

### Install

```bash
cd vmkit
pip install pyVmomi paramiko proxmoxer requests docker urllib3
pip install prompt_toolkit rich mcp   # CLI + MCP server
```

### Configure vSphere

Create `vmkit/vsphere/.config` (gitignored):

```ini
[vcenter]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443
```

### Library Usage

```python
from core.factory import HypervisorFactory
from core.models import CloneConfigBuilder

# Connect and list VMs
with HypervisorFactory.create("vsphere") as mgr:
    vm = mgr.get_vm("base-win10", folder_name="Templates")
    print(vm.get_power_status())

# Clone from snapshot
config = (
    CloneConfigBuilder()
    .target_folder("CI Pool")
    .name("test-vm-01")
    .snapshot("automation")
    .power_on(True)
    .build()
)
vm.clone_with_config(config)
```

### CLI

```bash
cd vmkit

python -m cli                                  # Interactive REPL
python -m cli list-vms --output json           # One-shot, JSON output
python -m cli clone "base-win10" "ci-01" \
    --target-folder "CI Pool" --snapshot "automation" --power-on
python -m cli vm "ci-01" --folder "CI Pool" snapshot create "pre-test"
```

### MCP Server (Claude Code / Claude Desktop)

```bash
cd vmkit
python -m mcp_server   # stdio transport
```

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "vmkit": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/dl_automation_project/vmkit",
      "env": { "VSPHERE_HOST": "...", "VSPHERE_USER": "...", "VSPHERE_PASS": "..." }
    }
  }
}
```

### Supported Platforms

| Platform | Clone | Snapshot | Execute | Notes |
|---|:---:|:---:|:---:|---|
| VMware vSphere | ✅ | ✅ | ✅ | Via GuestOps |
| Proxmox VE | ✅ | ✅ | ✅ | Via agent |
| VMware Fusion Pro | ✅ | ✅ | ✅ | REST API, Mac only |
| Docker | ✅ | ✅ | ✅ | commit/exec |
| SSH | ❌ | ❌ | ✅ | Direct shell access |

---

## VMForge — Test Automation Framework

A JSON-driven test orchestration layer that runs structured test cases on VMs. Uses vmkit as the VM backend and Robot Framework as the test runner.

> **Status**: Design complete, implementation pending. See `DESIGN_PLAN.md`, `ARCHITECTURE.md`, `IMPLEMENT_PLAN.md`.

### How It Works

```
configs/windows/7zip_x86.json          # Define test cases in JSON
    │
    ▼
vmforge generate --platform windows --tag REG1
    │                                  # Python resolves <vars>, generates .robot files
    ▼
tests/generated/windows_REG1/
    7zip_x86.robot                     # 1 file per product, all vars resolved
    1password.robot
    │
    ▼
pabot --processes 14                   # Parallel execution, each test on its own VM
    │
    ▼
reports/output.xml  log.html  junit.xml
```

### JSON Config Format

```json
{
  "product": { "id": "7zip-x86", "name": "7-Zip x86", "signature": 3112 },
  "vars": { "wrapper_path": "C:/Users/Admin/Desktop/wrapper" },
  "environments": [
    {
      "id": "win10-x86",
      "template": "windows-10-86",
      "snapshot": "automation",
      "platform": "vsphere",
      "executor": "powershell",
      "tags": ["REG1"],
      "run_tests": ["download-latest", "install-patch"]
    }
  ],
  "tests": [
    {
      "id": "download-latest",
      "steps": [
        { "run": "& \"<wrapper_path>/test.exe\" --sig <signature>", "capture_as": "output" }
      ],
      "assert": [
        { "path": "result.code", "equals": 0 }
      ]
    }
  ]
}
```

### CLI (planned)

```bash
vmforge validate configs/windows/7zip_x86.json   # Validate config, no VM needed
vmforge validate configs/windows/                 # Validate entire folder
vmforge generate --platform windows --tag REG1    # Generate .robot files only
vmforge run      --platform windows --tag REG1    # Generate + run via pabot
vmforge run      --platform windows --dry-run     # Validate without real VMs
vmforge report   --format excel --output reports/result.xlsx
vmforge migrate  --input vuln_automation/src/test/resources/TestConfig/ \
                 --output configs/windows/         # Convert legacy JSON schema
```

### Architecture

```
vmforge/
├── framework/
│   ├── core/schema/       # Pydantic v2 models, <var> resolver, JSON loader
│   ├── plugins/           # PlatformPlugin (vsphere, ssh_direct)
│   │                        ExecutorPlugin (powershell, ssh, winrm)
│   ├── robot/
│   │   ├── generator/     # JSON → .robot file generator
│   │   └── keywords/      # VmForgeKeywords (RF library: Clone VM, Execute PS, Check Field)
│   └── reporters/         # Excel + JUnit XML reporters
├── configs/               # New-schema JSON test configs
│   ├── windows/
│   └── linux/
├── tests/generated/       # Auto-generated .robot files (gitignored)
├── migrate/               # Legacy schema → new schema converter
├── cli.py
└── pyproject.toml
```

### Test Isolation Model

Each `.robot` suite (one per product × environment) gets **one dedicated VM**:
- `Suite Setup` — clone VM from snapshot once
- `Test Setup` — revert snapshot before each test case (~5–10s)
- `Suite Teardown` — delete VM after all tests finish

This gives full isolation without the cost of cloning per test case.

---

## Development

### Dependencies

| Component | Requires |
|---|---|
| vmkit | Python 3.11+, pyVmomi, paramiko, proxmoxer, docker |
| vmkit CLI | prompt_toolkit, rich |
| vmkit MCP server | mcp |
| VMForge (planned) | pydantic>=2.0, robotframework>=7.0, robotframework-pabot>=2.0, filelock, typer, openpyxl |

### Running Tests

```bash
# vmkit unit tests (no real vSphere needed)
cd vmkit
python -m pytest tests/unit/ -v

# vmkit Robot Framework integration tests (requires real vSphere/SSH)
robot tests/test_ssh_vsphere.robot
robot tests/test_execute_vsphere.robot
```

### Environment Variables

| Variable | Used By | Description |
|---|---|---|
| `VSPHERE_HOST` | vmkit | vCenter hostname or IP |
| `VSPHERE_USER` | vmkit | vCenter username |
| `VSPHERE_PASS` | vmkit | vCenter password |
| `VSPHERE_NO_SSL_VERIFY` | vmkit | Set `1` to skip SSL check |
| `VMK_PROFILE` | vmkit CLI | Default credentials profile name |
| `VMFORGE_VCENTER_HOST` | VMForge | vCenter host override for VMForge plugin |
| `VMFORGE_VCENTER_USER` | VMForge | vCenter user override |
| `VMFORGE_VCENTER_PASSWORD` | VMForge | vCenter password override |

---

## Design Documents

| Document | Contents |
|---|---|
| [`DESIGN_PLAN.md`](DESIGN_PLAN.md) | VMForge vision, JSON schema design, plugin architecture, CLI surface |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Layer diagram, directory structure, component code, data flow |
| [`IMPLEMENT_PLAN.md`](IMPLEMENT_PLAN.md) | 8-phase implementation plan, tasks, validation commands, timeline |
