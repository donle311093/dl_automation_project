"""Unit tests for mcp_server/tools.py and mcp_server/server.py.

Run with:
    cd automation_framework
    pip install pytest
    pytest tests/unit/test_mcp_tools.py -v

No vSphere connection required — all external calls are mocked.
"""
from __future__ import annotations

import sys
import threading
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub mcp package (not installed in most envs).
# ---------------------------------------------------------------------------

def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


class _FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name
        self._tools: dict = {}

    def tool(self):
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator

    def run(self, transport=None):
        pass


_mcp_fastmcp_mod = _stub("mcp.server.fastmcp", FastMCP=_FakeFastMCP)
_mcp_server_mod = _stub("mcp.server", fastmcp=_mcp_fastmcp_mod)
_mcp_mod = _stub("mcp", server=_mcp_server_mod)
for _k, _m in [
    ("mcp", _mcp_mod),
    ("mcp.server", _mcp_server_mod),
    ("mcp.server.fastmcp", _mcp_fastmcp_mod),
]:
    sys.modules.setdefault(_k, _m)

# ---------------------------------------------------------------------------
# Stub core.factory (avoids needing vSphere libs).
# ---------------------------------------------------------------------------

_core_pkg = _stub("core")
_core_factory_mod = _stub("core.factory", HypervisorFactory=MagicMock())
sys.modules.setdefault("core", _core_pkg)
sys.modules["core.factory"] = _core_factory_mod

# ---------------------------------------------------------------------------
# Import modules under test.
# ---------------------------------------------------------------------------

import mcp_server.tools as tools_mod  # noqa: E402
from mcp_server import server as server_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _CaptureMCP:
    """Minimal MCP substitute that captures registered tool functions."""

    def __init__(self):
        self._tools: dict = {}

    def tool(self):
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator


@pytest.fixture(autouse=True)
def reset_manager():
    tools_mod._manager = None
    yield
    tools_mod._manager = None


@pytest.fixture
def mcp() -> _CaptureMCP:
    cap = _CaptureMCP()
    tools_mod.register(cap)
    return cap


@pytest.fixture
def mgr() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mcp_mgr(mcp, mgr):
    """mcp with _get_manager patched to return mgr for the duration of the test."""
    with patch.object(tools_mod, "_get_manager", return_value=mgr):
        yield mcp, mgr


# ---------------------------------------------------------------------------
# _get_manager — env var validation, singleton, thread safety
# ---------------------------------------------------------------------------

