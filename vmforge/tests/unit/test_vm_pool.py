from pathlib import Path
from unittest.mock import patch

import filelock
import pytest

from framework.lifecycle.vm_pool import VmPool


class TestLockPath:
    def _path(self, template: str, tmp_path: Path) -> Path:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            return VmPool._lock_path(template)

    def test_ends_with_dot_lock(self, tmp_path: Path) -> None:
        assert self._path("win10", tmp_path).suffix == ".lock"

    def test_sanitizes_forward_slashes(self, tmp_path: Path) -> None:
        assert "/" not in self._path("linux/ubuntu-22", tmp_path).name

    def test_sanitizes_backslashes(self, tmp_path: Path) -> None:
        assert "\\" not in self._path("windows\\server\\2022", tmp_path).name

    def test_sanitizes_colons(self, tmp_path: Path) -> None:
        assert ":" not in self._path("win10:snapshot", tmp_path).name

    def test_sanitizes_spaces(self, tmp_path: Path) -> None:
        assert " " not in self._path("base snapshot v2", tmp_path).name

    def test_sanitizes_windows_illegal_chars(self, tmp_path: Path) -> None:
        name = self._path("win<10>x64|2022?*", tmp_path).name
        for ch in "<>|?*":
            assert ch not in name

    def test_different_templates_give_different_paths(self, tmp_path: Path) -> None:
        assert self._path("win10", tmp_path) != self._path("win11", tmp_path)

    def test_same_template_gives_same_path(self, tmp_path: Path) -> None:
        assert self._path("win10", tmp_path) == self._path("win10", tmp_path)


class TestSlotContextManager:
    def test_enters_and_exits_without_error(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path), VmPool.slot("win10"):
            pass

    def test_can_reacquire_after_release(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            with VmPool.slot("win10"):
                pass
            with VmPool.slot("win10"):
                pass

    def test_lock_dir_created_if_missing(self, tmp_path: Path) -> None:
        absent = tmp_path / "new_locks"
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", absent), VmPool.slot("win10"):
            pass
        assert absent.is_dir()

    def test_different_templates_do_not_block_each_other(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            with VmPool.slot("win10"), VmPool.slot("win11"):
                pass

    def test_timeout_raises_when_held(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            outer = VmPool.acquire("win10")
            try:
                with pytest.raises(filelock.Timeout):
                    with VmPool.slot("win10", timeout=0):
                        pass
            finally:
                VmPool.release(outer)

    def test_lock_released_on_exception(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            with pytest.raises(RuntimeError):
                with VmPool.slot("win10"):
                    raise RuntimeError("boom")
            # lock must be free — a zero-timeout acquire must succeed
            with VmPool.slot("win10", timeout=0):
                pass


class TestAcquireReleaseApi:
    def test_acquire_and_release(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            lock = VmPool.acquire("win10")
            VmPool.release(lock)

    def test_reacquire_after_release(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            lock = VmPool.acquire("win10")
            VmPool.release(lock)
            lock2 = VmPool.acquire("win10")
            VmPool.release(lock2)

    def test_timeout_raises_on_already_locked(self, tmp_path: Path) -> None:
        with patch("framework.lifecycle.vm_pool._LOCK_DIR", tmp_path):
            lock = VmPool.acquire("win10")
            try:
                with pytest.raises(filelock.Timeout):
                    VmPool.acquire("win10", timeout=0)
            finally:
                VmPool.release(lock)
