import base64
from unittest.mock import MagicMock, patch

import pytest

from framework.plugins.base import CommandResult, ExecutorPlugin, PlatformPlugin, VMHandle
from framework.plugins.executors.powershell import PowershellExecutor
from framework.plugins.executors.ssh import SshExecutor
from framework.plugins.platforms.ssh_direct import SshDirectPlatform
from framework.plugins.platforms.vsphere import VspherePlatform
from framework.plugins.registry import get_executor, get_platform


class TestVMHandle:
    def test_required_fields(self) -> None:
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere", folder_name="CI")
        assert h.vm_id == "clone-01"
        assert h.template == "win10"
        assert h.platform == "vsphere"
        assert h.folder_name == "CI"

    def test_folder_name_defaults_to_empty(self) -> None:
        h = VMHandle(vm_id="host", template="host", platform="ssh_direct")
        assert h.folder_name == ""


class TestCommandResult:
    def test_required_fields(self) -> None:
        r = CommandResult(stdout="ok", exit_code=0)
        assert r.stdout == "ok"
        assert r.exit_code == 0

    def test_stderr_defaults_to_empty(self) -> None:
        r = CommandResult(stdout="", exit_code=0)
        assert r.stderr == ""


class TestAbstractInterfaces:
    def test_platform_plugin_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            PlatformPlugin()  # type: ignore[abstract]

    def test_executor_plugin_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            ExecutorPlugin()  # type: ignore[abstract]


class TestSshDirectPlatform:
    def test_clone_uses_template_as_vm_id(self) -> None:
        p = SshDirectPlatform()
        h = p.clone_and_snapshot("10.0.0.1", "snap", "ignored", "ignored")
        assert h.vm_id == "10.0.0.1"
        assert h.template == "10.0.0.1"
        assert h.platform == "ssh_direct"

    def test_revert_is_noop(self) -> None:
        p = SshDirectPlatform()
        h = VMHandle(vm_id="host", template="host", platform="ssh_direct")
        p.revert_snapshot(h, "snap")  # must not raise

    def test_teardown_is_noop(self) -> None:
        p = SshDirectPlatform()
        h = VMHandle(vm_id="host", template="host", platform="ssh_direct")
        p.teardown(h)  # must not raise


def _mock_mgr(vm_obj: MagicMock | None = None) -> MagicMock:
    mgr = MagicMock()
    mgr.__enter__.return_value = mgr
    mgr.__exit__.return_value = False
    if vm_obj is not None:
        mgr.get_vm.return_value = vm_obj
    return mgr


class TestVspherePlatform:
    def _platform(self) -> VspherePlatform:
        return VspherePlatform(host="vc", user="admin", password="pass")

    def test_clone_and_snapshot_returns_handle(self) -> None:
        p = self._platform()
        vm_obj = MagicMock()
        vm_obj.clone_with_config.return_value = True
        mgr = _mock_mgr(vm_obj)

        with patch.object(p, "_manager", return_value=mgr):
            handle = p.clone_and_snapshot("win10-tpl", "automation", "clone-01", "CI Pool")

        assert handle.vm_id == "clone-01"
        assert handle.template == "win10-tpl"
        assert handle.platform == "vsphere"
        assert handle.folder_name == "CI Pool"

    def test_clone_calls_get_vm_and_clone_with_config(self) -> None:
        p = self._platform()
        vm_obj = MagicMock()
        vm_obj.clone_with_config.return_value = True
        mgr = _mock_mgr(vm_obj)

        with patch.object(p, "_manager", return_value=mgr):
            p.clone_and_snapshot("win10-tpl", "automation", "clone-01", "CI Pool")

        mgr.get_vm.assert_called_once_with("win10-tpl")
        vm_obj.clone_with_config.assert_called_once()

    def test_revert_snapshot(self) -> None:
        p = self._platform()
        vm_obj = MagicMock()
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere", folder_name="CI")

        with patch.object(p, "_manager", return_value=mgr):
            p.revert_snapshot(h, "automation")

        mgr.get_vm.assert_called_once_with("clone-01", folder_name="CI")
        vm_obj.revert_to_snapshot.assert_called_once_with("automation")

    def test_revert_passes_none_for_empty_folder(self) -> None:
        p = self._platform()
        vm_obj = MagicMock()
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere")

        with patch.object(p, "_manager", return_value=mgr):
            p.revert_snapshot(h, "snap")

        mgr.get_vm.assert_called_once_with("clone-01", folder_name=None)

    def test_teardown_deletes_vm(self) -> None:
        p = self._platform()
        mgr = _mock_mgr()
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere", folder_name="CI")

        with patch.object(p, "_manager", return_value=mgr):
            p.teardown(h)

        mgr.delete_vm.assert_called_once_with("CI", "clone-01")

    def test_teardown_passes_none_for_empty_folder(self) -> None:
        p = self._platform()
        mgr = _mock_mgr()
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere")

        with patch.object(p, "_manager", return_value=mgr):
            p.teardown(h)

        mgr.delete_vm.assert_called_once_with(None, "clone-01")


