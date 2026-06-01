# VMForge

JSON-driven VM test automation framework. Write test configs in JSON, generate Robot Framework suites, and run them in parallel across multiple VM environments.

## Overview

VMForge turns a structured JSON config into `.robot` suite files and executes them via [pabot](https://github.com/robotframework/pabot) (parallel) or `robot` (single-process). Results can be exported as Excel or JUnit XML.

**Pipeline:**

```
JSON config → validate → generate .robot suites → run (pabot/robot) → report (Excel / JUnit)
```

## Requirements

- Python 3.11+
- Robot Framework 7.0+
- robotframework-pabot 2.0+

## Installation

```bash
pip install .
# or for development:
pip install -e ".[dev]"
```

This installs the `vmforge` CLI entry point.

## CLI Reference

```
vmforge --help
```

### `validate` — check a config file

```bash
vmforge validate configs/windows/7zip_x86.json
```

Parses and validates the JSON config against the VMForge schema. Prints a summary on success, exits non-zero on error.

```
Product : 7-Zip x86 (7zip-x86)
Envs    : 1
  - win10-x86  template=windows-10-86  tests=2
Tests   : 2
OK — config is valid.
```

### `generate` — produce `.robot` suite files

```bash
vmforge generate configs/windows/7zip_x86.json --out-dir suites/
# or an entire directory:
vmforge generate configs/windows/ --out-dir suites/
```

One `.robot` file is written per product × environment combination:

```
suites/7zip-x86__win10-x86.robot
```

### `run` — generate and execute

```bash
# parallel (pabot, default 4 workers):
vmforge run configs/windows/ --out-dir results/

# custom worker count:
vmforge run configs/windows/ --processes 8

# single-process (robot):
vmforge run configs/windows/ --robot
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--out-dir` / `-o` | `results/` | Directory for suites and output files |
| `--processes` / `-p` | `4` | pabot parallel worker count |
| `--robot` / `--pabot` | `--pabot` | Use `robot` instead of `pabot` |

### `report` — generate reports from `output.xml`

```bash
# Excel (default):
vmforge report results/output.xml

# JUnit XML (requires rebot on PATH):
vmforge report results/output.xml --format junit

# Both at once:
vmforge report results/output.xml --format both

# Custom output path:
vmforge report results/output.xml --format excel --out reports/summary.xlsx
```

### `migrate` — convert old-format JSON configs

Converts legacy `vuln_automation` JSON configs to the VMForge schema.

```bash
# Single file:
vmforge migrate old/7zip.json --dst new/7zip.json

# Override product id:
vmforge migrate old/7zip.json --dst new/7zip.json --product-id 7zip-x86

# Entire directory:
vmforge migrate old/ --out-dir new/
```

## Config Schema

```json
{
  "product": {
    "id": "7zip-x86",
    "name": "7-Zip x86",
    "signature": 3112
  },
  "vars": {
    "wrapper_path": "C:/wrapper",
    "patch_id": 12
  },
  "environments": [
    {
      "id": "win10-x86",
      "template": "windows-10-86",
      "snapshot": "automation",
      "platform": "vsphere",
      "executor": "powershell",
      "tags": ["REG1"],
      "vars": { "exe_path": "C:/Program Files/7-Zip/7zFM.exe" },
      "run_tests": ["download-latest", "install-patch"]
    }
  ],
  "tests": [
    {
      "id": "download-latest",
      "name": "Download Latest Installer",
      "setup": ["New-Item -ItemType Directory -Force -Path \"<wrapper_path>/latest\""],
      "steps": [
        {
          "run": "& \"<wrapper_path>/test_auto_patching.exe\" --sig <signature> --download 2",
          "capture_as": "output"
        }
      ],
      "assert": [
        { "path": "result.code",     "equals": 0  },
        { "path": "result.patch_id", "equals": 12 }
      ],
      "teardown": []
    }
  ]
}
```

### Variable substitution

`<var_name>` tokens in `steps[].run`, `setup`, and `teardown` are resolved at suite-generation time from this priority chain:

```
product fields → top-level vars → environment vars
```

### `capture_as`

When a step sets `"capture_as": "some_name"`, the step's stdout is stored as `${some_name}` and can be referenced in subsequent steps via `<some_name>`.

### Assert types

| Form | Meaning |
|---|---|
| `{ "path": "result.code", "equals": 0 }` | Exact value match |
| `{ "path": "result.sha256", "equals_field": "result.expected_sha256" }` | Cross-field comparison |

## Platform Configuration

Copy `platform.cfg.example` to `platform.cfg` (gitignored) and fill in your vSphere credentials:

```ini
[vsphere]
host     = 192.168.1.10
user     = administrator@vsphere.local
password = YourPassword
port     = 443
```

Environment variables override the file — prefix with `VMFORGE_`:

```bash
export VMFORGE_VSPHERE_HOST=192.168.1.10
export VMFORGE_VSPHERE_USER=administrator@vsphere.local
export VMFORGE_VSPHERE_PASSWORD=secret
```

## Project Structure

```
vmforge/
├── framework/
│   ├── cli.py                   # Typer CLI entry point
│   ├── core/
│   │   ├── schema/              # Pydantic models + JSON loader
│   │   └── result/              # Test result models
│   ├── lifecycle/
│   │   └── vm_pool.py           # Parallel VM pool (filelock-based)
│   ├── plugins/
│   │   ├── base.py              # Platform plugin interface
│   │   ├── registry.py          # Plugin discovery & registration
│   │   └── executors/           # powershell, ssh executors
│   ├── reporters/
│   │   ├── excel.py             # openpyxl Excel report
│   │   └── junit.py             # JUnit XML via rebot
│   └── robot/
│       ├── generator/           # suite_builder + Jinja renderer
│       └── keywords/            # VmForgeKeywords Robot library
├── migrate/
│   └── json_to_new_schema.py    # Legacy config migration
├── configs/                     # Example JSON configs
│   ├── windows/
│   └── linux/
├── tests/unit/                  # 288 unit tests
├── pyproject.toml
└── platform.cfg.example
```

## Development

```bash
# Run all tests:
pytest

# Lint:
ruff check .

# Type check:
mypy .

# Format check:
ruff format --check .
```

### Test coverage by module

| Module | Tests |
|---|---|
| `core/schema` | 30 |
| `plugins` | 27 |
| `robot/generator` | 39 |
| `robot/keywords` | 25 |
| `lifecycle/vm_pool` | 17 |
| `reporters` | 37 |
| `migrate` | 59 |
| `cli` | 34 |
| **Total** | **288** |
