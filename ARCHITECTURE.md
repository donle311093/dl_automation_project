# VMForge -- Architecture

## 1. Layer Diagram

```
+-------------------------------------------------------------------------+
|  CLI  (vmforge run / generate / validate / report / migrate)            |
+-------------------------------------------------------------------------+
          |                    |                    |
          v                    v                    v
+------------------+  +------------------+  +------------------+
|  Config Layer    |  |  Generator       |  |  Reporter        |
|  JSON loader     |  |  .robot builder  |  |  Excel / JUnit   |
|  Pydantic v2     |  |  var resolver    |  |  Robot HTML      |
+------------------+  +------------------+  +------------------+
          |                    |
          |                    v
          |          +------------------+
          |          |  Robot Runner    |
          |          |  pabot parallel  |
          |          +------------------+
          |                    |
          v                    v
+-------------------------------------------------------------------------+
|  Plugin Layer                                                           |
|  +------------------------+     +------------------------------+        |
|  |  Platform Plugins      |     |  Executor Plugins            |        |
|  |  VspherePlatform       |     |  PowershellExecutor          |        |
|  |  SshDirectPlatform     |     |  SshExecutor                 |        |
|  +------------------------+     +------------------------------+        |
+-------------------------------------------------------------------------+
          |                                   |
          v                                   v
+---------------------+           +-------------------------+
|  automation_        |           |  automation_            |
|  framework/vsphere/ |           |  framework/ssh/         |
+---------------------+           +-------------------------+
```

---

## 2. Directory Structure

```
vmforge/
|-- framework/
|   |-- core/
|   |   |-- schema/
|   |   |   |-- models.py          # Pydantic v2: ProductConfig, Environment, TestCase, Step
|   |   |   |-- loader.py          # JSON -> ProductConfig with full validation
|   |   |   +-- resolver.py        # <var> resolution: product.vars + env.vars + captured
|   |   |-- lifecycle/
|   |   |   +-- vm_pool.py         # Semaphore-based VM pool per template
|   |   +-- result/
|   |       +-- models.py          # TestResult, StepResult, AssertResult
|   |
|   |-- plugins/
|   |   |-- base.py                # Abstract PlatformPlugin, ExecutorPlugin
|   |   |-- registry.py            # name -> class mapping
|   |   |-- platforms/
|   |   |   |-- vsphere.py         # VspherePlatform: clone, revert, teardown
|   |   |   +-- ssh_direct.py      # SshDirectPlatform: SSH without hypervisor
|   |   +-- executors/
|   |       |-- powershell.py      # PowershellExecutor: PS via vSphere GuestOps
|   |       +-- ssh.py             # SshExecutor: bash via paramiko
|   |
|   |-- robot/
|   |   |-- generator/
|   |   |   |-- suite_builder.py   # ProductConfig -> list[RobotTestCase]
|   |   |   +-- renderer.py        # list[RobotTestCase] -> .robot file text
|   |   +-- keywords/
|   |       +-- VmForgeKeywords.py # All keywords: VM lifecycle + Execute + Assert (single class)
|   |
|   +-- reporters/
|       |-- base.py                # Abstract Reporter
|       |-- excel.py               # ExcelReporter (ported from gen_patching_test_report)
|       +-- junit.py               # JUnit XML via Robot --xunit
|
|-- configs/                       # New-schema JSON configs
|   |-- windows/
|   +-- linux/
|
|-- platform.cfg.example           # Connection config template (actual .cfg is gitignored)
|
|-- tests/
|   |-- generated/                 # Auto-generated .robot files (gitignore)
|   |   |-- windows_REG1/
|   |   +-- linux/
|   +-- unit/
|
|-- migrate/
|   +-- json_to_new_schema.py      # Old schema -> new schema converter
|
|-- reports/                       # Run output (gitignore)
|
|-- cli.py
+-- pyproject.toml
```

---

## 3. Core Components

### 3.1 Schema Models (framework/core/schema/models.py)

```python
from pydantic import BaseModel, Field

class Step(BaseModel):
    run: str
    capture_as: str | None = None   # output stored as named var for next steps

class TestCase(BaseModel):
    id: str
    name: str
    setup: list[str] = []
    steps: list[Step] = []
    assert_: dict = Field(default_factory=dict, alias="assert")
    teardown: list[str] = []        # always runs, even if assert fails

class Environment(BaseModel):
    id: str
    template: str
    snapshot: str = "automation"
    platform: str                   # "vsphere" | "ssh_direct"
    executor: str                   # "powershell" | "ssh"
    tags: list[str] = []
    vars: dict[str, str | int] = {}
    run_tests: list[str]

class ProductConfig(BaseModel):
    product: dict                   # id, name, signature
    vars: dict[str, str | int] = {}
    environments: list[Environment]
    tests: list[TestCase]

    def get_test(self, test_id: str) -> TestCase:
        return next(t for t in self.tests if t.id == test_id)

    def build_var_context(self, env: Environment) -> dict[str, str]:
        ctx: dict = {}
        ctx.update(self.product)    # signature, id, name
        ctx.update(self.vars)       # product-level
        ctx.update(env.vars)        # env-level override
        return {k: str(v) for k, v in ctx.items()}
```

