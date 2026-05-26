"""Robot Framework keyword library for SSH VM tests.

Delegates to SSHVMManager — the existing adapter class — rather than
manipulating SSHClient directly.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from robot.api.deco import keyword, library
from robot.api import logger

from ssh.ssh_vm import SSHVMManager


@library(scope="SUITE", auto_keywords=False)
class SshVmLibrary:
    """Provides Robot Framework keywords for SSH-based VM management."""

    def __init__(self):
        self._manager: SSHVMManager | None = None
        self._last_result: dict = {}

    # ------------------------------------------------------------------ #
    #  Connection
    # ------------------------------------------------------------------ #

    @keyword("Connect To VM Via SSH")
    def connect_to_vm_via_ssh(self, host: str, username: str, password: str, port: int = 22):
        """Create an SSHVMManager, connect to *host*, and detect OS type.

        Fails if the SSH connection cannot be established.
        """
        self._manager = SSHVMManager(host, int(port))
        success = self._manager.login(username, password)
        if not success:
            raise AssertionError(
                f"SSH login to {host}:{port} as '{username}' failed"
            )
        logger.info(f"SSH connected to {host}:{port} (OS: {self._manager._os_type})")

    @keyword("Disconnect From VM SSH")
    def disconnect_from_vm_ssh(self):
        """Close the active SSH session."""
        if self._manager:
            self._manager.disconnect()
            logger.info("SSH disconnected")
            self._manager = None

    # ------------------------------------------------------------------ #
    #  Execute command
    # ------------------------------------------------------------------ #

    @keyword("Execute SSH Command")
    def execute_ssh_command(self, command: str, timeout: int = None) -> dict:
        """Execute *command* on the remote machine via SSH.

        Returns a dict with: exit_code, stdout, stderr, pid.
        Also stores the result for assertion keywords.
        """
        self._require_manager()
        logger.info(f"SSH execute: {command!r}")
        result = self._manager.execute_command(command)
        self._last_result = result
        logger.info(
            f"exit_code={result['exit_code']} | "
            f"stdout={result['stdout'][:200]!r} | "
            f"stderr={result['stderr'][:200]!r}"
        )
        return result

    @keyword("Get Last SSH Result")
    def get_last_ssh_result(self) -> dict:
        """Return the result dict from the most recent Execute SSH Command call."""
        return self._last_result

    # ------------------------------------------------------------------ #
    #  Assertions on execute results
    # ------------------------------------------------------------------ #

    @keyword("Exit Code Should Be")
    def exit_code_should_be(self, expected: int):
        """Assert the last command finished with *expected* exit code."""
        actual = self._last_result.get("exit_code")
        if actual != int(expected):
            raise AssertionError(
                f"Expected exit code {expected} but got {actual}. "
                f"stderr: {self._last_result.get('stderr', '')}"
            )

    @keyword("Exit Code Should Not Be Zero")
    def exit_code_should_not_be_zero(self):
        """Assert the last command finished with a non-zero exit code."""
        actual = self._last_result.get("exit_code")
        if actual == 0:
            raise AssertionError("Expected a non-zero exit code but got 0")

    @keyword("Stdout Should Contain")
    def stdout_should_contain(self, expected: str):
        """Assert captured stdout contains *expected*."""
        stdout = self._last_result.get("stdout", "")
        if expected not in stdout:
            raise AssertionError(
                f"Expected stdout to contain {expected!r}, but got:\n{stdout}"
            )

    @keyword("Stdout Should Not Be Empty")
    def stdout_should_not_be_empty(self):
        """Assert captured stdout is non-empty."""
        stdout = self._last_result.get("stdout", "")
        if not stdout.strip():
            raise AssertionError("Expected stdout to be non-empty, but it was empty")

    @keyword("Stderr Should Be Empty")
    def stderr_should_be_empty(self):
        """Assert captured stderr is empty."""
        stderr = self._last_result.get("stderr", "")
        if stderr.strip():
            raise AssertionError(f"Expected stderr to be empty, but got:\n{stderr}")

    @keyword("Result Should Have Key")
    def result_should_have_key(self, key: str):
        """Assert the last result dict contains *key*."""
        if key not in self._last_result:
            raise AssertionError(
                f"Result dict is missing key '{key}'. Keys present: {list(self._last_result)}"
            )

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _require_manager(self):
        if self._manager is None:
            raise RuntimeError(
                "No active SSH session. Call 'Connect To VM Via SSH' first."
            )
