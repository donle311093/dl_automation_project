from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any

from robot.api.deco import keyword

from ...plugins.base import VMHandle
from ...plugins.registry import get_executor, get_platform

__all__ = ["VmForgeKeywords"]

_CFG_SEARCH_PATHS = [
    Path(__file__).parents[4] / "platform.cfg",
    Path.cwd() / "platform.cfg",
]

# Sentinel distinguishing "key missing from JSON" vs "key exists with value None"
_MISSING: object = object()


def _load_cfg(cfg_path: str | None) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if cfg_path is None:
        for p in _CFG_SEARCH_PATHS:
            if p.exists():
                cfg.read(p)
                break
    elif cfg_path:
        cfg.read(cfg_path)
    return cfg


def _env_or_cfg(
    cfg: configparser.ConfigParser,
    section: str,
    key: str,
    env_var: str,
    default: str = "",
) -> str:
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val
    return cfg.get(section, key, fallback=default)


def _require_nonempty(value: str, field: str, env_var: str) -> str:
    if not value:
        raise ValueError(
            f"Missing required credential: {field!r}. "
            f"Set env var {env_var!r} or add it to the relevant section of platform.cfg."
        )
    return value


def _parse_port(raw: str, env_var: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"Invalid port value {raw!r} (from {env_var!r} or platform.cfg): must be an integer"
        ) from None


def _platform_kwargs(platform: str, cfg: configparser.ConfigParser) -> dict[str, Any]:
    if platform == "vsphere":
        return {
            "host": _require_nonempty(
                _env_or_cfg(cfg, "vsphere", "host", "VMFORGE_VCENTER_HOST"),
                "vsphere.host", "VMFORGE_VCENTER_HOST",
            ),
            "user": _require_nonempty(
                _env_or_cfg(cfg, "vsphere", "user", "VMFORGE_VCENTER_USER"),
                "vsphere.user", "VMFORGE_VCENTER_USER",
            ),
            "password": _require_nonempty(
                _env_or_cfg(cfg, "vsphere", "password", "VMFORGE_VCENTER_PASSWORD"),
                "vsphere.password", "VMFORGE_VCENTER_PASSWORD",
            ),
            "port": _parse_port(
                _env_or_cfg(cfg, "vsphere", "port", "VMFORGE_VCENTER_PORT", "443"),
                "VMFORGE_VCENTER_PORT",
            ),
        }
    return {}


def _executor_kwargs(
    executor: str, platform: str, cfg: configparser.ConfigParser
) -> dict[str, Any]:
    if executor == "powershell":
        kwargs: dict[str, Any] = {
            "guest_user": _require_nonempty(
                _env_or_cfg(cfg, "powershell", "guest_user", "VMFORGE_GUEST_USER"),
                "powershell.guest_user", "VMFORGE_GUEST_USER",
            ),
            "guest_password": _require_nonempty(
                _env_or_cfg(cfg, "powershell", "guest_password", "VMFORGE_GUEST_PASSWORD"),
                "powershell.guest_password", "VMFORGE_GUEST_PASSWORD",
            ),
        }
        if platform == "vsphere":
            kwargs.update({
                "vcenter_host": _require_nonempty(
                    _env_or_cfg(cfg, "vsphere", "host", "VMFORGE_VCENTER_HOST"),
                    "vsphere.host", "VMFORGE_VCENTER_HOST",
                ),
                "vcenter_user": _require_nonempty(
                    _env_or_cfg(cfg, "vsphere", "user", "VMFORGE_VCENTER_USER"),
                    "vsphere.user", "VMFORGE_VCENTER_USER",
                ),
                "vcenter_password": _require_nonempty(
                    _env_or_cfg(cfg, "vsphere", "password", "VMFORGE_VCENTER_PASSWORD"),
                    "vsphere.password", "VMFORGE_VCENTER_PASSWORD",
                ),
                "vcenter_port": _parse_port(
                    _env_or_cfg(cfg, "vsphere", "port", "VMFORGE_VCENTER_PORT", "443"),
                    "VMFORGE_VCENTER_PORT",
                ),
            })
        return kwargs
    if executor == "ssh":
        return {
            "ssh_user": _require_nonempty(
                _env_or_cfg(cfg, "ssh", "user", "VMFORGE_SSH_USER"),
                "ssh.user", "VMFORGE_SSH_USER",
            ),
            "ssh_password": _require_nonempty(
                _env_or_cfg(cfg, "ssh", "password", "VMFORGE_SSH_PASSWORD"),
                "ssh.password", "VMFORGE_SSH_PASSWORD",
            ),
            "port": _parse_port(
                _env_or_cfg(cfg, "ssh", "port", "VMFORGE_SSH_PORT", "22"),
                "VMFORGE_SSH_PORT",
            ),
        }
    return {}