### 3.2 Variable Resolver (framework/core/schema/resolver.py)

Scoping order (later overrides earlier):
```
product fields  ->  product.vars  ->  env.vars  ->  captured vars (step runtime)
```

```python
import re

def resolve(command: str, context: dict[str, str]) -> str:
    def replace(match):
        key = match.group(1)
        return context.get(key, match.group(0))  # keep <var> intact if not found
    return re.sub(r'<([^>]+)>', replace, command)
```

Unresolved tokens are left intact -- visible as diagnostic signal, not silently empty.

### 3.3 Plugin Interfaces (framework/plugins/base.py)

```python
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
    def clone_and_snapshot(self, template: str, snapshot: str) -> VMHandle:
        """Clone template from snapshot, create vmforge-base snapshot on clone."""
        ...

    @abstractmethod
    def revert_snapshot(self, snapshot: str = "vmforge-base") -> None:
        """Revert clone to clean state — called before each test."""
        ...

    @abstractmethod
    def teardown(self, vm: VMHandle) -> None:
        """Delete clone — called once after entire suite."""
        ...

class ExecutorPlugin(ABC):
    @abstractmethod
    def run(self, vm: VMHandle, command: str) -> CommandResult: ...
```

Plugin registry (framework/plugins/registry.py):
```python
PLATFORM_REGISTRY: dict[str, type[PlatformPlugin]] = {
    "vsphere":    VspherePlatform,
    "ssh_direct": SshDirectPlatform,
}
EXECUTOR_REGISTRY: dict[str, type[ExecutorPlugin]] = {
    "powershell": PowershellExecutor,
    "ssh":        SshExecutor,
}
```

vSphere platform wraps vmkit:
```python
class VspherePlatform(PlatformPlugin):
    def __init__(self):
        self._mgr = VSphereManager()  # from vmkit/vsphere/

    def clone_and_revert(self, template: str, snapshot: str) -> VMHandle:
        vm = self._mgr.clone_vm(template)
        vm.revert_to_snapshot(snapshot)
        return VMHandle(vm_id=vm.name, template=template, platform="vsphere")

    def teardown(self, vm: VMHandle):
        self._mgr.delete_vm(vm.vm_id)
```

### 3.4 Robot Generator (framework/robot/generator/)

suite_builder.py resolves all vars at build time and handles capture_as chaining:

```python
@dataclass
class AssertItem:
    path: str
    equals: Any | None = None              # exact value check
    equals_field: str | None = None        # cross-field check

@dataclass
class RobotSuite:
    """One .robot file — one product × one environment."""
    product_id: str
    env_id: str
    platform: str                          # injected into Library import in Settings
    executor: str
    template: str
    snapshot: str                          # "automation" — used for cloning
    test_cases: list["RobotTestCase"]

@dataclass
class RobotTestCase:
    name: str                              # "7zip_x86 :: win10-x86 :: download-latest"
    tags: list[str]                        # ["REG1", "7zip_x86"]
    step_lines: list[tuple[str|None, str]] # (capture_var | None, resolved_cmd)
    assert_items: list[AssertItem]

def build_test_case(config, env, test) -> RobotTestCase:
    ctx = config.build_var_context(env)
    captured: dict[str, str] = {}
    step_lines = []

    for step in test.steps:
        cmd = resolve(step.run, {**ctx, **captured})
        step_lines.append((step.capture_as, cmd))
        if step.capture_as:
            captured[step.capture_as] = f"${{{step.capture_as}}}"
    ...
```

