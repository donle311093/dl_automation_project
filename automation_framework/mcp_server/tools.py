from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.interfaces import IHypervisorManager

try:
    from defusedxml.ElementTree import parse as _xml_parse
except ImportError:
    from xml.etree.ElementTree import parse as _xml_parse  # type: ignore[assignment]

_logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_manager: IHypervisorManager | None = None
_manager_lock = threading.Lock()

_VAR_NAME_RE = re.compile(r'^[A-Za-z_]\w*$')


def _get_manager() -> "IHypervisorManager":
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                host = os.environ.get("VSPHERE_HOST", "")
                user = os.environ.get("VSPHERE_USER", "")
                password = os.environ.get("VSPHERE_PASS", "")
                if not host or not user or not password:
                    raise EnvironmentError(
                        "VSPHERE_HOST, VSPHERE_USER, and VSPHERE_PASS must be set"
                    )
                try:
                    port = int(os.environ.get("VSPHERE_PORT", "443"))
                except ValueError:
                    raise EnvironmentError("VSPHERE_PORT must be an integer") from None
                from core.factory import HypervisorFactory
                config = {
                    "host": host,
                    "user": user,
                    "password": password,
                    "port": port,
                    "ssl_verify": os.environ.get("VSPHERE_NO_SSL_VERIFY", "0") != "1",
                }
                mgr = HypervisorFactory.create("vsphere", config)
                mgr.connect()
                _manager = mgr
    return _manager


def _vm_list(vms: list[Any]) -> list[dict[str, Any]]:
    return [{"name": getattr(v, "name", str(v))} for v in (vms or [])]


def _snap_list(snaps: list[Any]) -> list[dict[str, Any]]:
    return [{"name": getattr(s, "name", str(s))} for s in (snaps or [])]