class TestGetManager:
    def test_raises_if_host_empty(self, monkeypatch):
        monkeypatch.delenv("VSPHERE_HOST", raising=False)
        monkeypatch.setenv("VSPHERE_USER", "u")
        monkeypatch.setenv("VSPHERE_PASS", "p")
        with pytest.raises(EnvironmentError, match="VSPHERE_HOST"):
            tools_mod._get_manager()

    def test_raises_if_user_empty(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "h")
        monkeypatch.delenv("VSPHERE_USER", raising=False)
        monkeypatch.setenv("VSPHERE_PASS", "p")
        with pytest.raises(EnvironmentError):
            tools_mod._get_manager()

    def test_raises_if_password_empty(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "h")
        monkeypatch.setenv("VSPHERE_USER", "u")
        monkeypatch.delenv("VSPHERE_PASS", raising=False)
        with pytest.raises(EnvironmentError):
            tools_mod._get_manager()

    def test_raises_for_non_integer_port(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "h")
        monkeypatch.setenv("VSPHERE_USER", "u")
        monkeypatch.setenv("VSPHERE_PASS", "p")
        monkeypatch.setenv("VSPHERE_PORT", "not-a-number")
        with pytest.raises(EnvironmentError, match="VSPHERE_PORT"):
            tools_mod._get_manager()

    def test_creates_and_connects_manager(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "myhost")
        monkeypatch.setenv("VSPHERE_USER", "myuser")
        monkeypatch.setenv("VSPHERE_PASS", "mypass")
        monkeypatch.delenv("VSPHERE_PORT", raising=False)
        monkeypatch.delenv("VSPHERE_NO_SSL_VERIFY", raising=False)
        fake_mgr = MagicMock()
        with patch.object(_core_factory_mod, "HypervisorFactory") as hf:
            hf.create.return_value = fake_mgr
            result = tools_mod._get_manager()
        assert result is fake_mgr
        fake_mgr.connect.assert_called_once()

    def test_returns_same_instance_on_repeated_calls(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "h")
        monkeypatch.setenv("VSPHERE_USER", "u")
        monkeypatch.setenv("VSPHERE_PASS", "p")
        fake_mgr = MagicMock()
        with patch.object(_core_factory_mod, "HypervisorFactory") as hf:
            hf.create.return_value = fake_mgr
            m1 = tools_mod._get_manager()
            m2 = tools_mod._get_manager()
        assert m1 is m2
        fake_mgr.connect.assert_called_once()

    def test_thread_safety_initialises_once(self, monkeypatch):
        monkeypatch.setenv("VSPHERE_HOST", "h")
        monkeypatch.setenv("VSPHERE_USER", "u")
        monkeypatch.setenv("VSPHERE_PASS", "p")
        fake_mgr = MagicMock()
        create_calls: list = []

        def counting_create(*a, **kw):
            create_calls.append(1)
            return fake_mgr

        with patch.object(_core_factory_mod, "HypervisorFactory") as hf:
            hf.create.side_effect = counting_create
            barrier = threading.Barrier(10)
            results: list = []

            def worker():
                barrier.wait()
                results.append(tools_mod._get_manager())

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(create_calls) == 1
        assert all(r is fake_mgr for r in results)


# ---------------------------------------------------------------------------
# Serialiser helpers
# ---------------------------------------------------------------------------

class TestSerializers:
    def test_vm_list_extracts_name_attribute(self):
        vm = MagicMock()
        vm.name = "vm-a"
        assert tools_mod._vm_list([vm]) == [{"name": "vm-a"}]

    def test_vm_list_falls_back_to_str(self):
        obj = object()
        result = tools_mod._vm_list([obj])
        assert result[0]["name"] == str(obj)

    def test_vm_list_empty_and_none(self):
        assert tools_mod._vm_list([]) == []
        assert tools_mod._vm_list(None) == []

    def test_snap_list_extracts_names(self):
        s = MagicMock()
        s.name = "snap-1"
        assert tools_mod._snap_list([s]) == [{"name": "snap-1"}]


# ---------------------------------------------------------------------------
# list_vms
# ---------------------------------------------------------------------------

