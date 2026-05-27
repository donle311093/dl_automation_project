# Review DESIGN_PLAN.md / IMPLEMENT_PLAN.md / ARCHITECTURE.md

Tôi đã đọc kỹ cả 3 docs. Dưới đây là review theo từng nhóm vấn đề — ưu tiên những điểm sẽ block hoặc gây đau khi implement.

---

## A. Những điểm BẤT HỢP LÝ / có rủi ro cao

### A1. `VspherePlatform.clone_and_revert()` — sai semantic với vsphere
Trong ARCHITECTURE.md và IMPLEMENT_PLAN.md §2.3:

```python
self._mgr = VSphereManager()
vm = self._mgr.clone_vm(template)
vm.revert_to_snapshot(snapshot)
```

Vấn đề:
1. vsphere_manager.py không có method `clone_vm(template)` trả về VM trực tiếp. Pattern thực tế là `get_vm()` rồi gọi `vm.clone_with_config(CloneConfig)` (xem CLAUDE.md).
2. Pattern đúng phải là: **find template VM → clone từ snapshot → power on → đợi IP → revert** (nếu revert), hoặc đơn giản hơn là **linked clone từ snapshot có sẵn**. Snapshot `automation` phải tồn tại trên template, không phải trên clone.
3. `VSphereManager()` cần context manager (`with ... as mgr`) — connection lifecycle bị bỏ qua trong plugin.
4. `vm.name` chưa chắc là VM ID dùng được để lookup lại sau (ID phải là MoRef như `vm-1234`).

**Đề xuất sửa:**
```python
class VspherePlatform(PlatformPlugin):
    def __init__(self, cfg):
        self._mgr = HypervisorFactory.create("vsphere", cfg)
        self._mgr.connect()  # hoặc dùng __enter__/__exit__ trong lifecycle

    def clone_and_revert(self, template: str, snapshot: str) -> VMHandle:
        tmpl = self._mgr.get_vm(template)
        clone_cfg = (CloneConfigBuilder()
                     .target_folder("VMForge-Pool")
                     .name(f"vmf-{template}-{uuid4().hex[:8]}")
                     .snapshot(snapshot)        # clone từ snapshot này
                     .power_on(True)
                     .build())
        clone = tmpl.clone_with_config(clone_cfg)
        return VMHandle(vm_id=clone.moref, template=template, platform="vsphere")
```

### A2. `[Setup] Clone And Revert VM` chạy **mỗi test case** — không khả thi production
Một clone vSphere mất 30s–3 phút. Một product có 10 test × 3 env = 30 clones. 700 products → **~10.500 clones**. Ngay cả với pabot 14 processes, batch nhỏ cũng mất nhiều giờ.

**Đây là design decision lớn nhất cần đánh đổi:**

| Strategy | Isolation | Speed | Cost |
|---|---|---|---|
| Clone per test case (hiện tại) | Tuyệt đối | Cực chậm | Cao |
| **Clone per (product × env), revert-to-snapshot per test** | Tốt | Trung bình | Trung bình |
| Clone per env, không revert | Yếu (dirty state) | Nhanh | Thấp |

Đề xuất: **đổi sang strategy 2** — `[Suite Setup]` clone 1 lần cho cả file `.robot`, `[Setup]` chỉ revert snapshot. Đây cũng đúng intent ban đầu (snapshot `automation` trên clone). Cần thêm `snapshot_after_clone` step để tạo snapshot trên clone trước khi chạy test case đầu tiên.

### A3. `VmPool` với `filelock` — chỉ giải quyết được 1/2 vấn đề
IMPLEMENT_PLAN.md §5.1 dùng `filelock` thay `Semaphore` — đúng cho cross-process, **nhưng**:

- `filelock` là mutex (binary lock), không phải counting semaphore. Để giới hạn N concurrent clones từ 1 template, cần **N lock files** hoặc dùng `multiprocessing.BoundedSemaphore` với manager, hoặc một file-based counter (race-prone).
- Hoặc đơn giản hơn: **dùng pabot built-in tag-based scheduling** (`--ordering`) để serialize các test có cùng template, hoặc đặt `--processes` thấp hơn template count.

**Đề xuất:** bỏ `VmPool` ở Phase 5, dùng pabot `--ordering` file để control concurrency per template. Chỉ cần build `VmPool` nếu thực sự đo được bottleneck.

### A4. automation_framework được import qua `sys.path.insert` — fragile
```python
sys.path.insert(0, str(Path(__file__).parents[5]))  # reach automation_framework/
```
- Đếm `parents[5]` cực dễ vỡ khi đổi cấu trúc folder.
- Không hoạt động khi cài qua `pip install -e .`.

**Đề xuất 1 (tốt nhất):** thêm automation_framework thành editable dependency trong `pyproject.toml`:
```toml
dependencies = [
    "automation_framework @ file://${PROJECT_ROOT}/../automation_framework",
    ...
]
```
hoặc gộp automation_framework thành sub-package của `vmforge/` (vmforge/backends/).

**Đề xuất 2:** đặt `vmforge/` ngang hàng với automation_framework, dùng workspace pyproject (PEP 621) hoặc `setup.py` ở root.

