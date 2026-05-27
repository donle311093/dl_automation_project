# VMForge — Implementation Plan

## Overview

| Total Phases | Estimated Duration | Primary Stack |
|---|---|---|
| 8 | 10–15 working days | Python 3.11+, Robot Framework 7, pabot, Pydantic v2 |

**Dependency install:**
```bash
pip install pydantic>=2.0 robotframework>=7.0 robotframework-pabot>=2.0 \
            pyvmomi>=8.0 paramiko>=3.0 typer>=0.12 openpyxl>=3.1
```

---

## Phase 1 — Project Scaffold + Schema & Models

**Duration:** 1–2 days  
**Goal:** Project package structure, Pydantic v2 models, variable resolver

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/pyproject.toml` | Package definition — needed immediately for imports to work |
| `vmforge/platform.cfg.example` | Connection config template (gitignored actual .cfg) |
| `vmforge/framework/__init__.py` | Package marker |
| `vmforge/framework/core/__init__.py` | Package marker |
| `vmforge/framework/core/schema/__init__.py` | Package marker |
| `vmforge/framework/core/result/__init__.py` | Package marker |
| `vmforge/framework/plugins/__init__.py` | Package marker |
| `vmforge/framework/plugins/platforms/__init__.py` | Package marker |
| `vmforge/framework/plugins/executors/__init__.py` | Package marker |
| `vmforge/framework/robot/__init__.py` | Package marker |
| `vmforge/framework/robot/generator/__init__.py` | Package marker |
| `vmforge/framework/robot/keywords/__init__.py` | Package marker |
| `vmforge/framework/reporters/__init__.py` | Package marker |
| `vmforge/framework/lifecycle/__init__.py` | Package marker |
| `vmforge/framework/core/schema/models.py` | `Step`, `TestCase`, `Environment`, `ProductConfig` |
| `vmforge/framework/core/schema/loader.py` | JSON file → `ProductConfig` with validation |
| `vmforge/framework/core/schema/resolver.py` | `<var>` token resolution |
| `vmforge/framework/core/result/models.py` | `TestResult`, `StepResult`, `AssertResult` |
| `vmforge/tests/unit/test_schema.py` | Unit tests for models and resolver |

**1.0 pyproject.toml scaffold (do this first):**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vmforge"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "robotframework>=7.0",
    "robotframework-pabot>=2.0",
    "pyvmomi>=8.0",
    "paramiko>=3.0",
    "typer>=0.12",
    "openpyxl>=3.1",
    "filelock>=3.13",
]

[project.scripts]
vmforge = "vmforge.cli:app"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.0"]
```

```bash
pip install -e ".[dev]"   # run once after scaffold
```

### Tasks

**1.1 Models**
```python
# framework/core/schema/models.py
from pydantic import BaseModel, Field

class Step(BaseModel):
    run: str
    capture_as: str | None = None

class TestCase(BaseModel):
    id: str
    name: str
    setup: list[str] = []
    steps: list[Step] = []
    assert_: dict = Field(default_factory=dict, alias="assert")
    teardown: list[str] = []

class Environment(BaseModel):
    id: str
    template: str
    snapshot: str = "automation"
    platform: str
    executor: str
    tags: list[str] = []
    vars: dict[str, str | int] = {}
    run_tests: list[str]

class ProductConfig(BaseModel):
    product: dict
    vars: dict[str, str | int] = {}
    environments: list[Environment]
    tests: list[TestCase]

    def get_test(self, test_id: str) -> TestCase:
        return next(t for t in self.tests if t.id == test_id)

    def build_var_context(self, env: Environment) -> dict[str, str]:
        ctx: dict = {}
        ctx.update(self.product)
        ctx.update(self.vars)
        ctx.update(env.vars)
        return {k: str(v) for k, v in ctx.items()}
```

**1.2 Loader**
```python
# framework/core/schema/loader.py
import json
from pathlib import Path
from .models import ProductConfig

def load(path: str | Path) -> ProductConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProductConfig.model_validate(data)

def load_all(directory: str | Path) -> list[ProductConfig]:
    return [load(p) for p in sorted(Path(directory).glob("*.json"))]
```

