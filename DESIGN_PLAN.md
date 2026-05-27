# VMForge — Design Plan

## 1. Vision

**VMForge** is a generic, Python-native test automation framework for running structured test cases on virtual machines. It is inspired by the domain knowledge of `vuln_automation/` (patch/vulnerability testing) but designed as a reusable platform for any VM-based automation testing: installation tests, configuration tests, regression suites, security checks.

**What it is NOT**: A 1:1 port of `vuln_automation/` from Ruby to Python. The Ruby project is a reference for domain patterns only.

**Core value proposition:**
- Define test cases in JSON config files, run them on VMs across platforms
- Robot Framework as the test runner — standard tooling, standard reports
- Plugin architecture — add new VM platforms or executors without touching core
- Full test isolation — every test case starts from a clean VM snapshot
- CI/CD native — JUnit XML output, proper exit codes, dry-run / validate mode

---

## 2. Key Design Decisions

### 2.1 JSON Config Format — Improved Schema

Keep JSON for backward compatibility with existing files. Schema is redesigned to be explicit and unambiguous.

**Variable syntax: `<var>` (angle brackets)**
- Zero conflict with PowerShell `${}`, Robot `${}`, Python `{}`
- 700 existing files compatible without modification
- Simple regex resolver, proven in original project

**`capture_as` for output chaining** — replaces `<std_out>` magic:
```json
{
  "steps": [
    { "run": "(Get-ChildItem ...).name",             "capture_as": "filename" },
    { "run": "... --path \"<wrapper_path>/<filename>\"", "capture_as": "output" }
  ]
}
```

**Lifecycle phase naming** — clearer than old `before/tested_function/after`:

| Old | New | Semantics |
|---|---|---|
| `before.commands` | `setup` | Runs before steps, failure skips test |
| `tested_function.commands` | `steps` | The actual test logic |
| `after.check` | `assert` | JSON field assertions on captured output |
| `after.commands` | `teardown` | Always runs, even if assert fails |

**Full new schema:**
```json
{
  "product": {
    "id": "7zip-x86-msi",
    "name": "7-Zip x86 MSI",
    "signature": 3112
  },
  "vars": {
    "wrapper_path": "C:/Users/Admin/Desktop/wrapper",
    "patch_id": 12,
    "architecture": "32-bit",
    "installers_path": "//10.40.164.66/test/installers/7z_x86"
  },
  "environments": [
    {
      "id": "win10-x86",
      "template": "windows-10-86",
      "snapshot": "automation",
      "platform": "vsphere",
      "executor": "powershell",
      "tags": ["REG1"],
      "vars": {
        "exe_path": "C:\\Program Files\\7-Zip\\7zFM.exe"
      },
      "run_tests": ["download-latest", "install-patch", "check-defunct"]
    },
    {
      "id": "win11-x64-online",
      "template": "windows-11-64-autologin",
      "snapshot": "automation",
      "platform": "vsphere",
      "executor": "powershell",
      "tags": ["REG1", "online"],
      "vars": {
        "exe_path": "C:\\Program Files (x86)\\7-Zip\\7zFM.exe"
      },
      "run_tests": ["download-latest", "check-defunct"]
    }
  ],
  "tests": [
    {
      "id": "download-latest",
      "name": "Download Latest Installer",
      "setup": [
        "& New-Item -ItemType Directory -Force -Path \"<wrapper_path>/latest\""
      ],
      "steps": [
        {
          "run": "& \"<wrapper_path>/test_auto_patching.exe\" --sig <signature> --download 2 --architecture <architecture>",
          "capture_as": "output"
        }
      ],
      "assert": [
        { "path": "result.code",     "equals": 0  },
        { "path": "result.patch_id", "equals": 12 }
      ],
      "teardown": []
    },
    {
      "id": "install-patch",
      "name": "Install from File with patch_id",
      "steps": [
        {
          "run": "(Get-ChildItem -Path \"<wrapper_path>/latest\" -Force -File | Select-Object -First 1).name",
          "capture_as": "filename"
        },
        {
          "run": "& \"<wrapper_path>/test_auto_patching.exe\" --install --path \"<wrapper_path>/latest/<filename>\" --patch_id <patch_id>",
          "capture_as": "output"
        }
      ],
      "assert": [
        { "path": "result.code",     "equals": 1005 },
        { "path": "result.patch_id", "equals": 12   }
      ],
      "teardown": []
    }
  ]
}
```

**Assert patterns supported:**