class TestPowershellExecutor:
    def _executor(self) -> PowershellExecutor:
        return PowershellExecutor(
            guest_user="Admin",
            guest_password="pass",
            vcenter_host="vc",
            vcenter_user="admin",
            vcenter_password="vcpass",
        )

    def test_run_returns_command_result(self) -> None:
        exec_ = self._executor()
        vm_obj = MagicMock()
        vm_obj.execute_command.return_value = {"stdout": "hello", "exit_code": 0, "stderr": ""}
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere", folder_name="CI")

        with patch("framework.plugins.executors.powershell.VSphereManager", return_value=mgr):
            result = exec_.run(h, "Write-Output hello")

        assert result.stdout == "hello"
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_run_calls_login_and_execute(self) -> None:
        exec_ = self._executor()
        vm_obj = MagicMock()
        vm_obj.execute_command.return_value = {"stdout": "", "exit_code": 0}
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="clone-01", template="win10", platform="vsphere", folder_name="CI")

        with patch("framework.plugins.executors.powershell.VSphereManager", return_value=mgr):
            exec_.run(h, "Get-Date")

        vm_obj.login.assert_called_once_with("Admin", "pass")
        cmd_arg = vm_obj.execute_command.call_args[0][0]
        assert "powershell" in cmd_arg.lower()
        assert "-EncodedCommand" in cmd_arg
        # Verify original command survives the base64 roundtrip
        encoded_part = cmd_arg.split("-EncodedCommand ")[1]
        decoded = base64.b64decode(encoded_part).decode("utf-16-le")
        assert "Get-Date" in decoded

    def test_run_passes_folder_name(self) -> None:
        exec_ = self._executor()
        vm_obj = MagicMock()
        vm_obj.execute_command.return_value = {"stdout": "", "exit_code": 0}
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="vm1", template="t", platform="vsphere", folder_name="Folder")

        with patch("framework.plugins.executors.powershell.VSphereManager", return_value=mgr):
            exec_.run(h, "ls")

        mgr.get_vm.assert_called_once_with("vm1", folder_name="Folder")

    def test_run_raises_if_vsphere_unavailable(self) -> None:
        exec_ = self._executor()
        h = VMHandle(vm_id="x", template="t", platform="vsphere")

        # M5: combined with statement (SIM117)
        with patch("framework.plugins.executors.powershell.VSphereManager", None),              pytest.raises(RuntimeError, match="vmkit vsphere not available"):
            exec_.run(h, "cmd")

    def test_run_propagates_execute_exception(self) -> None:
        exec_ = self._executor()
        vm_obj = MagicMock()
        vm_obj.execute_command.side_effect = RuntimeError("guest exec failed")
        mgr = _mock_mgr(vm_obj)
        h = VMHandle(vm_id="vm1", template="t", platform="vsphere", folder_name="CI")

        with patch("framework.plugins.executors.powershell.VSphereManager", return_value=mgr):
            with pytest.raises(RuntimeError, match="guest exec failed"):
                exec_.run(h, "cmd")