**1.3 Resolver**
```python
# framework/core/schema/resolver.py
import re

def resolve(command: str, context: dict[str, str]) -> str:
    def replace(match):
        key = match.group(1)
        return context.get(key, match.group(0))
    return re.sub(r'<([^>]+)>', replace, command)
```

**Validate:**
```bash
cd vmforge
python -m pytest tests/unit/test_schema.py -v
```

---

## Phase 2 — Plugin System

**Duration:** 2–3 days  
**Goal:** Abstract interfaces + vSphere and SSH direct platform implementations

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/framework/plugins/base.py` | `VMHandle`, `CommandResult`, `PlatformPlugin`, `ExecutorPlugin` |
| `vmforge/framework/plugins/registry.py` | Name → class mapping |
| `vmforge/framework/plugins/platforms/vsphere.py` | `VspherePlatform` wrapping `automation_framework/vsphere/` |
| `vmforge/framework/plugins/platforms/ssh_direct.py` | `SshDirectPlatform` for Linux without hypervisor |
| `vmforge/framework/plugins/executors/powershell.py` | `PowershellExecutor` via vSphere GuestOps |
| `vmforge/framework/plugins/executors/ssh.py` | `SshExecutor` via paramiko |
| `vmforge/tests/unit/test_plugins.py` | Unit tests with mock backends |

### Tasks

**2.1 Abstract base**
```python
# framework/plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class VMHandle:
    vm_id: str
    template: str
    platform: str

@dataclass
class CommandResult:
    stdout: str
    exit_code: int

class PlatformPlugin(ABC):
    @abstractmethod
    def clone_and_revert(self, template: str, snapshot: str) -> VMHandle: ...

    @abstractmethod
    def teardown(self, vm: VMHandle): ...

class ExecutorPlugin(ABC):
    @abstractmethod
    def run(self, vm: VMHandle, command: str) -> CommandResult: ...
```

**2.2 Registry**
```python
# framework/plugins/registry.py
from .platforms.vsphere import VspherePlatform
from .platforms.ssh_direct import SshDirectPlatform
from .executors.powershell import PowershellExecutor
from .executors.ssh import SshExecutor

PLATFORM_REGISTRY: dict[str, type] = {
    "vsphere":    VspherePlatform,
    "ssh_direct": SshDirectPlatform,
}
EXECUTOR_REGISTRY: dict[str, type] = {
    "powershell": PowershellExecutor,
    "ssh":        SshExecutor,
}
```

**2.3 VspherePlatform**
```python
# framework/plugins/platforms/vsphere.py
import sys
sys.path.insert(0, str(Path(__file__).parents[5]))  # reach automation_framework/
from automation_framework.vsphere.vsphere_manager import VSphereManager

class VspherePlatform(PlatformPlugin):
    def __init__(self):
        self._mgr = VSphereManager()

    def clone_and_revert(self, template: str, snapshot: str) -> VMHandle:
        vm = self._mgr.clone_vm(template)
        vm.revert_to_snapshot(snapshot)
        return VMHandle(vm_id=vm.name, template=template, platform="vsphere")

    def teardown(self, vm: VMHandle):
        self._mgr.delete_vm(vm.vm_id)
```

**2.4 SshDirectPlatform**  
Connects via SSH, no snapshot revert — suitable for pre-provisioned Linux VMs.
```python
class SshDirectPlatform(PlatformPlugin):
    def clone_and_revert(self, template: str, snapshot: str) -> VMHandle:
        # No cloning; template is treated as a hostname/IP
        return VMHandle(vm_id=template, template=template, platform="ssh_direct")

    def teardown(self, vm: VMHandle):
        pass  # no provisioned VM to delete
```

**Validate:**
```bash
python -m pytest tests/unit/test_plugins.py -v
```

---

## Phase 3 — Robot Generator

**Duration:** 2–3 days  
**Goal:** `ProductConfig` → `.robot` file text with all `<var>` tokens resolved at build time

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/framework/robot/generator/suite_builder.py` | `ProductConfig` + `Environment` + `TestCase` → `RobotTestCase` |
| `vmforge/framework/robot/generator/renderer.py` | `list[RobotTestCase]` → `.robot` file text |
| `vmforge/tests/unit/test_generator.py` | Snapshot test: known JSON → expected .robot text |

### Tasks

