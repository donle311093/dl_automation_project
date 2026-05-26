"""One-shot (non-interactive) command dispatcher.

Exit code contract:
  0 — success
  1 — runtime error (command failed, VM not found, etc.)
  2 — usage error (bad arguments, unknown command)
  3 — auth / connection error (caught in main.py before reaching here)
"""

import argparse

from cli.output import print_error, print_warning, render, audit
from cli.session import SessionState


def dispatch(tokens: list, session: SessionState) -> int:
    if not tokens:
        print_error("No command specified.")
        return 2

    cmd = tokens[0]
    rest = tokens[1:]

    dispatch_table = {
        "list-vms":       _cmd_list_vms,
        "search":         _cmd_search,
        "info":           _cmd_info,
        "snapshots":      _cmd_snapshots,
        "datastore-info": _cmd_datastore_info,
        "health-check":   _cmd_health_check,
        "clone":          _cmd_clone,
        "delete-vm":      _cmd_delete_vm,
        "vm":             _cmd_vm,
        "test":           _cmd_test,
    }

    handler = dispatch_table.get(cmd)
    if handler is None:
        print_error(f"Unknown command: '{cmd}'. Available: {', '.join(sorted(dispatch_table))}")
        return 2

    try:
        return handler(rest, session)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        print_error(str(e))
        if session.debug:
            import traceback
            traceback.print_exc()
        return 1


# ── Manager-level commands ────────────────────────────────────────────────────

