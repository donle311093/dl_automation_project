# Architecture: Automation Framework CLI + MCP Server

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        NGƯỜI DÙNG / CI PIPELINE                 │
└──────────────┬──────────────────────────────┬───────────────────┘
               │ terminal                     │ AI agent (Claude)
               ▼                              ▼
┌──────────────────────┐          ┌─────────────────────┐
│      CLI Layer       │          │    MCP Server        │
│  python -m cli       │          │  python -m mcp_server│
│                      │          │  (stdio transport)   │
│  ┌────────────────┐  │          └──────────┬──────────┘
│  │  Auth / Session│  │                     │
│  ├────────────────┤  │                     │
│  │ Manager REPL   │  │          ┌──────────▼──────────┐
│  │   VM REPL      │  │          │    tools.py          │
│  │   Shell REPL   │  │          │  (thin wrappers)     │
│  ├────────────────┤  │          └──────────┬──────────┘
│  │  Output/Render │  │                     │
│  └────────────────┘  │                     │
└──────────┬───────────┘                     │
           │                                 │
           └─────────────┬───────────────────┘
                         │ shared core library
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    automation_framework/core                      │
│                                                                   │
│   IHypervisorManager          IVMManager                         │
│   ─────────────────           ─────────────────────              │
│   connect()                   get_power_status()                 │
│   disconnect()                power_on/off/suspend/reset()       │
│   get_vm()                    get_vm_info()                      │
│   find_vms_in_folder()        get_snapshots()                    │
│   delete_vm()                 create/revert/delete_snapshot()    │
│   get_datastore_info()        login() / execute_command()        │
│                               clone()                            │
│                                                                   │
│   HypervisorFactory.create(platform, config)                     │
└──────────┬──────────────────────────────────────────────────────┘
           │
    ┌──────┴──────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌───────────────┐   ┌──────────────┐   ┌──────────────┐  ...
│   vsphere/    │   │ proxmox_impl/│   │ fusion_impl/ │
│               │   │              │   │              │
│VSphereManager │   │ProxmoxManager│   │FusionManager │
│VSphereVMManager   │ProxmoxVMMgr  │   │FusionVMMgr   │
└───────────────┘   └──────────────┘   └──────────────┘
        │
   pyVmomi (vSphere API)