### A5. `Environment.template` vs `Environment.id` — không khớp với .robot generated
Trong DESIGN_PLAN.md §2.1:
```json
"environments": [{"id": "win10-x86", "template": "windows-10-86", ...}]
```
Nhưng ARCHITECTURE.md §3.4 generate:
```robot
[Setup]    Clone And Revert VM    windows-10-86    automation
```
→ Đang truyền `template`, không phải `env.id`. OK với keyword, nhưng `[Teardown]` lại nhận `template` → không thể teardown đúng instance đã clone (vì 1 template clone ra N VM khác nhau). **Cần truyền VM handle/ID, không phải template name.**

Sửa: dùng Robot variable để chia sẻ handle:
```robot
[Setup]    ${vm}=    Clone And Revert VM    windows-10-86    automation
           Set Test Variable    ${VM}
[Teardown]    Teardown VM    ${VM}
```

### A6. Assert schema — mất khả năng diễn đạt
`assert: {"result.code": 0}` là dict → **không giữ được thứ tự** và **không thể có 2 assert cùng key**. Schema gốc Ruby cho phép array of checks. Đề xuất dùng list:
```json
"assert": [
  {"path": "result.code", "equals": 0},
  {"path": "result.expected_sha256", "equals_field": "result.sha256"},
  {"path": "result.has_vulnerability", "equals": true}
]
```
Mở đường cho future operators: `contains`, `matches` (regex), `greater_than`, `in_set`...

### A7. `<var>` resolver — không escape, không validate
- Command có literal `<` (ví dụ PowerShell `Get-Content < file`) sẽ bị regex match nhầm.
- Không có cách nào escape `<...>` nếu cần literal.
- Không có validation pass "tất cả `<var>` có resolve được không" trước khi generate → lỗi xuất hiện lúc runtime.

**Đề xuất:**
- Thêm escape sequence (ví dụ `<<` → `<` literal).
- `vmforge validate` phải fail nếu có unresolved tokens trong setup/steps/teardown.

### A8. `PowershellExecutor` qua vSphere GuestOps — không scale
GuestOps API:
- Yêu cầu VMware Tools đang chạy + credentials guest OS.
- Latency cao (~2–5s mỗi call).
- Không stream output — phải poll task + đọc temp file.
- 700 products × dozens of commands → rất chậm.

**Đề xuất:** mặc định nên dùng **WinRM/PSRemoting** (qua `pypsrp`) cho Windows, GuestOps chỉ là fallback khi VM chưa join network. Schema cần thêm field `executor` đã có rồi — nên thêm `winrm` vào registry.

---

## B. Những điểm HỢP LÝ — giữ nguyên

- **Pydantic v2 + schema explicit** ([DESIGN_PLAN §2.1](DESIGN_PLAN.md)): tốt, đặc biệt là tách `capture_as` thay cho magic `<std_out>`.
- **Pre-generate `.robot`** ([DESIGN_PLAN §2.2](DESIGN_PLAN.md)): đúng — debug dễ, đọc được, tận dụng tooling Robot.
- **Plugin registry tách Platform/Executor** ([ARCH §3.3](ARCHITECTURE.md)): clean separation of concerns.
- **`VmForgeKeywords` gộp 1 class với `ROBOT_LIBRARY_SCOPE = "TEST"`** ([IMPLEMENT §4](IMPLEMENT_PLAN.md)): đúng — quyết định này tránh được state-sharing bug.
- **`teardown` luôn chạy** (semantic Robot `[Teardown]` built-in): đúng.
- **Migration mapping table** ([IMPLEMENT §7](IMPLEMENT_PLAN.md)): đầy đủ, có handle edge case `<std_out>`.
- **Variable scoping order** (`product → product.vars → env.vars → captured`): correct.
- **CLI surface với Typer** ([IMPLEMENT §8](IMPLEMENT_PLAN.md)): minimal, đúng các verb cần thiết.

---

## C. Điểm CẦN ĐIỀU CHỈNH NHỎ

| # | Issue | Fix |
|---|---|---|
| C1 | DESIGN §2.5 credentials qua env var — chỉ có vSphere | Add SSH/WinRM credential env vars; document precedence (env > .cfg > prompt). |
| C2 | Phase ordering: Phase 7 (Migration) phụ thuộc Phase 1 nhưng nên chạy **song song** với Phase 2-6 vì có dataset thật để test schema | Move migration tool sớm hơn — sau Phase 1, song song với Phase 2. Validate được schema thật với 700 files giúp catch model bug sớm. |
| C3 | `JUnitReporter` chỉ wrap `rebot --xunit` ([IMPLEMENT §6.3](IMPLEMENT_PLAN.md)) | Không cần class riêng — gọi thẳng `rebot` từ CLI. Bỏ file `junit.py`. |
| C4 | generated trong gitignore — OK, nhưng cần commit 1–2 sample để code review | Add `tests/generated/_examples/` (committed) vs `tests/generated/<runtime>/` (ignored). |
| C5 | `ProductConfig.product` là `dict` (untyped) | Define `class Product(BaseModel)` với `id`, `name`, `signature`. |
| C6 | `Environment.vars` chỉ `dict[str, str \| int]` — thực tế có boolean, float, list | Mở thành `dict[str, Any]`, hoặc define union rộng hơn. |
| C7 | Không có phase nào dành cho logging / observability | Thêm cấu trúc logging (structlog) ở Phase 1; per-run log directory. |
| C8 | Không có concurrency cho `vmforge validate` 700 files | `validate` dùng `multiprocessing.Pool` — quick win. |
| C9 | Snapshot revert idempotency | VM đang power-on → revert phải power-off trước hoặc dùng `revert_to_current_snapshot` với `suppressPowerOn=False`. Cần document hành vi. |
| C10 | Test result correlation | `RobotTestCase.name = "{product}::{env}::{test}"` — pabot worker log không tách được product nếu test name trùng. Add suite-per-product (đang có) + tag scheme `product:7zip_x86`. |

