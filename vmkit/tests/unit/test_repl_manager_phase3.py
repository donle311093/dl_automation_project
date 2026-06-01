"""Unit tests for ManagerREPL Phase 3 test-runner commands.

Run with:
    cd vmkit
    pip install pytest
    pytest tests/unit/test_repl_manager_phase3.py -v

No vSphere connection required — all external calls are mocked.
"""

import os
import subprocess
import sys
import textwrap
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies so the module loads without them installed.
# ---------------------------------------------------------------------------

def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod

_stub("prompt_toolkit", PromptSession=MagicMock)
_stub("prompt_toolkit.completion", Completer=object, Completion=object)
_stub("prompt_toolkit.history", FileHistory=MagicMock)
_stub("rich")
_stub("rich.console", Console=MagicMock)
_stub("rich.table", Table=MagicMock)
_stub("rich.live", Live=MagicMock)
_stub("rich.spinner", Spinner=MagicMock)


@dataclass
class _SessionStateStub:
    platform: str = "vsphere"
    host: str = ""
    manager: object = None
    guest_user: Optional[str] = None
    guest_pass: Optional[str] = None
    output_format: str = "table"
    debug: bool = False
    no_log: bool = True


_stub("cli.session", SessionState=_SessionStateStub)

# Stub cli.output — tests assert on these mocks.
_render = MagicMock()
_print_error = MagicMock()
_print_warning = MagicMock()
_print_success = MagicMock()

