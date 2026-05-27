import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback

try:
    import defusedxml.ElementTree as _ET
except ImportError:
    import xml.etree.ElementTree as _ET  # type: ignore[no-redef]

from prompt_toolkit import PromptSession as _PromptSession
from prompt_toolkit.history import FileHistory as _FileHistory

from cli.completer import VMCompleter
from cli.output import (
    audit, confirm, print_error, print_success, print_warning, render, spinner
)
from cli.session import SessionState

_PROJECT_ROOT = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SUITE_RE = re.compile(r'^[\w\s\-]+$')
_VAR_RE = re.compile(r'^[A-Za-z_]\w*:.{0,256}$')
_WATCH_ALLOWED = frozenset({
    "list-vms", "list-folders", "search", "info", "snapshots",
    "datastore-info", "health-check",
})


class ManagerREPL:
    def __init__(self, session: SessionState):
        self.session = session
        history_path = os.path.expanduser("~/.dl_automation_history")
        self._completer = VMCompleter(session)
        self._prompt = _PromptSession(
            history=_FileHistory(history_path),
            completer=self._completer,
        )
        self._commands = {
            "list-vms": self.cmd_list_vms,
            "list-folders": self.cmd_list_folders,
            "search": self.cmd_search,
            "info": self.cmd_info,
            "snapshots": self.cmd_snapshots,
            "datastore-info": self.cmd_datastore_info,
            "health-check": self.cmd_health_check,
            "clone": self.cmd_clone,
            "delete-vm": self.cmd_delete_vm,
            "delete-folder": self.cmd_delete_folder,
            "delete-all-vms": self.cmd_delete_all_vms,
            "use": self.cmd_use,
            "bulk": self.cmd_bulk,
            "watch": self.cmd_watch,
            "test": self.cmd_test,
            "diff": self.cmd_diff,
            "bulk-clone": self.cmd_bulk_clone,
            "export": self.cmd_export,
            "run-script": self.cmd_run_script,
            "reconnect": self.cmd_reconnect,
            "switch-profile": self.cmd_switch_profile,
            "help": self.cmd_help,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
        }

    def run_loop(self):
        print_success(
            f"Connected to {self.session.host} [{self.session.platform}]. "
            f"Type 'help' for commands."
        )
        while True:
            try:
                line = self._prompt.prompt(f"{self.session.platform}> ")
            except (EOFError, KeyboardInterrupt):
                print_success("\nGoodbye.")
                break

            line = line.strip()
            if not line:
                continue

            try:
                tokens = shlex.split(line)
            except ValueError as e:
                print_error(f"Parse error: {e}")
                continue

            try:
                self.dispatch(tokens)
            except SystemExit as e:
                if e.code == 0:
                    break
            except Exception as e:
                print_error(str(e))
                if self.session.debug:
                    traceback.print_exc()

    def dispatch(self, tokens: list[str]) -> None:
        cmd = tokens[0].lower()
        rest = tokens[1:]
        handler = self._commands.get(cmd)
        if handler is None:
            print_error(f"Unknown command: '{cmd}'. Type 'help' for available commands.")
            return
        handler(rest)

    def _parser(self, prog):
        return argparse.ArgumentParser(prog=prog, add_help=False)

    def cmd_list_vms(self, rest):
        p = self._parser("list-vms")
        p.add_argument("--folder", default=None)
        p.add_argument("--limit", type=int, default=100)
        p.add_argument("--offset", type=int, default=0)
        args, _ = p.parse_known_args(rest)

        # find_vms_in_folder returns None when folder not found
        vms = self.session.manager.find_vms_in_folder(args.folder) or []
        total = len(vms)
        page = vms[args.offset: args.offset + args.limit]
        if total > args.offset + args.limit:
            print_warning(
                f"Showing {args.offset + 1}–{args.offset + len(page)} of {total}. "
                f"Use --offset to paginate."
            )

        rows = [{"name": getattr(vm, "name", str(vm))} for vm in page]
        render(rows, fmt=self.session.output_format)

    def cmd_list_folders(self, rest):
        print_warning(
            "No folder enumeration API available. "
            "Use 'list-vms --folder <name>' to list VMs in a specific folder."
        )

    def cmd_search(self, rest):
        p = self._parser("search")
        p.add_argument("keyword")
        args, _ = p.parse_known_args(rest)

        # find_vm_by_name returns [{"vm": vim_obj, "folder": vim_folder}]
        results = self.session.manager.find_vm_by_name(args.keyword) or []
        rows = [
            {
                "name": r["vm"].name if isinstance(r, dict) else getattr(r, "name", str(r)),
                "folder": r["folder"].name if isinstance(r, dict) and r.get("folder") else "",
            }
            for r in results
        ]
        render(rows, fmt=self.session.output_format)

    def cmd_info(self, rest):
        p = self._parser("info")
        p.add_argument("vm")
        p.add_argument("--folder", default=None)
        args, _ = p.parse_known_args(rest)

        vm = self.session.manager.get_vm(args.vm, args.folder)
        if vm is None:
            print_error(f"VM '{args.vm}' not found.")
            return
        info = vm.get_vm_info()
        render(info, fmt=self.session.output_format)

    def cmd_snapshots(self, rest):
        p = self._parser("snapshots")
        p.add_argument("vm")
        p.add_argument("--folder", default=None)
        args, _ = p.parse_known_args(rest)

        vm = self.session.manager.get_vm(args.vm, args.folder)
        if vm is None:
            print_error(f"VM '{args.vm}' not found.")
            return
        snaps = vm.get_snapshots()
        if not snaps:
            print_warning("No snapshots found.")
            return
        rows = [{"name": getattr(s, "name", str(s))} for s in snaps]
        render(rows, fmt=self.session.output_format)

    def cmd_datastore_info(self, rest):
        info = self.session.manager.get_datastore_info()
        render(info, fmt=self.session.output_format)

    def cmd_health_check(self, rest):
        p = self._parser("health-check")
        p.add_argument("--folder", default=None)
        args, _ = p.parse_known_args(rest)

        vms = self.session.manager.find_vms_in_folder(args.folder) or []
        rows = []
        for raw_vm in vms:
            vm_name = getattr(raw_vm, "name", str(raw_vm))
            try:
                vm_mgr = self.session.manager.get_vm(vm_name, args.folder)
                power = vm_mgr.get_power_status()
                tools = vm_mgr.get_guest_tools_status()
                healthy = power == "poweredOn" and tools == "guestToolsRunning"
                rows.append({
                    "name": vm_name,
                    "power": power,
                    "tools": tools,
                    "healthy": "yes" if healthy else "no",
                })
            except Exception as e:
                rows.append({"name": vm_name, "power": "?", "tools": "?", "healthy": f"error: {e}"})
        render(rows, fmt=self.session.output_format)

    def cmd_clone(self, rest):
        p = self._parser("clone")
        p.add_argument("vm")
        p.add_argument("new_name")
        p.add_argument("--folder", default=None)
        p.add_argument("--target-folder", default=None)
        p.add_argument("--snapshot", default=None)
        p.add_argument("--datastore", default=None)
        p.add_argument("--cpus", type=int, default=None)
        p.add_argument("--memory", type=int, default=None)
        p.add_argument("--power-on", action="store_true")
        args, _ = p.parse_known_args(rest)

        vm = self.session.manager.get_vm(args.vm, args.folder)
        if vm is None:
            print_error(f"VM '{args.vm}' not found.")
            return
        with spinner(f"Cloning {args.vm} → {args.new_name}"):
            result = vm.clone(
                target_folder_name=args.target_folder or args.folder,
                new_vm_name=args.new_name,
                snapshot_name=args.snapshot,
                datastore_name=args.datastore,
                num_cpus=args.cpus,
                memory_mb=args.memory,
                power_on=args.power_on,
            )
        audit(self.session, "clone", f"{args.vm} -> {args.new_name}", "OK" if result else "FAIL")
        if result:
            print_success(f"Cloned successfully to '{args.new_name}'.")
        else:
            print_error("Clone failed.")

    def cmd_delete_vm(self, rest):
        p = self._parser("delete-vm")
        p.add_argument("vm")
        p.add_argument("--folder", required=True)
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if not args.force and not confirm(f"Delete VM '{args.vm}' in folder '{args.folder}'?"):
            print_warning("Aborted.")
            return

        result = self.session.manager.delete_vm(args.folder, args.vm)
        audit(self.session, "delete-vm", f"{args.folder}/{args.vm}", "OK" if result else "FAIL")
        if result:
            print_success(f"VM '{args.vm}' deleted.")
        else:
            print_error("Delete failed.")

    def cmd_delete_folder(self, rest):
        p = self._parser("delete-folder")
        p.add_argument("folder")
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if not args.force and not confirm(f"Delete folder '{args.folder}' and all contents?"):
            print_warning("Aborted.")
            return

        result = self.session.manager.delete_folder(args.folder)
        audit(self.session, "delete-folder", args.folder, "OK" if result else "FAIL")
        if result:
            print_success(f"Folder '{args.folder}' deleted.")
        else:
            print_error("Delete failed.")

    def cmd_delete_all_vms(self, rest):
        p = self._parser("delete-all-vms")
        p.add_argument("--folder", required=True)
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if not args.force and not confirm(f"Delete ALL VMs in folder '{args.folder}'?"):
            print_warning("Aborted.")
            return

        result = self.session.manager.delete_all_vms_in_folder(args.folder)
        audit(self.session, "delete-all-vms", args.folder, "OK" if result else "FAIL")
        if result:
            print_success(f"All VMs in '{args.folder}' deleted.")
        else:
            print_error("Delete failed.")

    def cmd_use(self, rest):
        p = self._parser("use")
        p.add_argument("vm")
        p.add_argument("--folder", default=None)
        args, _ = p.parse_known_args(rest)

        from cli.repl_vm import VMREPL
        vm = self.session.manager.get_vm(args.vm, args.folder)
        if vm is None:
            print_error(f"VM '{args.vm}' not found.")
            return
        # For implementations (e.g. vSphere) that store the underlying object in .vm
        if hasattr(vm, 'vm') and not vm.vm:
            print_error(f"VM '{args.vm}' not found.")
            return
        VMREPL(self.session, args.vm, vm).run_loop()

    def cmd_reconnect(self, rest):
        try:
            self.session.manager.disconnect()
        except Exception as e:
            print_warning(f"Disconnect warning: {e}")
        try:
            self.session.manager.connect()
        except Exception as e:
            print_error(f"Reconnect failed: {e}")
            return
        self._completer.invalidate_cache()
        print_success("Reconnected.")

    def cmd_switch_profile(self, rest):
        p = self._parser("switch-profile")
        p.add_argument("profile")
        args, _ = p.parse_known_args(rest)

        import types
        fake_args = types.SimpleNamespace(
            platform=self.session.platform,
            profile=args.profile,
            debug=self.session.debug,
            output=self.session.output_format,
            no_log=self.session.no_log,
        )
        from cli.auth import auth
        new_session = auth(fake_args)
        # Transfer the new manager into the current session
        try:
            self.session.manager.disconnect()
        except Exception as e:
            print_warning(f"Disconnect warning: {e}")
        self.session.manager = new_session.manager
        self.session.host = new_session.host
        self._completer.invalidate_cache()
        print_success(f"Switched to profile '{args.profile}' ({self.session.host}).")

    def cmd_test(self, rest: list) -> None:
        if not rest:
            print_error("Usage: test list|run|report [options]")
            return
        sub = rest[0]
        subrest = rest[1:]
        if sub == "list":
            self._test_list(subrest)
        elif sub == "run":
            self._test_run(subrest)
        elif sub == "report":
            self._test_report(subrest)
        else:
            print_error(f"Unknown test subcommand: '{sub}'. Use list, run, or report.")

    def _test_list(self, rest: list) -> None:
        p = self._parser("test list")
        p.add_argument("dir", nargs="?", default="tests")
        args, _ = p.parse_known_args(rest)

        resolved_dir = os.path.realpath(args.dir)
        if not (resolved_dir == _PROJECT_ROOT or resolved_dir.startswith(_PROJECT_ROOT + os.sep)):
            print_error("Test directory must be inside the project root.")
            return

        files = sorted(glob.glob(f"{resolved_dir}/**/*.robot", recursive=True))
        if not files:
            print_warning(f"No .robot files found in '{args.dir}'.")
            return
        render([{"file": f} for f in files], fmt=self.session.output_format)

    def _test_run(self, rest: list) -> None:
        p = self._parser("test run")
        p.add_argument("path")
        p.add_argument("--tag", dest="tags", action="append", default=None)
        p.add_argument("--suite", default=None)
        p.add_argument("--variable", dest="variables", action="append", default=None)
        p.add_argument("--timeout", type=int, default=None,
                       help="Subprocess timeout in seconds")
        args, _ = p.parse_known_args(rest)

        if args.suite and not _SUITE_RE.match(args.suite):
            print_error("Invalid --suite: only alphanumerics, spaces, and hyphens allowed.")
            return
        for var in (args.variables or []):
            if not _VAR_RE.match(var):
                print_error(f"Invalid --variable format (expected NAME:value): {var!r}")
                return

        env = os.environ.copy()
        cmd = [
            "robot",
            "--variable", f"VSPHERE_HOST:{self.session.host}",
            "--variable", f"VM_HOST:{self.session.host}",
        ]
        if self.session.guest_user:
            cmd += ["--variable", f"VM_USER:{self.session.guest_user}",
                    "--variable", "VM_PASS:%{VM_PASS}"]
            if self.session.guest_pass:
                env["VM_PASS"] = self.session.guest_pass
        for tag in (args.tags or []):
            cmd += ["--include", tag]
        if args.suite:
            cmd += ["--suite", args.suite]
        for var in (args.variables or []):
            cmd += ["--variable", var]

        resolved_path = os.path.realpath(args.path)
        if not (resolved_path == _PROJECT_ROOT or resolved_path.startswith(_PROJECT_ROOT + os.sep)):
            print_error("Test path must be inside the project directory.")
            return
        cmd.append(resolved_path)

        try:
            rc = subprocess.run(cmd, env=env, timeout=args.timeout).returncode
        except FileNotFoundError:
            print_error("'robot' not found. Install it: pip install robotframework")
            return
        except subprocess.TimeoutExpired:
            print_error(f"Test run timed out after {args.timeout}s.")
            return
        if rc == 0:
            print_success("All tests passed.")
        else:
            print_warning(f"Tests finished with exit code {rc}.")

    def _test_report(self, rest: list) -> None:
        p = self._parser("test report")
        p.add_argument("--output-xml", default="tests/output.xml")
        args, _ = p.parse_known_args(rest)

        xml_path = os.path.realpath(args.output_xml)
        if not (xml_path == _PROJECT_ROOT or xml_path.startswith(_PROJECT_ROOT + os.sep)):
            print_error("--output-xml path must be inside the project directory.")
            return

        try:
            stat = _ET.parse(xml_path).getroot().find(".//statistics/total/stat")
            if stat is None:
                print_error("Could not parse statistics from output.xml.")
                return
            try:
                passed = int(stat.get("pass", 0))
                failed = int(stat.get("fail", 0))
            except ValueError as e:
                print_error(f"Unexpected value in statistics node: {e}")
                return
            data = {"total": passed + failed, "passed": passed, "failed": failed}
            render(data, fmt=self.session.output_format)
            if failed:
                print_warning(f"{failed} test(s) failed.")
        except FileNotFoundError:
            print_error(f"File not found: {args.output_xml}. Run 'test run' first.")
        except _ET.ParseError as e:
            print_error(f"Failed to parse XML: {e}")
        except OSError as e:
            print_error(f"Could not read report file: {e}")

    def cmd_diff(self, rest: list[str]) -> None:
        p = self._parser("diff")
        p.add_argument("vm1")
        p.add_argument("vm2")
        p.add_argument("--folder", default=None)
        args, _ = p.parse_known_args(rest)

        vm1 = self.session.manager.get_vm(args.vm1, args.folder)
        if vm1 is None:
            print_error(f"VM '{args.vm1}' not found.")
            return
        vm2 = self.session.manager.get_vm(args.vm2, args.folder)
        if vm2 is None:
            print_error(f"VM '{args.vm2}' not found.")
            return

        info1 = vm1.get_vm_info() or {}
        info2 = vm2.get_vm_info() or {}
        all_keys = sorted(set(info1) | set(info2))
        rows = []
        for key in all_keys:
            v1 = str(info1.get(key, ""))
            v2 = str(info2.get(key, ""))
            if v1 != v2:
                rows.append({"field": key, args.vm1: v1, args.vm2: v2})
        if not rows:
            print_success("No differences found.")
            return
        render(rows, fmt=self.session.output_format)

    def cmd_bulk_clone(self, rest: list[str]) -> None:
        p = self._parser("bulk-clone")
        p.add_argument("template")
        p.add_argument("--count", type=int, required=True)
        p.add_argument("--prefix", default="clone")
        p.add_argument("--folder", default=None)
        p.add_argument("--target-folder", default=None)
        p.add_argument("--snapshot", default=None)
        p.add_argument("--power-on", action="store_true")
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if args.count < 1 or args.count > 100:
            print_error("--count must be between 1 and 100.")
            return

        if not args.force and not confirm(
            f"Clone '{args.template}' × {args.count} with prefix '{args.prefix}'?"
        ):
            print_warning("Aborted.")
            return

        template_vm = self.session.manager.get_vm(args.template, args.folder)
        if template_vm is None:
            print_error(f"Template VM '{args.template}' not found.")
            return

        ok_count = 0
        fail_count = 0
        for i in range(1, args.count + 1):
            new_name = f"{args.prefix}-{i:02d}"
            try:
                with spinner(f"Cloning {new_name}"):
                    result = template_vm.clone(
                        target_folder_name=args.target_folder or args.folder,
                        new_vm_name=new_name,
                        snapshot_name=args.snapshot,
                        power_on=args.power_on,
                    )
                if result:
                    print_success(f"  {new_name}: OK")
                    ok_count += 1
                else:
                    print_error(f"  {new_name}: clone returned failure")
                    fail_count += 1
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print_error(f"  {new_name}: {e}")
                audit(self.session, "bulk-clone-fail", new_name, str(e))
                fail_count += 1

        status = "OK" if fail_count == 0 else "PARTIAL"
        audit(self.session, "bulk-clone", f"template={args.template} count={args.count}", status)
        summary = f"bulk-clone: {ok_count} OK, {fail_count} failed"
        if fail_count == 0:
            print_success(summary)
        else:
            print_warning(summary)

    def cmd_export(self, rest: list[str]) -> None:
        p = self._parser("export")
        p.add_argument("vm")
        p.add_argument("--folder", default=None)
        p.add_argument("--format", dest="fmt", choices=["json", "yaml"], default="json")
        p.add_argument("--output", default=None)
        args, _ = p.parse_known_args(rest)

        vm = self.session.manager.get_vm(args.vm, args.folder)
        if vm is None:
            print_error(f"VM '{args.vm}' not found.")
            return

        info = vm.get_vm_info() or {}

        if args.fmt == "json":
            text = json.dumps(info, indent=2, default=str)
            ext = "json"
        else:
            try:
                import yaml
                text = yaml.safe_dump(info, allow_unicode=True)
            except ImportError:
                print_error("PyYAML not installed. Run: pip install pyyaml")
                return
            ext = "yaml"

        if args.output:
            output_path = args.output
        else:
            safe_name = re.sub(r'[^\w\-]', '_', args.vm)
            output_path = f"{safe_name}.{ext}"

        resolved_output = os.path.realpath(output_path)
        if not (resolved_output == _PROJECT_ROOT or resolved_output.startswith(_PROJECT_ROOT + os.sep)):
            print_error("Output path must be inside the project directory.")
            return

        try:
            with open(resolved_output, "w") as f:
                f.write(text)
            audit(self.session, "export", f"{args.vm} -> {resolved_output}", "OK")
            print_success(f"Exported to '{resolved_output}'.")
        except OSError as e:
            print_error(f"Could not write file: {e}")

    def cmd_run_script(self, rest: list[str]) -> None:
        p = self._parser("run-script")
        p.add_argument("path")
        args, _ = p.parse_known_args(rest)

        resolved_path = os.path.realpath(args.path)
        if not (resolved_path == _PROJECT_ROOT or resolved_path.startswith(_PROJECT_ROOT + os.sep)):
            print_error("Script path must be inside the project directory.")
            return

        from cli.batch import ScriptError, run_script
        audit(self.session, "run-script", resolved_path, "START")
        try:
            run_script(resolved_path, self)
        except ScriptError as e:
            print_error(str(e))

    def cmd_bulk(self, rest: list[str]) -> None:
        p = self._parser("bulk")
        p.add_argument("action", choices=["start", "stop", "snapshot", "revert"])
        p.add_argument("--folder", required=True)
        p.add_argument("--snapshot-name", default=None)
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        try:
            vms = self.session.manager.find_vms_in_folder(args.folder) or []
        except Exception as e:
            print_error(f"Failed to list VMs in folder '{args.folder}': {e}")
            audit(self.session, f"bulk-{args.action}", f"folder={args.folder}", "ERROR")
            return

        if not vms:
            print_warning(f"No VMs found in folder '{args.folder}'.")
            return

        if not args.force and not confirm(
            f"Apply '{args.action}' to {len(vms)} VM(s) in '{args.folder}'?"
        ):
            print_warning("Aborted.")
            return

        snap_name = args.snapshot_name or f"bulk-{time.strftime('%Y%m%d-%H%M%S')}"
        ok_count = 0
        fail_count = 0

        for raw_vm in vms:
            vm_name = getattr(raw_vm, "name", str(raw_vm))
            try:
                vm = self.session.manager.get_vm(vm_name, args.folder)
                if vm is None:
                    raise ValueError("VM not found")
                if args.action == "start":
                    vm.power_on()
                elif args.action == "stop":
                    vm.power_off()
                elif args.action == "snapshot":
                    vm.create_snapshot(snap_name)
                elif args.action == "revert":
                    vm.revert_to_current_snapshot()
                print_success(f"  {vm_name}: OK")
                ok_count += 1
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print_error(f"  {vm_name}: {e}")
                fail_count += 1

        status = "OK" if fail_count == 0 else "PARTIAL"
        audit(self.session, f"bulk-{args.action}", f"folder={args.folder}", status)
        summary = f"bulk-{args.action}: {ok_count} OK, {fail_count} failed"
        if fail_count == 0:
            print_success(summary)
        else:
            print_warning(summary)

    def cmd_watch(self, rest: list[str]) -> None:
        p = self._parser("watch")
        p.add_argument("--interval", type=int, default=5)
        args, subcmd = p.parse_known_args(rest)

        if not subcmd:
            print_error(
                f"Usage: watch [--interval N] <command> [args...]\n"
                f"Allowed commands: {', '.join(sorted(_WATCH_ALLOWED))}"
            )
            return

        if subcmd[0].lower() not in _WATCH_ALLOWED:
            print_error(
                f"'{subcmd[0]}' is not allowed in watch. "
                f"Only read-only commands: {', '.join(sorted(_WATCH_ALLOWED))}"
            )
            return

        if args.interval < 1:
            print_error("--interval must be at least 1 second.")
            return

        audit(self.session, "watch-start", f"cmd={subcmd[0]} interval={args.interval}s", "OK")
        try:
            while True:
                if sys.stdout.isatty():
                    print("\033[2J\033[H", end="", flush=True)
                else:
                    print("---", flush=True)
                self.dispatch(subcmd)
                print_warning(f"\nRefresh every {args.interval}s — Ctrl+C to stop")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            audit(self.session, "watch-stop", f"cmd={subcmd[0]}", "OK")
            print()

    def cmd_help(self, rest):
        lines = [
            ("list-vms",        "[--folder F] [--limit N] [--offset N]  List VMs"),
            ("list-folders",    "                                        Show folder note"),
            ("search",          "<keyword>                               Search VMs by name"),
            ("info",            "<vm> [--folder F]                       VM details"),
            ("snapshots",       "<vm> [--folder F]                       List snapshots"),
            ("datastore-info",  "                                        Datastore usage"),
            ("health-check",    "[--folder F]                            Power + tools status"),
            ("clone",           "<vm> <new_name> [options]               Clone a VM"),
            ("delete-vm",       "<vm> --folder F [--force]              Delete a VM"),
            ("delete-folder",   "<folder> [--force]                      Delete folder"),
            ("delete-all-vms",  "--folder F [--force]                   Delete all VMs in folder"),
            ("use",             "<vm> [--folder F]                       Enter VM REPL"),
            ("bulk",            "start|stop|snapshot|revert --folder F   Bulk action on all VMs"),
            ("bulk-clone",      "<template> --count N [--prefix P]       Clone template N times"),
            ("watch",           "[--interval N] <command>                Auto-refresh a command"),
            ("test",            "list|run|report [options]               Robot Framework test runner"),
            ("diff",            "<vm1> <vm2> [--folder F]                Compare two VM configs"),
            ("export",          "<vm> [--format json|yaml] [--output F]  Export VM info to file"),
            ("run-script",      "<path>                                  Run a batch command script"),
            ("reconnect",       "                                        Reconnect to hypervisor"),
            ("switch-profile",  "<profile>                               Switch credentials profile"),
            ("help",            "                                        Show this help"),
            ("exit / quit",     "                                        Exit"),
        ]
        rows = [{"Command": cmd, "Usage": usage} for cmd, usage in lines]
        render(rows, fmt="table", headers=["Command", "Usage"])

    def cmd_exit(self, rest):
        raise SystemExit(0)