| Pattern | Example | Meaning |
|---|---|---|
| Exact value | `{"path": "result.code", "equals": 0}` | Field equals value |
| Boolean | `{"path": "result.is_defunct", "equals": false}` | Boolean comparison |
| Cross-field | `{"path": "result.expected_sha256", "equals_field": "result.sha256"}` | `equals_field` resolves value as a field path |
| Nested path | `{"path": "result.signature.background_patching", "equals": 0}` | Dot-notation traversal |
| Error path | `{"path": "error.code", "equals": -1030}` | Same traversal, different root |

### 2.2 Robot Framework Integration — Pre-generate Strategy

```
JSON configs
    |
    v
vmforge generate          # Python reads JSON, resolves <vars>, writes .robot files
    |
    v
tests/generated/windows_REG1/
    7zip_x86.robot         # 1 file per product, all <vars> already resolved
    1password.robot
    ...
    |
    v
pabot --processes 14 tests/generated/windows_REG1/
```

All `<var>` tokens resolved at generate time — generated `.robot` files contain literal values only.

### 2.3 Plugin Architecture

```
PlatformPlugin (abstract)       ExecutorPlugin (abstract)
├── VspherePlatform              ├── PowershellExecutor
└── SshDirectPlatform            └── SshExecutor

Registered by name in environment config:
  "platform": "vsphere"    -> VspherePlatform
  "executor": "powershell" -> PowershellExecutor
```

### 2.4 Test Isolation

Every test case starts with a **snapshot revert** before execution. Each environment defines its snapshot name (`"snapshot": "automation"`). This eliminates dirty state carryover — a known issue in the original Ruby implementation where VM state was shared between test cases.

### 2.5 Connection Config

Platform credentials live in `vmforge/platform.cfg` (gitignored), separate from JSON test configs:

```ini
[vsphere]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443

[ssh_direct]
# Per-environment — host/user/password passed via environment vars or env.vars
```

Environment variables override the file (for CI/CD):
```
VMFORGE_VCENTER_HOST, VMFORGE_VCENTER_USER, VMFORGE_VCENTER_PASSWORD
```

This keeps credentials out of JSON configs and out of version control.

### 2.6 Dry-Run Mode

`vmforge run --dry-run` validates configs and generates `.robot` files but does **not** connect to vSphere or execute commands. Robot Framework's `--dryrun` flag is passed through — all keyword calls are syntax-checked without executing. Useful for CI validation without VM access.

---

## 3. Framework Name & CLI

**Name**: VMForge  
**Package**: `vmforge`

```bash
vmforge validate configs/windows/7zip_x86.json   # validate config, no VM needed
vmforge validate configs/windows/                 # validate entire folder
vmforge generate --platform windows --tag REG1    # produce .robot files only
vmforge run      --platform windows --tag REG1    # generate + run via pabot
vmforge run      --platform linux
vmforge run      --platform windows --tag REG1 --processes 10
vmforge run      --platform windows --tag REG1 --test download-latest  # filter by test ID
vmforge run      --platform windows --dry-run                          # validate + generate, no real VMs
vmforge report   --format excel --output reports/result.xlsx
vmforge migrate  --input path/to/old_json/ --output configs/windows/
```

---

## 4. Scope

**In scope (Windows + Linux first):**
- JSON config loading, validation, variable resolution
- vSphere platform plugin (clone/revert/teardown)
- SSH direct platform plugin (Linux without hypervisor)
- PowerShell executor (Windows via vSphere GuestOps)
- SSH executor (Linux via paramiko)
- Robot Framework .robot generator (1 file per product)
- Parallel execution via `pabot`
- Robot HTML/XML report + JUnit XML for CI/CD
- Excel report (ported from `vuln_automation/gen_patching_test_report/`)
- Migration tool: old JSON schema → new JSON schema
- Dry-run / validate without real VMs

**Out of scope (future):**
- macOS (plugin architecture supports adding it)
- Proxmox platform
- Web dashboard
- Jira integration

---

## 5. Relationship to Existing Code

| Existing module | Role in VMForge |
|---|---|
| `vmkit/vsphere/` | Reused as vSphere platform plugin backend |
| `vmkit/ssh/ssh_vm.py` | Reused as SSH executor backend |
| `vuln_automation/gen_patching_test_report/` | Ported as Excel reporter |
| `vuln_automation/src/test/resources/TestConfig/` | Source data for migration tool |

VMForge is the **orchestration layer** above `vmkit/` — it does not re-implement VM management.