_stub(
    "cli.output",
    render=_render,
    spinner=MagicMock(),
    confirm=MagicMock(return_value=False),
    print_success=_print_success,
    print_error=_print_error,
    print_warning=_print_warning,
    audit=MagicMock(),
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from cli.repl_manager import ManagerREPL  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeSession:
    platform: str = "vsphere"
    host: str = "vc.local"
    manager: object = None
    guest_user: Optional[str] = None
    guest_pass: Optional[str] = None
    output_format: str = "table"
    debug: bool = False
    no_log: bool = True


def _make_repl(guest_user=None, guest_pass=None):
    session = FakeSession(guest_user=guest_user, guest_pass=guest_pass)
    repl = ManagerREPL.__new__(ManagerREPL)
    repl.session = session
    repl._prompt = MagicMock()
    return repl


@pytest.fixture(autouse=True)
def reset_mocks():
    _render.reset_mock()
    _print_error.reset_mock()
    _print_warning.reset_mock()
    _print_success.reset_mock()
    yield


# ===========================================================================
# cmd_test — routing
# ===========================================================================

class TestCmdTestRouting:
    def test_no_args_prints_usage(self):
        repl = _make_repl()
        repl.cmd_test([])
        _print_error.assert_called_once()
        assert "Usage" in _print_error.call_args[0][0]

    def test_unknown_subcommand_prints_error(self):
        repl = _make_repl()
        repl.cmd_test(["bogus"])
        _print_error.assert_called_once()
        assert "Unknown" in _print_error.call_args[0][0]

    def test_routes_to_test_list(self):
        repl = _make_repl()
        with patch.object(repl, "_test_list") as m:
            repl.cmd_test(["list", "tests/"])
            m.assert_called_once_with(["tests/"])

    def test_routes_to_test_run(self):
        repl = _make_repl()
        with patch.object(repl, "_test_run") as m:
            repl.cmd_test(["run", "tests/foo.robot"])
            m.assert_called_once_with(["tests/foo.robot"])

    def test_routes_to_test_report(self):
        repl = _make_repl()
        with patch.object(repl, "_test_report") as m:
            repl.cmd_test(["report"])
            m.assert_called_once_with([])


# ===========================================================================
# _test_list
# ===========================================================================

class TestTestList:
    def test_renders_found_robot_files(self, tmp_path):
        (tmp_path / "a.robot").touch()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.robot").touch()

        repl = _make_repl()
        with patch("cli.repl_manager._PROJECT_ROOT", str(tmp_path)), \
             patch("os.path.realpath", side_effect=lambda p: str(tmp_path) if p in (".", str(tmp_path)) else str(tmp_path / os.path.basename(p))):
            repl._test_list([str(tmp_path)])

        _render.assert_called_once()
        rows = _render.call_args[0][0]
        assert len(rows) == 2
        assert all("file" in r for r in rows)

    def test_no_robot_files_prints_warning(self, tmp_path):
        repl = _make_repl()
        with patch("cli.repl_manager._PROJECT_ROOT", str(tmp_path)), \
             patch("os.path.realpath", side_effect=lambda p: str(tmp_path) if p in (".", str(tmp_path)) else str(tmp_path / os.path.basename(p))):
            repl._test_list([str(tmp_path)])

        _print_warning.assert_called_once()
        _render.assert_not_called()

    def test_path_outside_project_root_rejected(self):
        repl = _make_repl()
        project_root = os.path.realpath(".")
        outside = os.path.dirname(project_root)

        repl._test_list([outside])

        _print_error.assert_called_once()
        assert "project root" in _print_error.call_args[0][0]
        _render.assert_not_called()


# ===========================================================================
# _test_run
# ===========================================================================

class TestTestRun:
    def _run(self, repl, args, mock_rc=0):
        with patch("subprocess.run", return_value=MagicMock(returncode=mock_rc)) as m:
            repl._test_run(args)
        return m

    def test_calls_robot_binary(self):
        repl = _make_repl()
        m = self._run(repl, ["tests/suite.robot"])
        cmd = m.call_args[0][0]
        assert cmd[0] == "robot"
        assert any("suite.robot" in s for s in cmd)

    def test_injects_vsphere_host(self):
        repl = _make_repl()
        m = self._run(repl, ["tests/suite.robot"])
        cmd = m.call_args[0][0]
        assert "VSPHERE_HOST:vc.local" in " ".join(cmd)

    def test_password_not_in_subprocess_args(self):
        repl = _make_repl(guest_user="admin", guest_pass="s3cr3t")
        m = self._run(repl, ["tests/suite.robot"])
        cmd_str = " ".join(m.call_args[0][0])
        assert "s3cr3t" not in cmd_str
        assert "VM_PASS:%{VM_PASS}" in cmd_str

    def test_password_injected_in_env(self):
        repl = _make_repl(guest_user="admin", guest_pass="s3cr3t")
        m = self._run(repl, ["tests/suite.robot"])
        assert m.call_args[1]["env"]["VM_PASS"] == "s3cr3t"

    def test_tag_becomes_include_filter(self):
        repl = _make_repl()
        m = self._run(repl, ["tests/suite.robot", "--tag", "smoke"])
        cmd = m.call_args[0][0]
        assert "--include" in cmd
        assert "smoke" in cmd

    def test_invalid_suite_rejected_no_subprocess(self):
        repl = _make_repl()
        with patch("subprocess.run") as m:
            repl._test_run(["tests/suite.robot", "--suite", "../../evil"])
        _print_error.assert_called_once()
        assert "Invalid --suite" in _print_error.call_args[0][0]
        m.assert_not_called()

    def test_valid_suite_passes_through(self):
        repl = _make_repl()
        m = self._run(repl, ["tests/suite.robot", "--suite", "My-Suite"])
        cmd = m.call_args[0][0]
        assert "--suite" in cmd
        assert "My-Suite" in cmd

    def test_invalid_variable_format_rejected(self):
        repl = _make_repl()
        with patch("subprocess.run") as m:
            repl._test_run(["tests/suite.robot", "--variable", "../../etc/passwd:val"])
        _print_error.assert_called_once()
        assert "Invalid --variable" in _print_error.call_args[0][0]
        m.assert_not_called()

    def test_valid_variable_passes_through(self):
        repl = _make_repl()
        m = self._run(repl, ["tests/suite.robot", "--variable", "MY_VAR:hello"])
        cmd = m.call_args[0][0]
        assert "MY_VAR:hello" in cmd

    def test_robot_not_on_path_gives_friendly_error(self):
        repl = _make_repl()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            repl._test_run(["tests/suite.robot"])
        _print_error.assert_called_once()
        msg = _print_error.call_args[0][0].lower()
        assert "robot" in msg
        assert "not found" in msg or "install" in msg

    def test_timeout_expired_gives_friendly_error(self):
        repl = _make_repl()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="robot", timeout=5)):
            repl._test_run(["tests/suite.robot", "--timeout", "5"])
        _print_error.assert_called_once()
        assert "timed out" in _print_error.call_args[0][0].lower()

    def test_rc_zero_prints_success(self):
        repl = _make_repl()
        self._run(repl, ["tests/suite.robot"], mock_rc=0)
        _print_success.assert_called_once()

    def test_nonzero_rc_prints_warning(self):
        repl = _make_repl()
        self._run(repl, ["tests/suite.robot"], mock_rc=1)
        _print_warning.assert_called_once()