def _traverse(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict):
            return _MISSING
        if key not in data:
            return _MISSING
        data = data[key]
    return data


class VmForgeKeywords:
    """Unified Robot Framework keyword library for VM-based test automation."""

    # SUITE scope: one library instance per suite file; each pabot worker runs one suite
    # in its own OS process so _vm is process-isolated. Do NOT change to GLOBAL —
    # parallel suites would share a single _vm reference and corrupt each other.
    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(
        self,
        platform: str,
        executor: str,
        clone_folder: str = "",
        cfg_path: str | None = None,
    ) -> None:
        cfg = _load_cfg(cfg_path)
        self._platform = get_platform(platform, **_platform_kwargs(platform, cfg))
        self._executor = get_executor(executor, **_executor_kwargs(executor, platform, cfg))
        self._clone_folder = clone_folder
        self._vm: VMHandle | None = None

    # ── VM lifecycle ──────────────────────────────────────────────────────────

    @keyword("Clone VM")
    def clone_vm(self, template: str, snapshot: str, clone_name: str = "") -> None:
        """Suite Setup: clone template at snapshot; store handle for this suite."""
        if self._vm is not None:
            raise RuntimeError(
                f"Clone VM called while a VM is already active ({self._vm.vm_id!r})"
                " — call Teardown VM first"
            )
        name = clone_name or f"vmforge-{template}"
        self._vm = self._platform.clone_and_snapshot(
            template, snapshot, name, self._clone_folder
        )

    @keyword("Revert Snapshot")
    def revert_snapshot(self, snapshot: str) -> None:
        """Test Setup: restore clone to clean state before each test case."""
        if self._vm is None:
            raise RuntimeError("No VM cloned — call Clone VM first")
        self._platform.revert_snapshot(self._vm, snapshot)

    @keyword("Teardown VM")
    def teardown_vm(self) -> None:
        """Suite Teardown: delete clone after all tests finish."""
        if self._vm is not None:
            self._platform.teardown(self._vm)
            self._vm = None

    # ── Executors ─────────────────────────────────────────────────────────────

    @keyword("Execute PS")
    def execute_ps(self, command: str) -> str:
        """Run a PowerShell command; raise AssertionError on non-zero exit."""
        if self._vm is None:
            raise RuntimeError("No VM available — call Clone VM first")
        result = self._executor.run(self._vm, command)
        if result.exit_code != 0:
            raise AssertionError(
                f"PowerShell command failed (exit {result.exit_code}): {command}\n{result.stderr}"
            )
        return result.stdout

    @keyword("Execute SSH")
    def execute_ssh(self, command: str, check_rc: bool = False) -> str:
        """Run a shell command over SSH; return stdout.

        By default exit code is ignored. Pass check_rc=True to raise
        AssertionError on non-zero exit.
        """
        if self._vm is None:
            raise RuntimeError("No VM available — call Clone VM first")
        result = self._executor.run(self._vm, command)
        if check_rc and result.exit_code != 0:
            raise AssertionError(
                f"SSH command failed (exit {result.exit_code}): {command}\n{result.stderr}"
            )
        return result.stdout

    # ── Assertions ────────────────────────────────────────────────────────────

    @keyword("Check Field")
    def check_field(self, json_output: str, path: str, expected: str) -> None:
        """Assert a dot-notation field in JSON output equals expected.

        If expected starts with =, treat the rest as a field path (equals_field).
        All comparisons are done as str(actual) == str(expected).
        """
        try:
            data: Any = json.loads(json_output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Check Field: invalid JSON (path={path!r}): {exc}\n"
                f"Input was: {json_output[:200]!r}"
            ) from exc

        actual = _traverse(data, path)
        if actual is _MISSING:
            raise AssertionError(
                f"Check Field: path {path!r} does not exist in JSON output"
            )

        if expected.startswith("="):
            ref_path = expected[1:]
            expected_val: Any = _traverse(data, ref_path)
            if expected_val is _MISSING:
                raise AssertionError(
                    f"Check Field: equals_field reference path {ref_path!r} does not exist in JSON output"
                )
        else:
            expected_val = expected

        assert str(actual) == str(expected_val), (
            f"{path}: got {actual!r}, expected {expected_val!r}"
        )
