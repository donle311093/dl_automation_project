import argparse
import shlex
import time

from prompt_toolkit import PromptSession as _PromptSession

from cli.output import (
    audit, confirm, print_error, print_success, print_warning, render, spinner
)
from cli.session import SessionState


class VMREPL:
    def __init__(self, session: SessionState, vm_name: str, vm):
        self.session = session
        self.vm_name = vm_name
        self.vm = vm
        self._prompt = _PromptSession()

    def run_loop(self):
        prompt_str = f"{self.session.platform}/vm[{self.vm_name}]> "
        print_success(f"Entered VM context: {self.vm_name}. Type 'help' for commands.")
        while True:
            try:
                line = self._prompt.prompt(prompt_str)
            except (EOFError, KeyboardInterrupt):
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
                if not self.dispatch(tokens):
                    break
            except SystemExit as e:
                if e.code == 0:
                    break
            except Exception as e:
                print_error(str(e))
                if self.session.debug:
                    import traceback
                    traceback.print_exc()

    def dispatch(self, tokens) -> bool:
        """Return False to break the loop."""
        cmd = tokens[0].lower()
        rest = tokens[1:]
        commands = {
            "status": self.cmd_status,
            "start": self.cmd_start,
            "stop": self.cmd_stop,
            "restart": self.cmd_restart,
            "reset": self.cmd_reset,
            "suspend": self.cmd_suspend,
            "info": self.cmd_info,
            "tools-status": self.cmd_tools_status,
            "health": self.cmd_health,
            "annotation": self.cmd_annotation,
            "snapshots": self.cmd_snapshots,
            "snapshot": self.cmd_snapshot,
            "clone": self.cmd_clone,
            "wait-for-status": self.cmd_wait_for_status,
            "wait-for-tools": self.cmd_wait_for_tools,
            "run": self.cmd_run,
            "login": self.cmd_login,
            "back": self.cmd_back,
            "exit": self.cmd_back,
            "help": self.cmd_help,
        }
        handler = commands.get(cmd)
        if handler is None:
            print_error(f"Unknown command: '{cmd}'. Type 'help' for commands.")
            return True
        return handler(rest)

    def _parser(self, prog):
        return argparse.ArgumentParser(prog=prog, add_help=False)

    def cmd_status(self, rest):
        status = self.vm.get_power_status()
        if status in ("poweredOn",):
            print_success(f"Power: {status}")
        else:
            print_error(f"Power: {status}")
        return True

    def cmd_start(self, rest):
        result = self.vm.power_on()
        if result:
            print_success("VM powered on.")
        else:
            print_warning("Power on returned False (may already be on).")
        return True

    def cmd_stop(self, rest):
        p = self._parser("stop")
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if not args.force and not confirm(f"Power off '{self.vm_name}'?"):
            print_warning("Aborted.")
            return True

        result = self.vm.power_off()
        if result:
            print_success("VM powered off.")
        else:
            print_warning("Power off returned False.")
        return True

    def cmd_restart(self, rest):
        result = self.vm.reboot()
        if result:
            print_success("VM rebooted.")
        else:
            print_warning("Reboot returned False.")
        return True

    def cmd_reset(self, rest):
        p = self._parser("reset")
        p.add_argument("--force", action="store_true")
        args, _ = p.parse_known_args(rest)

        if not args.force and not confirm(f"Hard reset '{self.vm_name}'?"):
            print_warning("Aborted.")
            return True

        result = self.vm.reset()
        if result:
            print_success("VM reset.")
        else:
            print_warning("Reset returned False.")
        return True

    def cmd_suspend(self, rest):
        result = self.vm.suspend()
        if result:
            print_success("VM suspended.")
        else:
            print_warning("Suspend returned False.")
        return True

    def cmd_info(self, rest):
        info = self.vm.get_vm_info()
        render(info, fmt=self.session.output_format)
        return True

    def cmd_tools_status(self, rest):
        status = self.vm.get_guest_tools_status()
        if status == "guestToolsRunning":
            print_success(f"Guest tools: {status}")
        else:
            print_warning(f"Guest tools: {status}")
        return True

    def cmd_health(self, rest):
        power = self.vm.get_power_status()
        tools = self.vm.get_guest_tools_status()
        healthy = power == "poweredOn" and tools == "guestToolsRunning"
        data = {
            "vm": self.vm_name,
            "power": power,
            "tools": tools,
            "healthy": "yes" if healthy else "no",
        }
        render(data, fmt=self.session.output_format)
        return True

    def cmd_annotation(self, rest):
        p = self._parser("annotation")
        p.add_argument("subcommand", choices=["get", "set"])
        p.add_argument("value", nargs="?", default=None)
        args, _ = p.parse_known_args(rest)

        if args.subcommand == "get":
            annotation = self.vm.get_annotation()
            print_success(f"Annotation: {annotation}")
        elif args.subcommand == "set":
            if args.value is None:
                print_error("Provide a value: annotation set <text>")
                return True
            result = self.vm.set_annotation(args.value)
            if result:
                print_success("Annotation updated.")
            else:
                print_error("Failed to update annotation.")
        return True

    def cmd_snapshots(self, rest):
        snaps = self.vm.get_snapshots()
        if not snaps:
            print_warning("No snapshots found.")
            return True

        # Render as indented tree; snapshot objects have .name and .childSnapshotList
        def _print_tree(snap_list, level=0):
            for snap in snap_list:
                indent = "  " * level
                name = getattr(snap, "name", str(snap))
                desc = getattr(snap, "description", "")
                line = f"{indent}├─ {name}"
                if desc:
                    line += f"  [{desc}]"
                print_success(line) if level == 0 else print(line)
                children = getattr(snap, "childSnapshotList", [])
                if children:
                    _print_tree(children, level + 1)

        # list_all_snapshots returns a flat list from snapshot.py's _traverse_snapshots
        # We can only show them flat since we don't have the hierarchy from that list
        rows = [{"name": getattr(s, "name", str(s)), "description": getattr(s, "description", "")}
                for s in snaps]
        render(rows, fmt=self.session.output_format)
        return True

    def cmd_snapshot(self, rest):
        p = self._parser("snapshot")
        p.add_argument("subcommand", choices=["create", "revert", "delete"])
        p.add_argument("name", nargs="?", default=None)
        p.add_argument("--description", default="")
        p.add_argument("--memory", action="store_true")
        p.add_argument("--quiesce", action="store_true")
        args, _ = p.parse_known_args(rest)

        if args.subcommand == "create":
            if not args.name:
                print_error("Provide snapshot name: snapshot create <name>")
                return True
            result = self.vm.create_snapshot(args.name, args.description, args.memory, args.quiesce)
            audit(self.session, "snapshot-create", f"{self.vm_name}:{args.name}", "OK" if result else "FAIL")
            print_success("Snapshot created.") if result else print_error("Snapshot creation failed.")
        elif args.subcommand == "revert":
            if args.name:
                result = self.vm.revert_to_snapshot(args.name)
            else:
                result = self.vm.revert_to_current_snapshot()
            audit(self.session, "snapshot-revert", f"{self.vm_name}:{args.name or 'current'}", "OK" if result else "FAIL")
            print_success("Reverted.") if result else print_error("Revert failed.")
        elif args.subcommand == "delete":
            if not args.name:
                print_error("Provide snapshot name: snapshot delete <name>")
                return True
            if not confirm(f"Delete snapshot '{args.name}' from '{self.vm_name}'?"):
                print_warning("Aborted.")
                return True
            result = self.vm.delete_snapshot(args.name)
            audit(self.session, "snapshot-delete", f"{self.vm_name}:{args.name}", "OK" if result else "FAIL")
            print_success("Snapshot deleted.") if result else print_error("Delete failed.")
        return True

    def cmd_clone(self, rest):
        p = self._parser("clone")
        p.add_argument("new_name")
        p.add_argument("--target-folder", default=None)
        p.add_argument("--snapshot", default=None)
        p.add_argument("--datastore", default=None)
        p.add_argument("--cpus", type=int, default=None)
        p.add_argument("--memory", type=int, default=None)
        p.add_argument("--power-on", action="store_true")
        args, _ = p.parse_known_args(rest)

        with spinner(f"Cloning {self.vm_name} → {args.new_name}"):
            result = self.vm.clone(
                target_folder_name=args.target_folder,
                new_vm_name=args.new_name,
                snapshot_name=args.snapshot,
                datastore_name=args.datastore,
                num_cpus=args.cpus,
                memory_mb=args.memory,
                power_on=args.power_on,
            )
        audit(self.session, "clone", f"{self.vm_name} -> {args.new_name}", "OK" if result else "FAIL")
        if result:
            print_success(f"Cloned to '{args.new_name}'.")
        else:
            print_error("Clone failed.")
        return True

    def cmd_wait_for_status(self, rest):
        p = self._parser("wait-for-status")
        p.add_argument("target", choices=["on", "off"])
        p.add_argument("--timeout", type=int, default=120)
        p.add_argument("--interval", type=int, default=5)
        args, _ = p.parse_known_args(rest)

        target_status = "poweredOn" if args.target == "on" else "poweredOff"
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            current = self.vm.get_power_status()
            if current == target_status:
                print_success(f"VM is now {target_status}.")
                return True
            print_warning(f"Status: {current} (waiting for {target_status})...")
            time.sleep(args.interval)
        print_error(f"Timeout waiting for status '{target_status}'.")
        return True

    def cmd_wait_for_tools(self, rest):
        p = self._parser("wait-for-tools")
        p.add_argument("--timeout", type=int, default=300)
        p.add_argument("--interval", type=int, default=10)
        args, _ = p.parse_known_args(rest)

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            status = self.vm.get_guest_tools_status()
            if status == "guestToolsRunning":
                print_success("Guest tools are running.")
                return True
            print_warning(f"Tools status: {status}...")
            time.sleep(args.interval)
        print_error("Timeout waiting for guest tools.")
        return True

    def cmd_run(self, rest):
        p = self._parser("run")
        p.add_argument("command", nargs=argparse.REMAINDER)
        p.add_argument("--show-pid", action="store_true", dest="show_pid")
        args, _ = p.parse_known_args(rest)

        if not self.session.guest_user:
            print_error("Not logged in. Use 'login <user>' first.")
            return True

        cmd_str = " ".join(args.command)
        if not cmd_str:
            print_error("Provide a command: run <command>")
            return True

        # Inject stored credentials into vm object for execute_command
        self.vm.user_login = self.session.guest_user
        self.vm.pass_login = self.session.guest_pass

        result = self.vm.execute_command(cmd_str, verbose=args.show_pid)
        render(result, fmt=self.session.output_format)
        return True

    def cmd_login(self, rest):
        p = self._parser("login")
        p.add_argument("user")
        p.add_argument("password", nargs="?", default=None)
        args, _ = p.parse_known_args(rest)

        import getpass as _getpass
        password = args.password or _getpass.getpass("Guest password: ")

        result = self.vm.login(args.user, password)
        if result:
            self.session.guest_user = args.user
            self.session.guest_pass = password
            print_success(f"Logged in as '{args.user}'.")
            from cli.repl_shell import ShellREPL
            ShellREPL(self.session, self.vm_name, self.vm).run_loop()
        else:
            print_error("Login failed.")
        return True

    def cmd_back(self, rest):
        return False

    def cmd_help(self, rest):
        lines = [
            ("status",            "              Power status"),
            ("start",             "              Power on"),
            ("stop",              "[--force]     Power off"),
            ("restart",           "              Reboot (guest OS)"),
            ("reset",             "[--force]     Hard reset"),
            ("suspend",           "              Suspend"),
            ("info",              "              VM details"),
            ("tools-status",      "              Guest tools status"),
            ("health",            "              Power + tools summary"),
            ("annotation",        "get|set [val] Annotation"),
            ("snapshots",         "              List snapshots"),
            ("snapshot",          "create|revert|delete <name>  Snapshot ops"),
            ("clone",             "<new_name> [options]  Clone this VM"),
            ("wait-for-status",   "on|off [--timeout N] [--interval N]"),
            ("wait-for-tools",    "[--timeout N] [--interval N]"),
            ("run",               "<command>     Execute guest command (requires login)"),
            ("login",             "<user> [pass] Authenticate to guest OS"),
            ("back / exit",       "              Return to manager REPL"),
            ("help",              "              Show this help"),
        ]
        rows = [{"Command": cmd, "Description": desc} for cmd, desc in lines]
        render(rows, fmt="table", headers=["Command", "Description"])
        return True