def _cmd_list_vms(rest: list, session: SessionState) -> int:
    p = _parser("list-vms")
    p.add_argument("--folder", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    args, _ = p.parse_known_args(rest)

    vms = session.manager.find_vms_in_folder(args.folder) or []
    page = vms[args.offset: args.offset + args.limit]
    render([{"name": getattr(vm, "name", str(vm))} for vm in page], session.output_format)
    return 0


def _cmd_search(rest: list, session: SessionState) -> int:
    p = _parser("search")
    p.add_argument("keyword")
    args, _ = p.parse_known_args(rest)

    results = session.manager.find_vm_by_name(args.keyword) or []
    rows = [
        {
            "name": r["vm"].name if isinstance(r, dict) else getattr(r, "name", str(r)),
            "folder": r["folder"].name if isinstance(r, dict) and r.get("folder") else "",
        }
        for r in results
    ]
    render(rows, session.output_format)
    return 0


def _cmd_info(rest: list, session: SessionState) -> int:
    p = _parser("info")
    p.add_argument("vm")
    p.add_argument("--folder", default=None)
    args, _ = p.parse_known_args(rest)

    vm = session.manager.get_vm(args.vm, args.folder)
    if vm is None:
        print_error(f"VM '{args.vm}' not found.")
        return 1
    render(vm.get_vm_info(), session.output_format)
    return 0


def _cmd_snapshots(rest: list, session: SessionState) -> int:
    p = _parser("snapshots")
    p.add_argument("vm")
    p.add_argument("--folder", default=None)
    args, _ = p.parse_known_args(rest)

    vm = session.manager.get_vm(args.vm, args.folder)
    if vm is None:
        print_error(f"VM '{args.vm}' not found.")
        return 1
    snaps = vm.get_snapshots() or []
    render([{"name": getattr(s, "name", str(s))} for s in snaps], session.output_format)
    return 0


def _cmd_datastore_info(rest: list, session: SessionState) -> int:
    render(session.manager.get_datastore_info(), session.output_format)
    return 0


def _cmd_health_check(rest: list, session: SessionState) -> int:
    p = _parser("health-check")
    p.add_argument("--folder", default=None)
    args, _ = p.parse_known_args(rest)

    vms = session.manager.find_vms_in_folder(args.folder) or []
    rows = []
    for raw_vm in vms:
        vm_name = getattr(raw_vm, "name", str(raw_vm))
        try:
            vm = session.manager.get_vm(vm_name, args.folder)
            power = vm.get_power_status()
            tools = vm.get_guest_tools_status()
            healthy = power == "poweredOn" and tools == "guestToolsRunning"
            rows.append({"name": vm_name, "power": power, "tools": tools,
                         "healthy": "yes" if healthy else "no"})
        except Exception as e:
            rows.append({"name": vm_name, "power": "?", "tools": "?",
                         "healthy": f"error: {e}"})
    render(rows, session.output_format)
    return 0


def _cmd_clone(rest: list, session: SessionState) -> int:
    p = _parser("clone")
    p.add_argument("vm")
    p.add_argument("new_name")
    p.add_argument("--folder", default=None)
    p.add_argument("--target-folder", default=None)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--cpus", type=int, default=None)
    p.add_argument("--memory", type=int, default=None)
    p.add_argument("--power-on", action="store_true")
    args, _ = p.parse_known_args(rest)

    vm = session.manager.get_vm(args.vm, args.folder)
    if vm is None:
        print_error(f"VM '{args.vm}' not found.")
        return 1
    ok = vm.clone(
        target_folder_name=args.target_folder or args.folder,
        new_vm_name=args.new_name,
        snapshot_name=args.snapshot,
        num_cpus=args.cpus,
        memory_mb=args.memory,
        power_on=args.power_on,
    )
    audit(session, "clone", f"{args.vm} -> {args.new_name}", "OK" if ok else "FAIL")
    if not ok:
        print_error("Clone failed.")
        return 1
    return 0


def _cmd_delete_vm(rest: list, session: SessionState) -> int:
    p = _parser("delete-vm")
    p.add_argument("vm")
    p.add_argument("--folder", required=True)
    args, _ = p.parse_known_args(rest)

    ok = session.manager.delete_vm(args.folder, args.vm)
    audit(session, "delete-vm", f"{args.folder}/{args.vm}", "OK" if ok else "FAIL")
    if not ok:
        print_error("Delete failed.")
        return 1
    return 0


# ── VM-level subcommands  (vm "<name>" [--folder F] <subcmd> [args]) ──────────

def _cmd_vm(rest: list, session: SessionState) -> int:
    p = _parser("vm")
    p.add_argument("vm_name")
    p.add_argument("--folder", default=None)
    args, remaining = p.parse_known_args(rest)

    if not remaining:
        print_error("Specify a VM subcommand: status, start, stop, restart, reset, "
                    "suspend, info, tools-status, health, snapshots, snapshot, "
                    "run, clone, wait-for-status, wait-for-tools")
        return 2

    vm = session.manager.get_vm(args.vm_name, args.folder)
    if vm is None:
        print_error(f"VM '{args.vm_name}' not found.")
        return 1
    subcmd = remaining[0]
    subrest = remaining[1:]

    vm_dispatch = {
        "status":          _vm_status,
        "start":           _vm_start,
        "stop":            _vm_stop,
        "restart":         _vm_restart,
        "reset":           _vm_reset,
        "suspend":         _vm_suspend,
        "info":            _vm_info,
        "tools-status":    _vm_tools_status,
        "health":          _vm_health,
        "snapshots":       _vm_snapshots,
        "snapshot":        _vm_snapshot,
        "run":             _vm_run,
        "clone":           _vm_clone,
        "wait-for-status": _vm_wait_for_status,
        "wait-for-tools":  _vm_wait_for_tools,
    }

    handler = vm_dispatch.get(subcmd)
    if handler is None:
        print_error(f"Unknown VM subcommand: '{subcmd}'")
        return 2

    return handler(subrest, session, vm, args.vm_name)


def _vm_status(rest, session, vm, name) -> int:
    print(vm.get_power_status())
    return 0

def _vm_start(rest, session, vm, name) -> int:
    return 0 if vm.power_on() else 1

def _vm_stop(rest, session, vm, name) -> int:
    return 0 if vm.power_off() else 1

def _vm_restart(rest, session, vm, name) -> int:
    return 0 if vm.reboot() else 1

def _vm_reset(rest, session, vm, name) -> int:
    return 0 if vm.reset() else 1

def _vm_suspend(rest, session, vm, name) -> int:
    return 0 if vm.suspend() else 1

def _vm_info(rest, session, vm, name) -> int:
    render(vm.get_vm_info(), session.output_format)
    return 0

def _vm_tools_status(rest, session, vm, name) -> int:
    print(vm.get_guest_tools_status())
    return 0

def _vm_health(rest, session, vm, name) -> int:
    power = vm.get_power_status()
    tools = vm.get_guest_tools_status()
    healthy = power == "poweredOn" and tools == "guestToolsRunning"
    render({"name": name, "power": power, "tools": tools,
            "healthy": "yes" if healthy else "no"}, session.output_format)
    return 0

def _vm_snapshots(rest, session, vm, name) -> int:
    snaps = vm.get_snapshots() or []
    render([{"name": getattr(s, "name", str(s))} for s in snaps], session.output_format)
    return 0

def _vm_snapshot(rest, session, vm, name) -> int:
    p = _parser("snapshot")
    p.add_argument("subcommand", choices=["create", "revert", "delete"])
    p.add_argument("snap_name", nargs="?", default=None)
    p.add_argument("--description", default="")
    p.add_argument("--memory", action="store_true")
    p.add_argument("--quiesce", action="store_true")
    args, _ = p.parse_known_args(rest)

    if args.subcommand == "create":
        if not args.snap_name:
            print_error("snapshot create requires a name")
            return 2
        ok = vm.create_snapshot(args.snap_name, args.description, args.memory, args.quiesce)
        audit(session, "snapshot-create", f"{name}:{args.snap_name}", "OK" if ok else "FAIL")
        return 0 if ok else 1

    if args.subcommand == "revert":
        ok = (vm.revert_to_snapshot(args.snap_name) if args.snap_name
              else vm.revert_to_current_snapshot())
        audit(session, "snapshot-revert", f"{name}:{args.snap_name or 'current'}",
              "OK" if ok else "FAIL")
        return 0 if ok else 1

    if args.subcommand == "delete":
        if not args.snap_name:
            print_error("snapshot delete requires a name")
            return 2
        ok = vm.delete_snapshot(args.snap_name)
        audit(session, "snapshot-delete", f"{name}:{args.snap_name}", "OK" if ok else "FAIL")
        return 0 if ok else 1

    return 0

def _vm_run(rest, session, vm, name) -> int:
    p = _parser("run")
    p.add_argument("command", nargs=argparse.REMAINDER)
    args, _ = p.parse_known_args(rest)

    user = session.guest_user
    password = session.guest_pass
    if not user or not password:
        print_error("Guest credentials required. Use 'login' in interactive mode or set AF_GUEST_USER / AF_GUEST_PASS env vars.")
        return 1

    if not vm.login(user, password):
        print_error("Guest login failed.")
        return 1
    cmd_str = " ".join(args.command)
    if not cmd_str:
        print_error("Provide a command to run.")
        return 2

    result = vm.execute_command(cmd_str)
    render(result, session.output_format)
    return 0 if (result.get("exit_code") or 0) == 0 else 1

def _vm_clone(rest, session, vm, name) -> int:
    p = _parser("clone")
    p.add_argument("new_name")
    p.add_argument("--target-folder", default=None)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--cpus", type=int, default=None)
    p.add_argument("--memory", type=int, default=None)
    p.add_argument("--power-on", action="store_true")
    args, _ = p.parse_known_args(rest)

    ok = vm.clone(args.target_folder, args.new_name, args.snapshot,
                  num_cpus=args.cpus, memory_mb=args.memory, power_on=args.power_on)
    audit(session, "clone", f"{name} -> {args.new_name}", "OK" if ok else "FAIL")
    return 0 if ok else 1

def _vm_wait_for_status(rest, session, vm, name) -> int:
    import time
    p = _parser("wait-for-status")
    p.add_argument("target", choices=["on", "off"])
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--interval", type=int, default=5)
    args, _ = p.parse_known_args(rest)

    target_status = "poweredOn" if args.target == "on" else "poweredOff"
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if vm.get_power_status() == target_status:
            return 0
        time.sleep(args.interval)
    print_error(f"Timeout: VM not '{target_status}' after {args.timeout}s")
    return 1

def _vm_wait_for_tools(rest, session, vm, name) -> int:
    import time
    p = _parser("wait-for-tools")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--interval", type=int, default=10)
    args, _ = p.parse_known_args(rest)

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if vm.get_guest_tools_status() == "guestToolsRunning":
            return 0
        time.sleep(args.interval)
    print_error(f"Timeout: tools not running after {args.timeout}s")
    return 1


# ── Test runner ───────────────────────────────────────────────────────────────

def _cmd_test(rest: list, session: SessionState) -> int:
    if not rest:
        print_error("Usage: test list|run|report [options]")
        return 2

    sub = rest[0]
    subrest = rest[1:]

    if sub == "list":
        return _test_list(subrest, session)
    if sub == "run":
        return _test_run(subrest, session)
    if sub == "report":
        return _test_report(subrest, session)

    print_error(f"Unknown test subcommand: '{sub}'")
    return 2


def _test_list(rest, session) -> int:
    import glob
    p = _parser("test list")
    p.add_argument("dir", nargs="?", default="tests")
    args, _ = p.parse_known_args(rest)
    files = sorted(glob.glob(f"{args.dir}/**/*.robot", recursive=True))
    if not files:
        print_warning(f"No .robot files found in '{args.dir}'.")
    for f in files:
        print(f)
    return 0


def _test_run(rest, session) -> int:
    import subprocess
    p = _parser("test run")
    p.add_argument("path")
    p.add_argument("--tag", dest="tags", action="append", default=[])
    p.add_argument("--suite", default=None)
    p.add_argument("--variable", dest="variables", action="append", default=[])
    args, _ = p.parse_known_args(rest)

    import os as _os
    cmd = ["robot",
           "--variable", f"VSPHERE_HOST:{session.host}",
           "--variable", f"VM_HOST:{session.host}"]
    env = _os.environ.copy()
    if session.guest_user:
        cmd += ["--variable", f"VM_USER:{session.guest_user}",
                "--variable", "VM_PASS:%{VM_PASS}"]
        if session.guest_pass:
            env["VM_PASS"] = session.guest_pass
    for tag in args.tags:
        cmd += ["--include", tag]
    if args.suite:
        cmd += ["--suite", args.suite]
    for var in args.variables:
        cmd += ["--variable", var]
    cmd.append(args.path)

    return subprocess.run(cmd, env=env).returncode


def _test_report(rest, session) -> int:
    import xml.etree.ElementTree as ET
    p = _parser("test report")
    p.add_argument("--output-xml", default="tests/output.xml")
    args, _ = p.parse_known_args(rest)

    try:
        stat = ET.parse(args.output_xml).getroot().find(".//statistics/total/stat")
        if stat is None:
            print_error("Could not find statistics in output.xml")
            return 1
        passed = int(stat.get("pass", 0))
        failed = int(stat.get("fail", 0))
        render({"total": passed + failed, "passed": passed, "failed": failed},
               session.output_format)
        return 0 if failed == 0 else 1
    except FileNotFoundError:
        print_error(f"File not found: {args.output_xml}. Run 'test run' first.")
        return 1


# ── Helper ────────────────────────────────────────────────────────────────────

def _parser(prog: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=prog, add_help=False)