**3.1 suite_builder.py**
```python
from dataclasses import dataclass, field
from ...core.schema.resolver import resolve

@dataclass
class RobotTestCase:
    name: str
    tags: list[str]
    template: str
    snapshot: str
    setup_lines: list[str]
    step_lines: list[tuple[str | None, str]]  # (capture_var, resolved_cmd)
    assert_items: list[tuple[str, str]]       # (json_path, expected)
    teardown_lines: list[str]

def build_test_case(config, env, test) -> RobotTestCase:
    ctx = config.build_var_context(env)
    captured: dict[str, str] = {}
    step_lines = []

    for step in test.steps:
        cmd = resolve(step.run, {**ctx, **captured})
        step_lines.append((step.capture_as, cmd))
        if step.capture_as:
            captured[step.capture_as] = f"${{{step.capture_as}}}"

    return RobotTestCase(
        name=f"{config.product['id']} :: {env.id} :: {test.id}",
        tags=env.tags + [config.product['id']],
        template=env.template,
        snapshot=env.snapshot,
        setup_lines=[resolve(cmd, ctx) for cmd in test.setup],
        step_lines=step_lines,
        assert_items=list(test.assert_.items()),
        teardown_lines=[resolve(cmd, ctx) for cmd in test.teardown],
    )
```

**3.2 renderer.py**  
Outputs valid `.robot` syntax with proper indentation (4-space). Each `capture_as` step emits `${varname}=    Keyword    args`.

**3.3 generate command integration**  
```python
# Wired in Phase 8 CLI, but test standalone:
configs = load_all("configs/windows/")
for cfg in configs:
    for env in cfg.environments:
        if "REG1" in env.tags:
            cases = [build_test_case(cfg, env, cfg.get_test(t)) for t in env.run_tests]
            robot_text = render(cases)
            out_path = Path(f"tests/generated/windows_REG1/{cfg.product['id']}.robot")
            out_path.write_text(robot_text)
```

**Validate:**
```bash
python -m pytest tests/unit/test_generator.py -v
# Visual check: open tests/generated/windows_REG1/7zip_x86_msi.robot
```

---

## Phase 4 — Robot Keyword Libraries

**Duration:** 1–2 days  
**Goal:** Single unified keyword library that Robot Framework calls during test execution

### Design Note

`VmKeywords`, `ExecKeywords`, and `AssertKeywords` are **merged into one class** `VmForgeKeywords`. This avoids the shared-state problem where `ExecutorPlugin` and `self._vm` would need to be accessible across separate class instances in the same Robot test. Robot Framework's `ROBOT_LIBRARY_SCOPE = "TEST"` gives each test its own instance.

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/framework/robot/keywords/VmForgeKeywords.py` | All keywords: VM lifecycle + Execute + Assert |

### Tasks

**4.1 VmForgeKeywords.py**
```python
import json
import re
from robot.api.deco import keyword
from ...plugins.registry import PLATFORM_REGISTRY, EXECUTOR_REGISTRY

class VmForgeKeywords:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self, platform: str, executor: str):
        self._platform = PLATFORM_REGISTRY[platform]()
        self._executor = EXECUTOR_REGISTRY[executor]()
        self._vm = None

    # --- VM Lifecycle ---

    @keyword("Clone And Revert VM")
    def clone_and_revert_vm(self, template: str, snapshot: str = "automation"):
        self._vm = self._platform.clone_and_revert(template, snapshot)

    @keyword("Teardown VM")
    def teardown_vm(self, template: str = ""):
        if self._vm:
            self._platform.teardown(self._vm)
            self._vm = None

    # --- Executors ---

    @keyword("Execute PS")
    def execute_ps(self, command: str) -> str:
        result = self._executor.run(self._vm, command)
        if result.exit_code != 0:
            raise AssertionError(f"Command failed (exit {result.exit_code}): {command}")
        return result.stdout

    @keyword("Execute SSH")
    def execute_ssh(self, command: str) -> str:
        return self._executor.run(self._vm, command).stdout

    # --- Assertions ---

    @keyword("Check Field")
    def check_field(self, json_output: str, path: str, expected):
        data = json.loads(json_output)
        actual = self._traverse(data, path)
        # "=field.path" means cross-field comparison
        if isinstance(expected, str) and expected.startswith("="):
            expected = self._traverse(data, expected[1:])
        assert str(actual) == str(expected), \
            f"{path}: got {actual!r}, expected {expected!r}"

    @keyword("Check Fields Equal")
    def check_fields_equal(self, json_output: str, path1: str, path2: str):
        data = json.loads(json_output)
        v1, v2 = self._traverse(data, path1), self._traverse(data, path2)
        assert v1 == v2, f"{path1} ({v1!r}) != {path2} ({v2!r})"

    def _traverse(self, data, path: str):
        for key in path.split("."):
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data
```

The renderer generates `Library    vmforge.framework.robot.keywords.VmForgeKeywords    platform=vsphere    executor=powershell` in the `*** Settings ***` section of each `.robot` file, using the `Environment.platform` and `Environment.executor` values.

**Validate:**
```bash
# Dry-run against generated .robot (no real VM needed)
robot --dryrun tests/generated/windows_REG1/7zip_x86_msi.robot
```

---

## Phase 5 — Parallel Execution

**Duration:** 1 day  
**Goal:** Wire `pabot` for concurrent per-product test execution

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/framework/lifecycle/vm_pool.py` | Semaphore-based VM pool per template |
| `vmforge/pabot.ini` | Default pabot settings |