renderer.py output example:
```robot
*** Settings ***
Library          vmforge.framework.robot.keywords.VmForgeKeywords    platform=vsphere    executor=powershell
Suite Setup      Clone VM    windows-10-86    automation
Suite Teardown   Teardown VM
Test Setup       Revert Snapshot    vmforge-base

*** Test Cases ***

7zip_x86 :: win10-x86 :: download-latest
    [Tags]    REG1    7zip_x86
    Execute PS    & New-Item -ItemType Directory -Force -Path "C:/Users/Admin/Desktop/wrapper/latest"
    ${output}=    Execute PS    & "C:/Users/Admin/Desktop/wrapper/test_auto_patching.exe" --sig 3112 --download 2
    Check Field    ${output}    result.code      0
    Check Field    ${output}    result.patch_id  12

7zip_x86 :: win10-x86 :: install-patch
    [Tags]    REG1    7zip_x86
    ${filename}=    Execute PS    (Get-ChildItem -Path "C:/wrapper/latest" -File | Select -First 1).name
    ${output}=      Execute PS    & "C:/wrapper/test_auto_patching.exe" --install --path "C:/wrapper/latest/${filename}"
    Check Field    ${output}    result.code    1005
```

- `Suite Setup` clones the VM once from the `automation` snapshot, then creates a `vmforge-base` checkpoint.
- `Test Setup` reverts to `vmforge-base` before each test case (~5–10s, not a full clone).
- `Suite Teardown` deletes the clone after all tests finish.
- `platform` and `executor` args are injected by the renderer from `Environment` config.

### 3.5 Assert Keywords (framework/robot/keywords/AssertKeywords.py)

```python
import json

class AssertKeywords:
    def check_field(self, json_output: str, path: str, expected):
        data = json.loads(json_output)
        actual = self._traverse(data, path)
        assert str(actual) == str(expected), f"{path}: got {actual!r}, expected {expected!r}"

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

---

## 4. Data Flow

### 4.1 Generate Flow

```
vmforge generate --platform windows --tag REG1
    |
JsonLoader.load_all("configs/windows/*.json")  -- Pydantic strict validation
    |
for each ProductConfig:
    for each Environment where tag in env.tags:
        for each test_id in env.run_tests:
            build_test_case(config, env, test) -> RobotTestCase
    renderer.write("tests/generated/windows_REG1/{product_id}.robot", cases)
```

### 4.2 Run Flow

```
vmforge run --platform windows --tag REG1 --processes 14
    |
[generate flow]
    |
pabot --processes 14 tests/generated/windows_REG1/
    |
    +-- worker A: 7zip_x86.robot
    |       [Suite Setup]  Clone VM          -> VspherePlatform.clone_and_snapshot()
    |       [Test Setup]   Revert Snapshot   -> VspherePlatform.revert_snapshot()
    |       Execute PS <cmd>                 -> PowershellExecutor.run(vm, cmd)
    |       Check Field ${output} path val   -> VmForgeKeywords.check_field()
    |       [Suite Teardown] Teardown VM     -> VspherePlatform.teardown()
    |
    +-- worker B: 1password.robot (independent, own VM)
    ...
    |
output/log.html, report.html, junit.xml
```

### 4.3 Migration Flow

```
vmforge migrate --input vuln_automation/src/test/resources/TestConfig/ \
                --output configs/windows/

Mapping:
  old.product_info.* (flat)       -> new.product.{id,name,signature} + new.vars
  old.envs[].template_name        -> new.environments[].template
  old.envs[].used_test_cases      -> new.environments[].run_tests
  old.envs[].tags (string)        -> new.environments[].tags (list)
  old.envs[].online == 1          -> new.environments[].tags += ["online"]
  old.envs[].exe_path             -> new.environments[].vars.exe_path
  old.test_cases[].before         -> new.tests[].setup
  old.test_cases[].tested_function-> new.tests[].steps (with capture_as detection)
  old.test_cases[].after.check    -> new.tests[].assert
  old.test_cases[].after.commands -> new.tests[].teardown

<std_out> detection:
  if steps[i+1].run contains "<std_out>":
      steps[i].capture_as = "std_out"
```

---

## 5. Parallel Execution & Isolation

| Concern | Mechanism |
|---|---|
| Test state isolation | Snapshot revert before every test case ([Setup]) |
| Clone per suite, revert per test | 1 clone per (product × env), snapshot revert between tests |
| vSphere connection safety | Each pabot worker has its own VspherePlatform instance |
| Keyword thread safety | All keyword libraries are stateless per test case |
| Result merging | pabot merges per-worker XML into final output.xml |

Default concurrency: windows=14, linux=12. Override: `vmforge run --processes 8`

---

## 6. Adding a New Platform or Executor

To add macOS support:
1. Create `framework/plugins/executors/applescript.py` implementing `ExecutorPlugin`
2. Register: `EXECUTOR_REGISTRY["applescript"] = ApplescriptExecutor`
3. In JSON config: set `"executor": "applescript"` on the environment

No changes to core, generator, or CLI needed.