```

---

## 2. CLI Internal Architecture

```
cli/
│
├── __main__.py ──► main.py
│                     │
│               ┌─────▼──────────────────────────────┐
│               │           main.py                   │
│               │                                     │
│               │  parse_global_args()                │
│               │        │                            │
│               │        ├── --version → print & exit │
│               │        ├── --help    → print & exit │
│               │        │                            │
│               │  dispatch_mode()                    │
│               │        │                            │
│               │        ├── subcommand args present  │
│               │        │   → one_shot_mode()        │
│               │        │                            │
│               │        └── no subcommand            │
│               │            → interactive_mode()     │
│               └─────────────────────────────────────┘
│                         │               │
│                         ▼               ▼
│               ┌──────────────┐  ┌──────────────────┐
│               │  one_shot    │  │  interactive      │
│               │  _mode()     │  │  _mode()          │
│               │              │  │                   │
│               │  parse cmd   │  │  auth() → session │
│               │  execute     │  │  → ManagerREPL    │
│               │  output json │  │    .run_loop()    │
│               │  sys.exit(N) │  │                   │
│               └──────────────┘  └──────────────────┘
│
├── auth.py
│     auth(args) → SessionState
│       1. try env var (VSPHERE_HOST/USER/PASS)
│       2. try --profile file
│       3. try local .config
│       4. interactive prompt
│       5. HypervisorFactory.create() → connect()
│       6. return SessionState
│
├── session.py
│     SessionState:
│       platform: str
│       host: str
│       manager: IHypervisorManager      ← platform connection
│       current_vm: IVMManager | None    ← set khi vào VM REPL
│       guest_user: str | None           ← set sau login
│       guest_pass: str | None
│       ssl_verify: bool
│       debug: bool
│       output_format: str              ← "table" | "json" | "yaml"
│
├── repl_manager.py  ──► ManagerREPL(session)
│     .run_loop()         prompt_toolkit session
│     .cmd_list_vms()     calls session.manager.find_vms_in_folder()
│     .cmd_use()          creates repl_vm.VMREPL(session, vm_name)
│     .cmd_clone()        calls vm.clone() + spinner
│     ...
│
├── repl_vm.py       ──► VMREPL(session, vm_name)
│     .run_loop()         prompt: vsphere/vm[<name>]>
│     .cmd_login()        vm.login(user, pass) → stores in session
│                         → ShellREPL(session, vm).run_loop()
│     .cmd_run()          vm.execute_command() (requires session.guest_user)
│     .cmd_snapshot()     delegates to vm.create/revert/delete_snapshot()
│     ...
│
├── repl_shell.py    ──► ShellREPL(session, vm)
│     .run_loop()         prompt: vsphere/vm[<name>]/shell>
│     .<input>            vm.execute_command(input) → print raw output
│     exit               return to VMREPL
│
├── output.py
│     render(data, format)   → table (rich) | json | yaml
│     spinner(label)         → rich Live spinner với elapsed time
│     confirm(msg)           → "Are you sure? [y/N]"
│     print_error(msg)       → red
│     print_success(msg)     → green
│     print_warning(msg)     → yellow
│
├── batch.py
│     run_script(path, session)
│       → đọc từng dòng .af
│       → bỏ comment (#)
│       → parse và gọi tương ứng ManagerREPL.cmd_*()
│       → dừng nếu lỗi (exit 1)
│
└── completer.py
      VMCompleter(session)
        → get_completions():  VM names, folder names, snapshot names
        → lazy-load: chỉ fetch khi user gõ Tab
```

---

## 3. REPL State Machine

```
                    ┌─────────────┐
                    │    START    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  auth()     │  env var / config / prompt
                    └──────┬──────┘
                    connection fail → print error, exit 3
                           │ ok
                    ┌──────▼──────────────────────────────┐
                    │         Manager REPL                 │
                    │         prompt: vsphere>             │
                    │                                      │
                    │  list-vms, clone, delete, test, ...  │
                    └──┬──────────────────────────────┬────┘
                       │ use <vm>                     │ exit
                       ▼                              ▼
              ┌─────────────────┐             ┌──────────┐
              │    VM REPL      │             │   EXIT   │
              │ vsphere/vm[X]>  │             │ (code 0) │
              │                 │             └──────────┘
              │ start/stop/snap │
              │ info/health/... │
              └──┬──────────┬───┘
                 │ login    │ back
                 ▼          ▼
        ┌───────────────┐  Manager REPL
        │  Shell REPL   │
        │ vsphere/vm[X] │
        │ /shell>       │
        │               │
        │ <any command> │
        └──────┬────────┘
               │ exit
               ▼
            VM REPL

Notes:
- Session timeout xảy ra ở bất kỳ tầng nào
  → auto-reconnect 1 lần → thông báo user
  → nếu fail lần 2 → in lỗi, quay về Manager REPL
- Ctrl+C: hủy lệnh đang gõ, không thoát REPL
- Ctrl+D: tương đương exit, thoát hẳn
```

---

## 4. Auth & Session Flow

```
main.py calls auth(args)
          │
          ├─ 1. Env var? ──────────────────────────────────────── YES ──►┐
          │     VSPHERE_HOST / VSPHERE_USER / VSPHERE_PASS               │
          │                                                               │
          ├─ 2. --profile flag? ──────────────────────────────── YES ──►┤
          │     load ~/.automation_framework/profiles/<n>.config         │
          │                                                               │
          ├─ 3. Local config? ─────────────────────────────────── YES ──►┤
          │     automation_framework/vsphere/.config                     │
          │                                                               │
          └─ 4. Interactive prompt ──────────────────────────────────────►┤
                Platform? Host? User? Pass? Save?                         │
                                                                          │
                                                              ┌───────────▼──────────┐
                                                              │ HypervisorFactory    │
                                                              │   .create(platform,  │
                                                              │    config)           │
                                                              │   .connect()         │
                                                              └───────────┬──────────┘
                                                              fail        │ ok
                                                              exit(3)     │
                                                                 ┌────────▼────────┐
                                                                 │  SessionState   │
                                                                 │  returned to    │
                                                                 │  main.py        │
                                                                 └─────────────────┘
```

---

## 5. Request Data Flow — clone win10-base --to-folder "CI Pool" --name ci-01

```
User input (REPL)
      │
      ▼
repl_manager.py: cmd_clone(args)
      │  parse: vm_name="win10-base", folder=None, to_folder="CI Pool", name="ci-01"
      │
      ├── output.confirm("Are you sure?")  ← nếu --dry-run thì dừng đây
      │
      ├── output.spinner("Cloning ci-01...")
      │
      ├── session.manager.get_vm("win10-base") → VSphereVMManager
      │         calls vsphere/find_vm.py → pyVmomi API → vCenter
      │
      └── vm.clone(target_folder_name="CI Pool", new_vm_name="ci-01", ...)
                calls vsphere/clone_vm.py
                    → build CloneSpec
                    → submit vim.Task (async vSphere task)
                    → poll task status until complete
                    → return bool
      │
      ├── success: output.print_success("Cloned: ci-01")
      │            audit_log.write(timestamp | vsphere | clone | ... | OK)
      │
      └── failure: output.print_error("Clone failed: <reason>")
                   audit_log.write(timestamp | vsphere | clone | ... | FAIL)
```

---

## 6. MCP Server Flow

```
Claude Desktop / AI Agent
      │
      │  stdin (JSON-RPC via MCP protocol)
      ▼
mcp_server/server.py
  mcp = FastMCP("automation-framework")
      │
      │  tool call: list_vms(folder="CI Pool")
      ▼
mcp_server/tools.py
  @mcp.tool()
  def list_vms(folder: str = None):
      │
      │  session được khởi tạo 1 lần khi server start
      │  load credentials: env var → config file
      │
      └── manager.find_vms_in_folder(folder)
              → vsphere/find_vm.py → pyVmomi → vCenter
              → return list[dict]
      │
      stdout (JSON-RPC response)
      ▼
Claude Desktop / AI Agent
```

---

## 7. Module Dependency Map

```
cli/main.py
    ├── cli/auth.py
    │       └── core/factory.py
    │               ├── vsphere/vsphere_manager.py
    │               ├── proxmox_impl/...
    │               └── fusion_impl/...
    │
    ├── cli/session.py          (data class, no deps)
    │
    ├── cli/repl_manager.py
    │       ├── cli/session.py
    │       ├── cli/output.py
    │       ├── cli/completer.py
    │       ├── cli/repl_vm.py  ──► cli/repl_shell.py
    │       └── cli/batch.py
    │
    └── cli/output.py
            ├── rich             (external)
            └── prompt_toolkit   (external)

mcp_server/server.py
    ├── mcp_server/tools.py
    │       └── core/factory.py  (same as CLI)
    └── mcp                      (external SDK)
```

---

## 8. Xử Lý Lỗi

```
Tầng         Lỗi                           Hành vi
──────────   ───────────────────────────   ─────────────────────────────────────
auth         Connection refused            print_error + exit(3)
auth         SSL cert invalid              print_error + hint "--no-verify-ssl"
             (không có --no-verify-ssl)
REPL         Session timeout (mid-session) auto-reconnect 1 lần → warn user
             reconnect fail               print_error, quay về Manager REPL
REPL         VM not found                 print_error, tiếp tục REPL
REPL         Operation fail               print_error + reason, tiếp tục REPL
One-shot     Any error                    print_error to stderr + exit(1)
One-shot     Auth error                   print_error to stderr + exit(3)
Batch (.af)  Any line fail                print_error + dừng script + exit(1)
MCP tool     Any error                    return {"success": false, "message": ...}
```

---

## 9. Extension Points — Thêm Platform Mới

Để thêm platform mới (ví dụ: Proxmox vào CLI), chỉ cần:

```
1. Implement IHypervisorManager + IVMManager
   (đã có sẵn: proxmox_impl/, fusion_impl/)

2. Register vào HypervisorFactory:
   core/factory.py:
     REGISTRY["proxmox"] = lambda cfg: ProxmoxManager(cfg)

3. Thêm env var prefix vào auth.py:
   PROXMOX_HOST / PROXMOX_USER / PROXMOX_PASS / PROXMOX_NODE

4. CLI và MCP Server tự động hỗ trợ platform mới —
   không cần sửa REPL hay tools.py vì tất cả gọi qua interface.
```

Không có platform-specific code nào trong `cli/` hay `mcp_server/`.

---

## 10. File & Config Locations

```
~/.automation_framework/
├── profiles/
│   ├── lab.config          ← --profile lab
│   └── prod.config         ← --profile prod
├── history                 ← REPL command history (prompt_toolkit)
└── audit.log               ← append-only audit log

automation_framework/
├── vsphere/.config         ← local dev config (gitignored)
└── tests/
    ├── output.xml          ← Robot Framework output
    ├── log.html
    └── report.html

Config file format (INI):
  [vcenter]
  host       = 10.40.x.x
  user       = administrator@vsphere.local
  password   = xxxxxxxx
  port       = 443
  ssl_verify = false

Audit log format (append-only, one line per action):
  2026-05-26T10:30:01 | vsphere | clone     | vm=win10-base → CI Pool/ci-01 | OK
  2026-05-26T10:31:45 | vsphere | delete-vm | folder=CI Pool vm=ci-01       | OK
  2026-05-26T10:32:00 | vsphere | run-cmd   | vm=ci-01 cmd="ipconfig"       | OK
```

---

## 11. Design Decisions

| Quyết định | Lý do |
|---|---|
| Ba tầng REPL (Manager → VM → Shell) | Phản ánh đúng mô hình quản lý: platform → VM → guest OS. Prompt thay đổi theo tầng giúp user không bị lạc. |
| Shared `SessionState` object | Tránh truyền credentials qua nhiều tầng. REPL, batch, test runner đều đọc từ 1 nguồn duy nhất. |
| MCP transport = stdio | Đơn giản, không cần network, phù hợp Claude Desktop. Nếu cần multi-user thì nâng lên HTTP/SSE. |
| Core library không phụ thuộc CLI | `automation_framework/core/` hoàn toàn độc lập. CLI và MCP Server đều là thin layer bên trên. |
| `IHypervisorManager` interface | CLI/MCP không biết platform nào đang chạy — chỉ gọi qua interface. Thêm platform mới không cần sửa CLI. |
| Exit code 3 riêng cho auth | CI pipeline phân biệt được "lệnh fail" (1) với "không kết nối được" (3) để retry hay alert khác nhau. |
| Auto-reconnect 1 lần | vCenter token expire sau ~30 phút idle. Reconnect im lặng nếu thành công, warn nếu fail. |
| Batch file dừng khi lỗi | Fail-fast: CI script không nên tiếp tục khi 1 bước fail. |