def register(mcp: Any) -> None:

    @mcp.tool()
    def list_vms(folder: str | None = None) -> list[dict[str, Any]]:
        """List all VMs, optionally filtered by folder."""
        try:
            return _vm_list(_get_manager().find_vms_in_folder(folder))
        except Exception as e:
            _logger.exception("list_vms failed")
            return [{"error": str(e)}]

    @mcp.tool()
    def get_vm_info(vm_name: str, folder: str | None = None) -> dict[str, Any]:
        """Get detailed configuration and runtime info for a VM."""
        try:
            return _get_manager().get_vm(vm_name, folder).get_vm_info() or {}
        except Exception as e:
            _logger.exception("get_vm_info failed for %s", vm_name)
            return {"error": str(e)}

    @mcp.tool()
    def get_power_status(vm_name: str, folder: str | None = None) -> dict[str, Any]:
        """Return the current power state of a VM."""
        try:
            status = _get_manager().get_vm(vm_name, folder).get_power_status()
            return {"vm": vm_name, "status": status}
        except Exception as e:
            _logger.exception("get_power_status failed for %s", vm_name)
            return {"error": str(e)}

    @mcp.tool()
    def power_on(vm_name: str, folder: str | None = None) -> dict[str, Any]:
        """Power on a VM."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).power_on()
            return {"success": ok, "message": "Powered on" if ok else "Failed"}
        except Exception as e:
            _logger.exception("power_on failed for %s", vm_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def power_off(vm_name: str, folder: str | None = None) -> dict[str, Any]:
        """Power off a VM."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).power_off()
            return {"success": ok, "message": "Powered off" if ok else "Failed"}
        except Exception as e:
            _logger.exception("power_off failed for %s", vm_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def restart_vm(vm_name: str, folder: str | None = None) -> dict[str, Any]:
        """Reboot a VM guest OS."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).reboot()
            return {"success": ok, "message": "Restarted" if ok else "Failed"}
        except Exception as e:
            _logger.exception("restart_vm failed for %s", vm_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_snapshots(vm_name: str, folder: str | None = None) -> list[dict[str, Any]]:
        """List all snapshots for a VM."""
        try:
            snaps = _get_manager().get_vm(vm_name, folder).get_snapshots()
            return _snap_list(snaps)
        except Exception as e:
            _logger.exception("list_snapshots failed for %s", vm_name)
            return [{"error": str(e)}]

    @mcp.tool()
    def create_snapshot(
        vm_name: str,
        snap_name: str,
        description: str = "",
        folder: str | None = None,
    ) -> dict[str, Any]:
        """Create a named snapshot of a VM."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).create_snapshot(snap_name, description)
            return {"success": ok, "message": f"Snapshot '{snap_name}' created" if ok else "Failed"}
        except Exception as e:
            _logger.exception("create_snapshot failed for %s/%s", vm_name, snap_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def revert_snapshot(
        vm_name: str,
        snap_name: str | None = None,
        folder: str | None = None,
    ) -> dict[str, Any]:
        """Revert a VM to a snapshot. Omit snap_name to revert to the current snapshot."""
        try:
            vm = _get_manager().get_vm(vm_name, folder)
            ok = vm.revert_to_snapshot(snap_name) if snap_name else vm.revert_to_current_snapshot()
            return {"success": ok, "message": "Reverted" if ok else "Failed"}
        except Exception as e:
            _logger.exception("revert_snapshot failed for %s", vm_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def delete_snapshot(
        vm_name: str,
        snap_name: str,
        folder: str | None = None,
    ) -> dict[str, Any]:
        """Delete a named snapshot from a VM."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).delete_snapshot(snap_name)
            return {"success": ok, "message": f"Snapshot '{snap_name}' deleted" if ok else "Failed"}
        except Exception as e:
            _logger.exception("delete_snapshot failed for %s/%s", vm_name, snap_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def clone_vm(
        vm_name: str,
        new_name: str,
        target_folder: str,
        folder: str | None = None,
        snapshot: str | None = None,
        cpus: int | None = None,
        memory_mb: int | None = None,
        power_on: bool = False,
    ) -> dict[str, Any]:
        """Clone a VM to a new name in the given target folder."""
        try:
            ok = _get_manager().get_vm(vm_name, folder).clone(
                target_folder_name=target_folder,
                new_vm_name=new_name,
                snapshot_name=snapshot,
                num_cpus=cpus,
                memory_mb=memory_mb,
                power_on=power_on,
            )
            return {"success": ok, "message": f"Cloned to '{new_name}'" if ok else "Failed"}
        except Exception as e:
            _logger.exception("clone_vm failed: %s -> %s", vm_name, new_name)
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def execute_command(
        vm_name: str,
        command: str,
        folder: str | None = None,
    ) -> dict[str, Any]:
        """Execute a shell command inside a VM guest OS.

        Credentials are read from VM_USER and VM_PASS environment variables
        on the MCP server — they are never passed as tool parameters.
        """
        user = os.environ.get("VM_USER", "")
        password = os.environ.get("VM_PASS", "")
        if not user or not password:
            return {"error": "VM_USER and VM_PASS must be set in the MCP server environment"}
        try:
            vm = _get_manager().get_vm(vm_name, folder)
            if not vm.login(user, password):
                return {"error": "Guest login failed — check VM_USER / VM_PASS"}
            raw = vm.execute_command(command)
            if not isinstance(raw, dict):
                return {"output": str(raw) if raw is not None else ""}
            return raw
        except Exception as e:
            _logger.exception("execute_command failed on %s", vm_name)
            return {"error": str(e)}

    @mcp.tool()
    def health_check(folder: str | None = None) -> list[dict[str, Any]]:
        """Check power state and VMware Tools status for every VM in a folder."""
        try:
            mgr = _get_manager()
            vms = mgr.find_vms_in_folder(folder) or []
            results = []
            for raw_vm in vms:
                vm_name = getattr(raw_vm, "name", str(raw_vm))
                try:
                    vm = mgr.get_vm(vm_name, folder)
                    power = vm.get_power_status()
                    tools = vm.get_guest_tools_status()
                    results.append({
                        "name": vm_name,
                        "power": power,
                        "tools": tools,
                        "healthy": power == "poweredOn" and tools == "guestToolsRunning",
                    })
                except Exception as e:
                    _logger.warning("health_check failed for VM %s: %s", vm_name, e)
                    results.append({"name": vm_name, "error": str(e)})
            return results
        except Exception as e:
            _logger.exception("health_check failed")
            return [{"error": str(e)}]

    @mcp.tool()
    def get_datastore_info() -> dict[str, Any]:
        """Return storage capacity and usage statistics."""
        try:
            return _get_manager().get_datastore_info() or {}
        except Exception as e:
            _logger.exception("get_datastore_info failed")
            return {"error": str(e)}

    @mcp.tool()
    def run_tests(
        test_path: str,
        tags: list[str] | None = None,
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run Robot Framework tests and return pass/fail counts.

        test_path must be a path inside the project directory.
        Variable keys must match [A-Za-z_][A-Za-z0-9_]*.
        """
        resolved = os.path.realpath(test_path)
        if not (resolved == _PROJECT_ROOT or resolved.startswith(_PROJECT_ROOT + os.sep)):
            return {"error": "test_path must be inside the project directory"}

        output_dir = os.path.join(_PROJECT_ROOT, "tests")
        cmd = ["robot", "--outputdir", output_dir]

        for tag in (tags or []):
            if not tag or tag.startswith("-"):
                return {"error": f"Invalid tag value: {tag!r}"}
            cmd += ["--include", tag]

        for k, v in (variables or {}).items():
            if not _VAR_NAME_RE.match(k):
                return {"error": f"Invalid variable name: {k!r}"}
            cmd += ["--variable", f"{k}:{v}"]

        cmd.append(resolved)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=600,
            )
            rc = result.returncode
        except FileNotFoundError:
            return {"error": "'robot' not found — install robotframework"}
        except subprocess.TimeoutExpired:
            return {"error": "Test run timed out after 600s"}

        xml_path = os.path.join(output_dir, "output.xml")
        try:
            stat = _xml_parse(xml_path).getroot().find(".//statistics/total/stat")
            if stat is None:
                return {"exit_code": rc, "parse_warning": "statistics node not found in output.xml"}
            return {
                "exit_code": rc,
                "passed": int(stat.get("pass", 0)),
                "failed": int(stat.get("fail", 0)),
            }
        except Exception as exc:
            _logger.warning("Failed to parse output.xml: %s", exc)
            return {"exit_code": rc, "parse_warning": str(exc)}