### Tasks

**5.1 vm_pool.py**

`threading.Semaphore` does NOT work with pabot's multi-process model — each `--processes` worker is a separate OS process. Use `filelock` (cross-process file-based locking) instead:

```python
import filelock
from pathlib import Path

_LOCK_DIR = Path("/tmp/vmforge_locks")

class VmPool:
    """Limits concurrent VMs cloned from the same template (cross-process safe)."""

    @staticmethod
    def _lock_path(template: str) -> Path:
        _LOCK_DIR.mkdir(exist_ok=True)
        safe = template.replace("/", "_").replace("\\", "_")
        return _LOCK_DIR / f"{safe}.lock"

    @classmethod
    def acquire(cls, template: str) -> filelock.FileLock:
        lock = filelock.FileLock(cls._lock_path(template))
        lock.acquire()
        return lock  # caller must call lock.release() in teardown

    @classmethod
    def release(cls, lock: filelock.FileLock):
        lock.release()
```

Add `filelock>=3.13` to `pyproject.toml` dependencies (already included in Phase 1 scaffold).

**5.2 pabot.ini**
```ini
[pabot]
processes=14
ordering=parallel
```

**5.3 Run command**
```bash
pabot --processes 14 --outputdir reports/ tests/generated/windows_REG1/
```

Each pabot worker gets its own `VmKeywords` instance → own `VspherePlatform` instance → own vSphere connection. No shared state.

**Validate:**
```bash
pabot --dryrun --processes 4 tests/generated/windows_REG1/
```

---

## Phase 6 — Reporting

**Duration:** 1–2 days  
**Goal:** Excel report (ported from `vuln_automation/gen_patching_test_report/`) + JUnit XML

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/framework/reporters/base.py` | `Reporter` abstract class |
| `vmforge/framework/reporters/excel.py` | `ExcelReporter` using openpyxl |
| `vmforge/framework/reporters/junit.py` | `JUnitReporter` — thin wrapper around Robot `--xunit` |

### Tasks

**6.1 Reporter interface**
```python
from abc import ABC, abstractmethod

class Reporter(ABC):
    @abstractmethod
    def generate(self, output_xml: str, output_path: str): ...
```

**6.2 ExcelReporter**  
Parse Robot `output.xml` → openpyxl workbook with columns:
- Product, Environment, Test ID, Test Name, Status, Duration, Failure Message

Port styling and sheet structure from `vuln_automation/gen_patching_test_report/`.

**6.3 JUnit**  
Robot Framework natively supports `--xunit junit.xml`. `JUnitReporter` just calls:
```python
subprocess.run(["rebot", "--xunit", output_path, "reports/output.xml"])
```

**Validate:**
```bash
vmforge report --format excel --output reports/result.xlsx
# Open result.xlsx and verify columns + data
```

---

## Phase 7 — Migration Tool

**Duration:** 1 day  
**Goal:** Convert 700 old-schema JSON files to new VMForge schema automatically

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/migrate/json_to_new_schema.py` | Old → new schema converter |
| `vmforge/tests/unit/test_migrate.py` | Round-trip test: old JSON → new JSON validates cleanly |

### Migration Mapping