# ===========================================================================
# _test_report
# ===========================================================================

_VALID_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <robot>
      <statistics>
        <total>
          <stat pass="5" fail="2">All Tests</stat>
        </total>
      </statistics>
    </robot>
""")

_BAD_XML = "<<not xml>>"

_WRONG_ATTR_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <robot>
      <statistics>
        <total>
          <stat pass="N/A" fail="??">All Tests</stat>
        </total>
      </statistics>
    </robot>
""")

_ALL_PASS_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <robot>
      <statistics>
        <total>
          <stat pass="3" fail="0">All Tests</stat>
        </total>
      </statistics>
    </robot>
""")


class TestTestReport:
    def _report_with_xml(self, repl, tmp_path, content, filename="output.xml"):
        xml_file = tmp_path / filename
        xml_file.write_text(content)
        project_root = str(tmp_path)
        with patch("cli.repl_manager._PROJECT_ROOT", project_root), \
             patch("os.path.realpath", side_effect=lambda p: project_root if p == "." else str(tmp_path / os.path.basename(p))):
            repl._test_report([f"--output-xml={xml_file}"])

    def test_path_traversal_rejected(self):
        repl = _make_repl()
        repl._test_report(["--output-xml=/etc/passwd"])
        _print_error.assert_called_once()
        assert "project directory" in _print_error.call_args[0][0]

    def test_valid_xml_renders_stats(self, tmp_path):
        repl = _make_repl()
        self._report_with_xml(repl, tmp_path, _VALID_XML)
        _render.assert_called_once()
        data = _render.call_args[0][0]
        assert data["passed"] == 5
        assert data["failed"] == 2
        assert data["total"] == 7

    def test_failures_emit_warning(self, tmp_path):
        repl = _make_repl()
        self._report_with_xml(repl, tmp_path, _VALID_XML)
        _print_warning.assert_called_once()
        assert "2 test(s) failed" in _print_warning.call_args[0][0]

    def test_all_pass_no_warning(self, tmp_path):
        repl = _make_repl()
        self._report_with_xml(repl, tmp_path, _ALL_PASS_XML)
        _print_warning.assert_not_called()

    def test_malformed_xml_prints_parse_error(self, tmp_path):
        repl = _make_repl()
        self._report_with_xml(repl, tmp_path, _BAD_XML)
        _print_error.assert_called_once()
        assert "parse" in _print_error.call_args[0][0].lower()

    def test_non_integer_xml_attrs_print_error(self, tmp_path):
        repl = _make_repl()
        self._report_with_xml(repl, tmp_path, _WRONG_ATTR_XML)
        _print_error.assert_called_once()
        assert "Unexpected value" in _print_error.call_args[0][0]

    def test_missing_file_prints_error(self):
        repl = _make_repl()
        project_root = os.path.realpath(".")
        with patch("os.path.realpath", side_effect=lambda p: project_root if p == "." else os.path.join(project_root, os.path.basename(p))):
            repl._test_report(["--output-xml=tests/output.xml"])
        # Either file-not-found or path-traversal error is acceptable
        _print_error.assert_called_once()


# ===========================================================================
# Phase 4 — cmd_bulk
# ===========================================================================

def _make_vm(name):
    vm = MagicMock()
    vm.name = name
    return vm


def _make_repl_with_manager(vm_names, guest_user=None, guest_pass=None):
    repl = _make_repl(guest_user=guest_user, guest_pass=guest_pass)
    raw_vms = [_make_vm(n) for n in vm_names]
    vm_mgrs = {n: MagicMock() for n in vm_names}
    repl.session.manager = MagicMock()
    repl.session.manager.find_vms_in_folder.return_value = raw_vms
    repl.session.manager.get_vm.side_effect = lambda name, folder: vm_mgrs.get(name)
    return repl, vm_mgrs


class TestCmdBulk:
    def test_empty_folder_prints_warning(self):
        repl = _make_repl()
        repl.session.manager = MagicMock()
        repl.session.manager.find_vms_in_folder.return_value = []
        repl.cmd_bulk(["start", "--folder", "CI", "--force"])
        _print_warning.assert_called_once()
        assert "No VMs" in _print_warning.call_args[0][0]

    def test_aborted_confirm_does_nothing(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1", "vm2"])
        # confirm returns False by default (stubbed above)
        repl.cmd_bulk(["start", "--folder", "CI"])
        _print_warning.assert_called_once()
        assert "Aborted" in _print_warning.call_args[0][0]
        for vm in vm_mgrs.values():
            vm.power_on.assert_not_called()

    def test_bulk_start_calls_power_on(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1", "vm2"])
        repl.cmd_bulk(["start", "--folder", "CI", "--force"])
        for vm in vm_mgrs.values():
            vm.power_on.assert_called_once()

    def test_bulk_stop_calls_power_off(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1", "vm2"])
        repl.cmd_bulk(["stop", "--folder", "CI", "--force"])
        for vm in vm_mgrs.values():
            vm.power_off.assert_called_once()

    def test_bulk_snapshot_calls_create_snapshot(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1"])
        repl.cmd_bulk(["snapshot", "--folder", "CI", "--force", "--snapshot-name", "my-snap"])
        vm_mgrs["vm1"].create_snapshot.assert_called_once_with("my-snap")

    def test_bulk_revert_calls_revert_to_current(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1"])
        repl.cmd_bulk(["revert", "--folder", "CI", "--force"])
        vm_mgrs["vm1"].revert_to_current_snapshot.assert_called_once()

    def test_partial_failure_prints_warning_summary(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1", "vm2"])
        vm_mgrs["vm2"].power_on.side_effect = RuntimeError("host unreachable")
        repl.cmd_bulk(["start", "--folder", "CI", "--force"])
        _print_warning.assert_called()
        last = _print_warning.call_args_list[-1][0][0]
        assert "1 OK" in last and "1 failed" in last

    def test_all_success_prints_success_summary(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1", "vm2"])
        repl.cmd_bulk(["start", "--folder", "CI", "--force"])
        # last print_success call should be the summary
        summary = _print_success.call_args_list[-1][0][0]
        assert "2 OK" in summary and "0 failed" in summary

    def test_audit_called_after_bulk(self):
        repl, _ = _make_repl_with_manager(["vm1"])
        with patch("cli.repl_manager.audit") as mock_audit:
            repl.cmd_bulk(["stop", "--folder", "CI", "--force"])
        mock_audit.assert_called_once()
        assert "bulk-stop" in mock_audit.call_args[0][1]


# ===========================================================================
# Phase 4 — cmd_watch
# ===========================================================================

class TestCmdWatch:
    def test_no_subcommand_prints_error(self):
        repl = _make_repl()
        repl.cmd_watch([])
        _print_error.assert_called_once()
        assert "Usage" in _print_error.call_args[0][0]

    def test_dispatches_subcommand_once_then_stops(self):
        repl = _make_repl()
        call_count = {"n": 0}

        def fake_sleep(_):
            call_count["n"] += 1
            raise KeyboardInterrupt

        with patch("time.sleep", side_effect=fake_sleep), \
             patch.object(repl, "dispatch") as mock_dispatch:
            repl.cmd_watch(["health-check", "--folder", "CI"])

        mock_dispatch.assert_called_once_with(["health-check", "--folder", "CI"])

    def test_interval_flag_passed_to_sleep(self):
        repl = _make_repl()
        slept = []

        def fake_sleep(n):
            slept.append(n)
            raise KeyboardInterrupt

        with patch("time.sleep", side_effect=fake_sleep), \
             patch.object(repl, "dispatch"):
            repl.cmd_watch(["--interval", "10", "list-vms"])

        assert slept == [10]

    def test_keyboard_interrupt_exits_cleanly(self):
        repl = _make_repl()
        with patch("time.sleep", side_effect=KeyboardInterrupt), \
             patch.object(repl, "dispatch"):
            repl.cmd_watch(["list-vms"])  # must not raise


# ===========================================================================
# Phase 4 fix — additional tests for review findings
# ===========================================================================

class TestCmdBulkFixes:
    """Cover HIGH-1 (find_vms_in_folder raises) and HIGH-2 (KeyboardInterrupt re-raised)."""

    def test_find_vms_raises_prints_error_and_audits(self):
        repl = _make_repl()
        repl.session.manager = MagicMock()
        repl.session.manager.find_vms_in_folder.side_effect = ConnectionError("network error")
        with patch("cli.repl_manager.audit") as mock_audit:
            repl.cmd_bulk(["start", "--folder", "CI", "--force"])
        _print_error.assert_called_once()
        assert "Failed to list" in _print_error.call_args[0][0]
        mock_audit.assert_called_once()
        assert "ERROR" in mock_audit.call_args[0]

    def test_keyboard_interrupt_in_loop_propagates(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1"])
        vm_mgrs["vm1"].power_on.side_effect = KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            repl.cmd_bulk(["start", "--folder", "CI", "--force"])

    def test_system_exit_in_loop_propagates(self):
        repl, vm_mgrs = _make_repl_with_manager(["vm1"])
        vm_mgrs["vm1"].power_on.side_effect = SystemExit(1)
        with pytest.raises(SystemExit):
            repl.cmd_bulk(["start", "--folder", "CI", "--force"])


class TestCmdWatchFixes:
    """Cover CRITICAL-1 (allowlist), CRITICAL-2 (TTY check), MEDIUM-1 (interval bound)."""

    def test_destructive_command_rejected(self):
        repl = _make_repl()
        for cmd in ["delete-vm", "delete-folder", "delete-all-vms", "clone"]:
            _print_error.reset_mock()
            repl.cmd_watch([cmd, "--folder", "prod", "--force"])
            _print_error.assert_called_once()
            assert "not allowed" in _print_error.call_args[0][0].lower()

    def test_allowed_command_accepted(self):
        repl = _make_repl()
        with patch("time.sleep", side_effect=KeyboardInterrupt), \
             patch.object(repl, "dispatch"):
            repl.cmd_watch(["health-check", "--folder", "CI"])
        _print_error.assert_not_called()

    def test_interval_zero_rejected(self):
        repl = _make_repl()
        repl.cmd_watch(["--interval", "0", "list-vms"])
        _print_error.assert_called_once()
        assert "at least 1" in _print_error.call_args[0][0]

    def test_interval_negative_rejected(self):
        repl = _make_repl()
        repl.cmd_watch(["--interval", "-5", "list-vms"])
        _print_error.assert_called_once()
        assert "at least 1" in _print_error.call_args[0][0]

    def test_non_tty_emits_separator_not_ansi(self, capsys):
        repl = _make_repl()
        call_n = {"n": 0}

        def fake_sleep(_):
            call_n["n"] += 1
            raise KeyboardInterrupt

        with patch("sys.stdout.isatty", return_value=False), \
             patch("time.sleep", side_effect=fake_sleep), \
             patch.object(repl, "dispatch"):
            repl.cmd_watch(["list-vms"])

        captured = capsys.readouterr().out
        assert "\033[" not in captured
        assert "---" in captured

    def test_tty_emits_ansi_clear(self, capsys):
        repl = _make_repl()

        def fake_sleep(_):
            raise KeyboardInterrupt

        with patch("sys.stdout.isatty", return_value=True), \
             patch("time.sleep", side_effect=fake_sleep), \
             patch.object(repl, "dispatch"):
            repl.cmd_watch(["list-vms"])

        captured = capsys.readouterr().out
        assert "\033[2J" in captured

    def test_audit_logged_on_watch_start(self):
        repl = _make_repl()
        with patch("time.sleep", side_effect=KeyboardInterrupt), \
             patch.object(repl, "dispatch"), \
             patch("cli.repl_manager.audit") as mock_audit:
            repl.cmd_watch(["list-vms"])
        assert mock_audit.call_count >= 1
        first_call_action = mock_audit.call_args_list[0][0][1]
        assert "watch-start" in first_call_action
