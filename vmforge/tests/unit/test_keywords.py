from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from framework.plugins.base import CommandResult, VMHandle
from framework.robot.keywords.VmForgeKeywords import (
    VmForgeKeywords,
    _MISSING,
    _traverse,
)

_MODULE = "framework.robot.keywords.VmForgeKeywords"


def _make_kw(
    platform_mock: MagicMock,
    executor_mock: MagicMock,
    clone_folder: str = "",
) -> VmForgeKeywords:
    with (
        patch(f"{_MODULE}.get_platform", return_value=platform_mock),
        patch(f"{_MODULE}.get_executor", return_value=executor_mock),
        patch(f"{_MODULE}._platform_kwargs", return_value={}),
        patch(f"{_MODULE}._executor_kwargs", return_value={}),
    ):
        return VmForgeKeywords(
            platform="vsphere",
            executor="powershell",
            clone_folder=clone_folder,
            cfg_path="",
        )


def _handle(**kwargs: Any) -> VMHandle:
    defaults: dict[str, Any] = dict(
        vm_id="clone-01", template="win10", platform="vsphere", folder_name=""
    )
    defaults.update(kwargs)
    return VMHandle(**defaults)


class TestCloneVM:
    def test_stores_vm_handle(self) -> None:
        p = MagicMock()
        h = _handle()
        p.clone_and_snapshot.return_value = h
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        assert kw._vm is h

    def test_explicit_clone_name_is_passed(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "my-clone")
        assert p.clone_and_snapshot.call_args[0][2] == "my-clone"

    def test_default_clone_name_derived_from_template(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10-tpl", "automation")
        assert p.clone_and_snapshot.call_args[0][2] == "vmforge-win10-tpl"

    def test_clone_folder_passed_to_platform(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock(), clone_folder="CI Pool")
        kw.clone_vm("win10", "automation", "clone-01")
        assert p.clone_and_snapshot.call_args[0][3] == "CI Pool"

    def test_raises_when_vm_already_active(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        with pytest.raises(RuntimeError, match="already active"):
            kw.clone_vm("win10", "automation", "clone-02")

    def test_double_clone_does_not_overwrite_first_handle(self) -> None:
        p = MagicMock()
        first = _handle(vm_id="first")
        p.clone_and_snapshot.return_value = first
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "first")
        with pytest.raises(RuntimeError):
            kw.clone_vm("win10", "automation", "second")
        assert kw._vm is first


class TestRevertSnapshot:
    def test_calls_platform_revert(self) -> None:
        p = MagicMock()
        h = _handle()
        p.clone_and_snapshot.return_value = h
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        kw.revert_snapshot("automation")
        p.revert_snapshot.assert_called_once_with(h, "automation")

    def test_raises_when_no_clone(self) -> None:
        kw = _make_kw(MagicMock(), MagicMock())
        with pytest.raises(RuntimeError, match="No VM cloned"):
            kw.revert_snapshot("automation")


class TestTeardownVM:
    def test_calls_platform_teardown(self) -> None:
        p = MagicMock()
        h = _handle()
        p.clone_and_snapshot.return_value = h
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        kw.teardown_vm()
        p.teardown.assert_called_once_with(h)

    def test_clears_vm_reference(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        kw.teardown_vm()
        assert kw._vm is None

    def test_noop_when_no_vm(self) -> None:
        p = MagicMock()
        kw = _make_kw(p, MagicMock())
        kw.teardown_vm()
        p.teardown.assert_not_called()

    def test_second_teardown_is_noop(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        kw.teardown_vm()
        kw.teardown_vm()
        assert p.teardown.call_count == 1

    def test_clone_allowed_after_teardown(self) -> None:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, MagicMock())
        kw.clone_vm("win10", "automation", "clone-01")
        kw.teardown_vm()
        kw.clone_vm("win10", "automation", "clone-02")  # must not raise


class TestExecutePS:
    def _kw_with_vm(self, executor: MagicMock) -> VmForgeKeywords:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle()
        kw = _make_kw(p, executor)
        kw.clone_vm("win10", "automation", "clone-01")
        return kw

    def test_returns_stdout_on_success(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="hello", exit_code=0)
        assert self._kw_with_vm(e).execute_ps("echo hello") == "hello"

    def test_raises_on_nonzero_exit(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="", exit_code=1, stderr="fail")
        with pytest.raises(AssertionError, match="exit 1"):
            self._kw_with_vm(e).execute_ps("bad-cmd")

    def test_error_message_includes_command(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="", exit_code=2, stderr="")
        with pytest.raises(AssertionError, match="Get-Date"):
            self._kw_with_vm(e).execute_ps("Get-Date")

    def test_raises_when_no_vm(self) -> None:
        kw = _make_kw(MagicMock(), MagicMock())
        with pytest.raises(RuntimeError, match="No VM available"):
            kw.execute_ps("cmd")


class TestExecuteSSH:
    def _kw_with_vm(self, executor: MagicMock) -> VmForgeKeywords:
        p = MagicMock()
        p.clone_and_snapshot.return_value = _handle(
            vm_id="10.0.0.5", template="10.0.0.5", platform="ssh_direct"
        )
        kw = _make_kw(p, executor)
        kw.clone_vm("10.0.0.5", "automation", "10.0.0.5")
        return kw

    def test_returns_stdout(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="Linux", exit_code=0)
        assert self._kw_with_vm(e).execute_ssh("uname -s") == "Linux"

    def test_does_not_raise_on_nonzero_exit_by_default(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="out", exit_code=1)
        assert self._kw_with_vm(e).execute_ssh("cmd") == "out"

    def test_check_rc_raises_on_nonzero_exit(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="", exit_code=127, stderr="not found")
        with pytest.raises(AssertionError, match="exit 127"):
            self._kw_with_vm(e).execute_ssh("bad-cmd", check_rc=True)

    def test_check_rc_passes_on_zero_exit(self) -> None:
        e = MagicMock()
        e.run.return_value = CommandResult(stdout="ok", exit_code=0)
        assert self._kw_with_vm(e).execute_ssh("cmd", check_rc=True) == "ok"

    def test_raises_when_no_vm(self) -> None:
        kw = _make_kw(MagicMock(), MagicMock())
        with pytest.raises(RuntimeError, match="No VM available"):
            kw.execute_ssh("cmd")


class TestCheckField:
    def _kw(self) -> VmForgeKeywords:
        return _make_kw(MagicMock(), MagicMock())

    def test_exact_integer(self) -> None:
        self._kw().check_field('{"result": {"code": 0}}', "result.code", "0")

    def test_exact_string(self) -> None:
        self._kw().check_field('{"status": "ok"}', "status", "ok")

    def test_nested_path(self) -> None:
        self._kw().check_field('{"a": {"b": {"c": 42}}}', "a.b.c", "42")

    def test_bool_true(self) -> None:
        self._kw().check_field('{"result": {"ok": true}}', "result.ok", "True")

    def test_bool_false(self) -> None:
        self._kw().check_field('{"result": {"ok": false}}', "result.ok", "False")

    def test_equals_field(self) -> None:
        data = '{"result": {"sha256": "abc", "expected": "abc"}}'
        self._kw().check_field(data, "result.sha256", "=result.expected")

    def test_equals_field_mismatch_raises(self) -> None:
        data = '{"result": {"sha256": "abc", "expected": "xyz"}}'
        with pytest.raises(AssertionError):
            self._kw().check_field(data, "result.sha256", "=result.expected")

    def test_value_mismatch_raises(self) -> None:
        with pytest.raises(AssertionError, match="result.code"):
            self._kw().check_field('{"result": {"code": 1}}', "result.code", "0")

    def test_missing_path_raises(self) -> None:
        with pytest.raises(AssertionError, match="does not exist"):
            self._kw().check_field('{"result": {}}', "result.missing", "0")

    def test_null_value_compares_as_none_string(self) -> None:
        self._kw().check_field('{"result": {"val": null}}', "result.val", "None")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(AssertionError, match="invalid JSON"):
            self._kw().check_field("not-json", "result.code", "0")

    def test_equals_field_missing_reference_raises(self) -> None:
        data = '{"result": {"sha256": "abc"}}'
        with pytest.raises(AssertionError, match="does not exist"):
            self._kw().check_field(data, "result.sha256", "=result.expected")

    def test_error_message_shows_path(self) -> None:
        with pytest.raises(AssertionError, match="result.code"):
            self._kw().check_field('{"result": {"code": 99}}', "result.code", "0")


class TestTraverse:
    def test_single_key(self) -> None:
        assert _traverse({"x": "hello"}, "x") == "hello"

    def test_nested_path(self) -> None:
        assert _traverse({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_key_returns_missing_sentinel(self) -> None:
        assert _traverse({"a": 1}, "b") is _MISSING

    def test_non_dict_intermediate_returns_missing_sentinel(self) -> None:
        assert _traverse({"a": 1}, "a.b") is _MISSING

    def test_none_value_is_returned_not_missing(self) -> None:
        assert _traverse({"a": None}, "a") is None

    def test_missing_nested_key_returns_missing_sentinel(self) -> None:
        assert _traverse({"a": {"b": 1}}, "a.c") is _MISSING