class TestListVms:
    def test_returns_serialised_vm_list(self, mcp_mgr):
        cap, mgr = mcp_mgr
        vm = MagicMock()
        vm.name = "myvm"
        mgr.find_vms_in_folder.return_value = [vm]
        assert cap._tools["list_vms"](folder="F") == [{"name": "myvm"}]
        mgr.find_vms_in_folder.assert_called_once_with("F")

    def test_returns_error_dict_on_exception(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.find_vms_in_folder.side_effect = RuntimeError("boom")
        result = cap._tools["list_vms"]()
        assert result[0]["error"] == "boom"


# ---------------------------------------------------------------------------
# get_vm_info / get_power_status
# ---------------------------------------------------------------------------

class TestVmInfoAndStatus:
    def test_get_vm_info_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.get_vm_info.return_value = {"cpus": 4}
        assert cap._tools["get_vm_info"]("vm1") == {"cpus": 4}

    def test_get_vm_info_error(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.side_effect = ValueError("not found")
        assert "error" in cap._tools["get_vm_info"]("vm1")

    def test_get_power_status_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.get_power_status.return_value = "poweredOn"
        assert cap._tools["get_power_status"]("vm1") == {"vm": "vm1", "status": "poweredOn"}

    def test_get_power_status_error(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.side_effect = RuntimeError("unreachable")
        assert "error" in cap._tools["get_power_status"]("vm1")


# ---------------------------------------------------------------------------
# Power operations
# ---------------------------------------------------------------------------

class TestPowerOps:
    @pytest.mark.parametrize("tool,method", [
        ("power_on", "power_on"),
        ("power_off", "power_off"),
        ("restart_vm", "reboot"),
    ])
    def test_success(self, mcp_mgr, tool, method):
        cap, mgr = mcp_mgr
        getattr(mgr.get_vm.return_value, method).return_value = True
        assert cap._tools[tool]("vm1")["success"] is True

    @pytest.mark.parametrize("tool,method", [
        ("power_on", "power_on"),
        ("power_off", "power_off"),
        ("restart_vm", "reboot"),
    ])
    def test_operation_failure(self, mcp_mgr, tool, method):
        cap, mgr = mcp_mgr
        getattr(mgr.get_vm.return_value, method).return_value = False
        assert cap._tools[tool]("vm1")["success"] is False

    @pytest.mark.parametrize("tool", ["power_on", "power_off", "restart_vm"])
    def test_exception_returns_error(self, mcp_mgr, tool):
        cap, mgr = mcp_mgr
        mgr.get_vm.side_effect = RuntimeError("conn fail")
        result = cap._tools[tool]("vm1")
        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Snapshot operations
# ---------------------------------------------------------------------------

class TestSnapshotOps:
    def test_list_snapshots_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        s = MagicMock()
        s.name = "s1"
        mgr.get_vm.return_value.get_snapshots.return_value = [s]
        assert cap._tools["list_snapshots"]("vm1") == [{"name": "s1"}]

    def test_list_snapshots_error(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.side_effect = RuntimeError("fail")
        assert cap._tools["list_snapshots"]("vm1")[0]["error"] == "fail"

    def test_create_snapshot_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.create_snapshot.return_value = True
        result = cap._tools["create_snapshot"]("vm1", "snap1")
        assert result["success"] is True
        assert "snap1" in result["message"]

    def test_revert_with_named_snapshot(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.revert_to_snapshot.return_value = True
        result = cap._tools["revert_snapshot"]("vm1", snap_name="snap1")
        assert result["success"] is True
        mgr.get_vm.return_value.revert_to_snapshot.assert_called_once_with("snap1")

    def test_revert_without_name_uses_current(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.revert_to_current_snapshot.return_value = True
        result = cap._tools["revert_snapshot"]("vm1")
        assert result["success"] is True
        mgr.get_vm.return_value.revert_to_current_snapshot.assert_called_once()

    def test_delete_snapshot(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.delete_snapshot.return_value = True
        result = cap._tools["delete_snapshot"]("vm1", "snap1")
        assert result["success"] is True
        assert "snap1" in result["message"]


# ---------------------------------------------------------------------------
# clone_vm
# ---------------------------------------------------------------------------

class TestCloneVm:
    def test_clone_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.clone.return_value = True
        result = cap._tools["clone_vm"]("src", "dst", "folder")
        assert result["success"] is True
        assert "dst" in result["message"]

    def test_clone_failure(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.clone.return_value = False
        assert cap._tools["clone_vm"]("src", "dst", "folder")["success"] is False

    def test_clone_exception(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.side_effect = RuntimeError("fail")
        result = cap._tools["clone_vm"]("src", "dst", "folder")
        assert result["success"] is False
        assert "error" in result

    def test_clone_forwards_optional_params(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_vm.return_value.clone.return_value = True
        cap._tools["clone_vm"]("src", "dst", "tgt", cpus=4, memory_mb=8192, power_on=True)
        mgr.get_vm.return_value.clone.assert_called_once_with(
            target_folder_name="tgt",
            new_vm_name="dst",
            snapshot_name=None,
            num_cpus=4,
            memory_mb=8192,
            power_on=True,
        )


# ---------------------------------------------------------------------------
# execute_command
# ---------------------------------------------------------------------------

class TestExecuteCommand:
    def test_returns_error_when_vm_user_missing(self, mcp, monkeypatch):
        monkeypatch.delenv("VM_USER", raising=False)
        monkeypatch.delenv("VM_PASS", raising=False)
        result = mcp._tools["execute_command"]("vm1", "ls")
        assert "VM_USER" in result["error"]

    def test_returns_error_when_login_fails(self, mcp_mgr, monkeypatch):
        cap, mgr = mcp_mgr
        monkeypatch.setenv("VM_USER", "user")
        monkeypatch.setenv("VM_PASS", "pass")
        mgr.get_vm.return_value.login.return_value = False
        result = cap._tools["execute_command"]("vm1", "ls")
        assert "login failed" in result["error"].lower()

    def test_success_returns_dict(self, mcp_mgr, monkeypatch):
        cap, mgr = mcp_mgr
        monkeypatch.setenv("VM_USER", "user")
        monkeypatch.setenv("VM_PASS", "pass")
        vm = mgr.get_vm.return_value
        vm.login.return_value = True
        vm.execute_command.return_value = {"stdout": "hello", "exit_code": 0}
        assert cap._tools["execute_command"]("vm1", "echo hello") == {
            "stdout": "hello", "exit_code": 0
        }

    def test_non_dict_result_wrapped(self, mcp_mgr, monkeypatch):
        cap, mgr = mcp_mgr
        monkeypatch.setenv("VM_USER", "user")
        monkeypatch.setenv("VM_PASS", "pass")
        vm = mgr.get_vm.return_value
        vm.login.return_value = True
        vm.execute_command.return_value = "raw string"
        assert cap._tools["execute_command"]("vm1", "ls") == {"output": "raw string"}

    def test_none_result_wrapped(self, mcp_mgr, monkeypatch):
        cap, mgr = mcp_mgr
        monkeypatch.setenv("VM_USER", "user")
        monkeypatch.setenv("VM_PASS", "pass")
        vm = mgr.get_vm.return_value
        vm.login.return_value = True
        vm.execute_command.return_value = None
        assert cap._tools["execute_command"]("vm1", "ls") == {"output": ""}


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_status_per_vm(self, mcp_mgr):
        cap, mgr = mcp_mgr
        raw = MagicMock()
        raw.name = "vm1"
        mgr.find_vms_in_folder.return_value = [raw]
        vm = mgr.get_vm.return_value
        vm.get_power_status.return_value = "poweredOn"
        vm.get_guest_tools_status.return_value = "guestToolsRunning"
        result = cap._tools["health_check"]()
        assert result[0] == {
            "name": "vm1", "power": "poweredOn",
            "tools": "guestToolsRunning", "healthy": True,
        }

    def test_per_vm_exception_included_in_results(self, mcp_mgr):
        cap, mgr = mcp_mgr
        good = MagicMock(); good.name = "good"
        bad = MagicMock(); bad.name = "bad"
        mgr.find_vms_in_folder.return_value = [good, bad]

        def _get_vm(name, folder=None):
            if name == "bad":
                raise RuntimeError("unreachable")
            m = MagicMock()
            m.get_power_status.return_value = "poweredOn"
            m.get_guest_tools_status.return_value = "guestToolsRunning"
            return m

        mgr.get_vm.side_effect = _get_vm
        result = cap._tools["health_check"]()
        assert len(result) == 2
        bad_row = next(r for r in result if r["name"] == "bad")
        assert "error" in bad_row

    def test_outer_exception_returns_error_list(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.find_vms_in_folder.side_effect = RuntimeError("conn lost")
        result = cap._tools["health_check"]()
        assert result[0]["error"] == "conn lost"


# ---------------------------------------------------------------------------
# get_datastore_info
# ---------------------------------------------------------------------------

class TestGetDatastoreInfo:
    def test_success(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_datastore_info.return_value = {"free_gb": 500}
        assert cap._tools["get_datastore_info"]() == {"free_gb": 500}

    def test_error(self, mcp_mgr):
        cap, mgr = mcp_mgr
        mgr.get_datastore_info.side_effect = RuntimeError("fail")
        assert "error" in cap._tools["get_datastore_info"]()


# ---------------------------------------------------------------------------
# run_tests
# ---------------------------------------------------------------------------

class TestRunTests:
    def test_rejects_path_outside_project(self, mcp):
        result = mcp._tools["run_tests"]("/etc/passwd")
        assert "error" in result
        assert "project directory" in result["error"]

    def test_rejects_invalid_variable_key(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            result = mcp._tools["run_tests"](str(script), variables={"--inject": "val"})
        assert "variable name" in result["error"].lower()

    def test_rejects_tag_starting_with_dash(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            result = mcp._tools["run_tests"](str(script), tags=["--listener"])
        assert "error" in result

    def test_robot_not_found(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = mcp._tools["run_tests"](str(script))
        assert "robot" in result["error"].lower()

    def test_timeout_reported(self, mcp, tmp_path):
        import subprocess
        script = tmp_path / "suite.robot"
        script.write_text("")
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("robot", 600)):
                result = mcp._tools["run_tests"](str(script))
        assert any(kw in result["error"].lower() for kw in ("timeout", "timed out"))

    def test_passes_outputdir_flag_to_robot(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        xml_dir = tmp_path / "tests"
        xml_dir.mkdir()
        (xml_dir / "output.xml").write_text(
            '<?xml version="1.0"?><robot>'
            '<statistics><total><stat pass="2" fail="0">All</stat></total></statistics>'
            '</robot>'
        )
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            with patch("subprocess.run", return_value=MagicMock(returncode=0)) as sp:
                mcp._tools["run_tests"](str(script))
        cmd = sp.call_args[0][0]
        assert "--outputdir" in cmd

    def test_returns_pass_fail_counts(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        xml_dir = tmp_path / "tests"
        xml_dir.mkdir()
        (xml_dir / "output.xml").write_text(
            '<?xml version="1.0"?><robot>'
            '<statistics><total><stat pass="3" fail="1">All</stat></total></statistics>'
            '</robot>'
        )
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            with patch("subprocess.run", return_value=MagicMock(returncode=1)):
                result = mcp._tools["run_tests"](str(script))
        assert result == {"exit_code": 1, "passed": 3, "failed": 1}

    def test_xml_parse_failure_returns_warning_key(self, mcp, tmp_path):
        script = tmp_path / "suite.robot"
        script.write_text("")
        with patch.object(tools_mod, "_PROJECT_ROOT", str(tmp_path)):
            with patch("subprocess.run", return_value=MagicMock(returncode=0)):
                result = mcp._tools["run_tests"](str(script))
        assert result["exit_code"] == 0
        assert "parse_warning" in result


# ---------------------------------------------------------------------------
# server.run()
# ---------------------------------------------------------------------------

class TestServer:
    def test_run_creates_new_mcp_each_call(self):
        """A new FastMCP instance must be created on each run() — no singleton."""
        created: list = []

        class Tracking(_FakeFastMCP):
            def __init__(self, name):
                super().__init__(name)
                created.append(self)

        with patch("mcp_server.server.FastMCP", Tracking):
            with patch("mcp_server.tools.register"):
                server_mod.run()
                server_mod.run()

        assert len(created) == 2

    def test_run_calls_register_then_mcp_run(self):
        fake_instance = _FakeFastMCP("test")
        with patch("mcp_server.server.FastMCP", return_value=fake_instance):
            with patch("mcp_server.tools.register") as reg:
                server_mod.run()
        reg.assert_called_once_with(fake_instance)