class TestSshExecutor:
    def test_run_returns_command_result(self) -> None:
        exec_ = SshExecutor(ssh_user="root", ssh_password="pass")
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = False
        mock_ssh.execute_command.return_value = {"stdout": "Linux", "exit_code": 0}
        h = VMHandle(vm_id="10.0.0.5", template="10.0.0.5", platform="ssh_direct")

        with patch("framework.plugins.executors.ssh.SSHVMManager", return_value=mock_ssh):
            result = exec_.run(h, "uname -s")

        assert result.stdout == "Linux"
        assert result.exit_code == 0

    def test_run_calls_login_and_execute(self) -> None:
        exec_ = SshExecutor(ssh_user="root", ssh_password="pass")
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = False
        mock_ssh.execute_command.return_value = {"stdout": "", "exit_code": 0}
        h = VMHandle(vm_id="10.0.0.5", template="10.0.0.5", platform="ssh_direct")

        with patch("framework.plugins.executors.ssh.SSHVMManager", return_value=mock_ssh):
            exec_.run(h, "uname -s")

        mock_ssh.login.assert_called_once_with("root", "pass")
        mock_ssh.execute_command.assert_called_once_with("uname -s")

    def test_run_uses_vm_id_as_host(self) -> None:
        exec_ = SshExecutor(ssh_user="u", ssh_password="p", port=2222)
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = False
        mock_ssh.execute_command.return_value = {"stdout": "", "exit_code": 0}
        h = VMHandle(vm_id="192.168.1.50", template="192.168.1.50", platform="ssh_direct")

        with patch("framework.plugins.executors.ssh.SSHVMManager", return_value=mock_ssh) as mock_cls:
            exec_.run(h, "ls")

        mock_cls.assert_called_once_with("192.168.1.50", port=2222)

    def test_run_raises_if_ssh_unavailable(self) -> None:
        exec_ = SshExecutor(ssh_user="u", ssh_password="p")
        h = VMHandle(vm_id="x", template="t", platform="ssh_direct")

        # M5: combined with statement (SIM117)
        with patch("framework.plugins.executors.ssh.SSHVMManager", None),              pytest.raises(RuntimeError, match="vmkit SSH not available"):
            exec_.run(h, "cmd")

    def test_run_propagates_execute_exception(self) -> None:
        exec_ = SshExecutor(ssh_user="root", ssh_password="pass")
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = False
        mock_ssh.execute_command.side_effect = RuntimeError("ssh channel error")
        h = VMHandle(vm_id="10.0.0.5", template="10.0.0.5", platform="ssh_direct")

        with patch("framework.plugins.executors.ssh.SSHVMManager", return_value=mock_ssh):
            with pytest.raises(RuntimeError, match="ssh channel error"):
                exec_.run(h, "cmd")


class TestRegistry:
    def test_get_platform_vsphere(self) -> None:
        p = get_platform("vsphere", host="vc", user="u", password="p")
        assert isinstance(p, VspherePlatform)

    def test_get_platform_ssh_direct(self) -> None:
        p = get_platform("ssh_direct")
        assert isinstance(p, SshDirectPlatform)

    def test_get_platform_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown"):
            get_platform("unknown")

    def test_get_executor_powershell(self) -> None:
        e = get_executor("powershell", guest_user="u", guest_password="p")
        assert isinstance(e, PowershellExecutor)

    def test_get_executor_ssh(self) -> None:
        e = get_executor("ssh", ssh_user="u", ssh_password="p")
        assert isinstance(e, SshExecutor)

    def test_get_executor_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown"):
            get_executor("unknown")