| Old field | New field | Notes |
|---|---|---|
| `product_info.*` (flat) | `product.{id,name,signature}` + `vars` | Split by type |
| `envs[].template_name` | `environments[].template` | Rename |
| `envs[].used_test_cases` | `environments[].run_tests` | Rename |
| `envs[].tags` (string) | `environments[].tags` (list) | Split on comma |
| `envs[].online == 1` | `environments[].tags += ["online"]` | Flag → tag |
| `envs[].exe_path` | `environments[].vars.exe_path` | Move to vars |
| `test_cases[].before` | `tests[].setup` | Rename |
| `test_cases[].tested_function` | `tests[].steps` | With `capture_as` detection |
| `test_cases[].after.check` | `tests[].assert` | Rename |
| `test_cases[].after.commands` | `tests[].teardown` | Rename |

**`<std_out>` detection logic:**
```python
for i, step in enumerate(steps[:-1]):
    if "<std_out>" in steps[i+1]["run"]:
        step["capture_as"] = "std_out"
```

**Validate:**
```bash
vmforge migrate --input vuln_automation/src/test/resources/TestConfig/ \
                --output configs/windows/
vmforge validate configs/windows/   # all migrated files pass Pydantic validation
```

---

## Phase 8 — CLI & DX

**Duration:** 0.5 day  
**Goal:** Typer-based CLI wiring all commands together

### Files to Create

| File | Purpose |
|---|---|
| `vmforge/cli.py` | Main CLI entrypoint using Typer |
| `vmforge/pyproject.toml` | Package definition, entry point `vmforge = vmforge.cli:app` |

### CLI Commands

```python
import typer
app = typer.Typer()

@app.command()
def validate(path: str):
    """Validate one JSON config or an entire folder."""

@app.command()
def generate(platform: str, tag: str = ""):
    """Generate .robot files without running."""

@app.command()
def run(platform: str, tag: str = "", processes: int = 14):
    """Generate + run via pabot."""

@app.command()
def report(format: str = "excel", output: str = "reports/result.xlsx"):
    """Generate report from last run output."""

@app.command()
def migrate(input: str, output: str):
    """Convert old JSON schema to new VMForge schema."""

if __name__ == "__main__":
    app()
```

**pyproject.toml entry point:**
```toml
[project.scripts]
vmforge = "vmforge.cli:app"
```

**Validate:**
```bash
pip install -e .
vmforge --help
vmforge validate configs/windows/7zip_x86_msi.json
vmforge generate --platform windows --tag REG1
```

---

## Phase Sequence & Dependencies

```
Phase 1 (Schema)
    └─> Phase 2 (Plugins)
            └─> Phase 4 (Keywords)
                    └─> Phase 5 (Parallel)
    └─> Phase 3 (Generator)
            └─> Phase 4 (Keywords)

Phase 1 ─────────────────────────────> Phase 7 (Migration)
Phase 5 ─────────────────────────────> Phase 6 (Reporting)
Phases 1–7 ──────────────────────────> Phase 8 (CLI)
```

Phases 2 and 3 can proceed in parallel after Phase 1 completes.

---

## Full Timeline Estimate

| Phase | Days | Blocking |
|---|---|---|
| 1 – Schema & Models | 1–2 | None |
| 2 – Plugin System | 2–3 | Phase 1 |
| 3 – Robot Generator | 2–3 | Phase 1 |
| 4 – Robot Keywords | 1–2 | Phases 2 + 3 |
| 5 – Parallel Execution | 1 | Phase 4 |
| 6 – Reporting | 1–2 | Phase 5 |
| 7 – Migration Tool | 1 | Phase 1 |
| 8 – CLI & DX | 0.5 | Phases 1–7 |
| **Total** | **10–15** | |

---

## Done Criteria

- [ ] `vmforge validate configs/windows/` passes all 700 migrated configs
- [ ] `vmforge generate --platform windows --tag REG1` produces one `.robot` per product
- [ ] `robot --dryrun` on generated files reports 0 errors
- [ ] `pabot --dryrun --processes 4` on generated suite completes cleanly
- [ ] `vmforge migrate` round-trip: migrated JSON validates with Pydantic
- [ ] `vmforge report --format excel` produces valid `.xlsx`
- [ ] All unit tests pass: `python -m pytest vmforge/tests/unit/ -v`