---

## D. Đề xuất MỞ RỘNG (out-of-scope hiện tại nhưng nên thiết kế chừa chỗ)

### D1. **Pre-flight check** trước khi run
```bash
vmforge preflight --platform windows --tag REG1
```
Kiểm tra:
- Tất cả templates tồn tại trên vSphere.
- Snapshots `automation` tồn tại trên mỗi template.
- Connectivity tới vCenter/SSH targets.
- Disk space đủ cho N clones.
- Credentials hợp lệ.

→ Tránh fail giữa chừng sau khi đã clone 10 VM.

### D2. **Resume / retry failed tests**
Robot natively support `--rerunfailed output.xml -o rerun.xml`. CLI wrap:
```bash
vmforge rerun --output reports/last_run/output.xml
```

### D3. **Config inheritance / composition**
700 products có nhiều shared `vars` (`wrapper_path`, `analog_path`...). Đề xuất:
```json
{
  "extends": "_base/windows_common.json",
  "product": {...}
}
```
Resolver merge deep. Giảm ~30% trùng lặp.

### D4. **Schema versioning**
```json
{ "schema_version": "1.0", "product": {...} }
```
Migration tool stamp version. Loader reject version không support → safe upgrade path.

### D5. **Result publishing hooks (plugin)**
```python
class ResultPublisher(ABC):
    def publish(self, run_result: RunResult): ...
```
Implementations: Jira, Slack, Elasticsearch, S3 upload. Đặt sau Phase 6.

### D6. **Test selection DSL**
Hiện tại chỉ filter theo `--tag` và `--test`. Mở rộng:
```bash
vmforge run --select "tag:REG1 AND NOT tag:slow AND product:7zip_*"
```
Mượn syntax pytest `-k` hoặc Robot tag expression có sẵn (`--include "REG1ANDNOTslow"`).

### D7. **Dry-run với mock executor**
Thêm `MockExecutor` đọc fixture responses từ JSON → chạy E2E test của VMForge framework mà không cần infrastructure. Critical cho CI của chính VMForge.

### D8. **Telemetry / run metrics**
Mỗi run emit JSON: total duration, clone time vs execute time vs assert time, failures by category. Giúp identify bottleneck (clone chiếm 80%? executor chiếm 80%?).

### D9. **Snapshot pool / VM warm cache**
Một bước xa hơn của A2: maintain pool N VM đã clone sẵn cho mỗi template, test case chỉ revert snapshot. Khi pool cạn thì clone thêm. Có thể là Phase 9+.

### D10. **Cross-product dependencies**
Test case "install 7zip" có thể là prerequisite cho test case "upgrade 7zip" của product khác. Hiện schema không express được. Thêm field `depends_on` ở env hoặc test level (out-of-scope MVP nhưng cần ghi nhận).

---

## E. Tóm tắt action items (ưu tiên)

| Priority | Item | Phase ảnh hưởng |
|---|---|---|
| P0 | Sửa `VspherePlatform.clone_and_revert` dùng đúng `CloneConfigBuilder` API (A1) | Phase 2 |
| P0 | Đổi clone strategy: clone-per-suite + revert-per-test (A2) | Phase 3+4 |
| P0 | Truyền VM handle giữa Setup/Teardown qua Test Variable (A5) | Phase 3+4 |
| P0 | Đổi `assert` schema sang list of objects (A6) | Phase 1 |
| P0 | Fix automation_framework import path qua pyproject dependency (A4) | Phase 1 |
| P1 | Thêm `vmforge validate` check unresolved `<var>` (A7) | Phase 1 |
| P1 | Thêm `Product` Pydantic model (C5) | Phase 1 |
| P1 | Move migration tool song song với Phase 2 (C2) | Sequencing |
| P1 | Thêm WinRM executor option (A8) | Phase 2 |
| P2 | Pre-flight command (D1) | Sau Phase 8 |
| P2 | Config inheritance `extends` (D3) | Sau Phase 7 |
| P2 | Mock executor cho self-CI (D7) | Sau Phase 4 |
| P3 | Schema versioning (D4), publisher hooks (D5), telemetry (D8) | Roadmap v2 |

Nếu bạn muốn, tôi có thể edit trực tiếp 3 docs để apply các P0/P1 fixes — chỉ cần confirm.