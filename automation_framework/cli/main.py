import argparse

from cli.auth import auth
from cli.output import print_error, print_warning
from cli.repl_manager import ManagerREPL

VERSION = "0.1.0"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="automation-framework",
        description="Multi-platform VM management CLI",
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "--platform", default="vsphere",
        choices=["vsphere", "proxmox", "fusion"],
        help="Hypervisor platform (default: vsphere)",
    )
    parser.add_argument(
        "--profile", default=None,
        help="Credentials profile name (~/.automation_framework/profiles/<name>.config)",
    )
    parser.add_argument(
        "--output", default="table",
        choices=["table", "json", "yaml"],
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--no-verify-ssl", dest="no_verify_ssl", action="store_true",
        help="Disable SSL certificate verification",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug output (tracebacks on errors)",
    )
    parser.add_argument(
        "--no-log", dest="no_log", action="store_true",
        help="Disable audit logging",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args, remaining = parser.parse_known_args()

    if args.version:
        print(f"automation-framework {VERSION}")
        return 0

    try:
        session = auth(args)
    except FileNotFoundError as e:
        print_error(str(e))
        return 3
    except Exception as e:
        print_error(f"Auth failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 3

    if remaining:
        from cli.oneshot import dispatch
        return dispatch(remaining, session)

    ManagerREPL(session).run_loop()
    return 0
