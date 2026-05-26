"""Robot Framework keyword library for vSphere execute_command tests.

Delegates to VSphereManager and VSphereVMManager — the existing facade
and strategy classes — rather than calling low-level vsphere.* functions.
"""

import sys
import os

# Allow imports from the pyvmomi_example package root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from robot.api.deco import keyword, library
from robot.api import logger

from vsphere.vsphere_manager import VSphereManager
from vsphere.vsphere_vm import VSphereVMManager


@library(scope="SUITE", auto_keywords=False)
class VsphereExecuteLibrary:
    """Provides Robot Framework keywords for vSphere guest command execution."""

    def __init__(self):
        self._vsphere: VSphereManager | None = None
        self._vm_manager: VSphereVMManager | None = None
        self._last_result: dict = {}

    # ------------------------------------------------------------------ #
    #  Connection
    # ------------------------------------------------------------------ #

    @keyword("Connect To VCenter")
    def connect_to_vcenter(self, config_path: str = None):
        """Connect to vCenter using the given config file path (or default .config)."""
        self._vsphere = VSphereManager(config_path)
        self._vsphere.connect()
        logger.info(f"Connected to vCenter: {self._vsphere._client.host}")

    @keyword("Disconnect From VCenter")
    def disconnect_from_vcenter(self):
        """Disconnect from vCenter if a session is active."""
        if self._vsphere:
            self._vsphere.disconnect()
            logger.info("Disconnected from vCenter")
            self._vsphere = None

    # ------------------------------------------------------------------ #
    #  VM lookup
    # ------------------------------------------------------------------ #

    @keyword("Find VM In Folder")
    def find_vm_in_folder(self, folder_name: str, vm_name: str):
        """Get a VSphereVMManager for *vm_name* inside *folder_name*.

        Fails if the VM is not found.
        """
        self._require_connection()
        vm_manager = self._vsphere.get_vm(vm_name, folder_name=folder_name)
        if vm_manager.vm is None:
            raise AssertionError(
                f"VM '{vm_name}' not found inside folder '{folder_name}'"
            )
        self._vm_manager = vm_manager
        logger.info(f"Found VM: {vm_manager.vm.name}")
        return vm_manager

    @keyword("Find VM By Name")
    def find_vm_by_name(self, vm_name: str):
        """Get a VSphereVMManager for *vm_name* across all folders.

        Fails if no VM with the given name is found.
        """
        self._require_connection()
        vm_manager = self._vsphere.get_vm(vm_name)
        if vm_manager.vm is None:
            raise AssertionError(f"VM '{vm_name}' not found in vCenter inventory")
        self._vm_manager = vm_manager
        logger.info(f"Found VM: {vm_manager.vm.name}")
        return vm_manager

    @keyword("VM Should Not Exist In Folder")
    def vm_should_not_exist_in_folder(self, folder_name: str, vm_name: str):
        """Verify that a VM does *not* exist inside a folder."""
        self._require_connection()
        vm_manager = self._vsphere.get_vm(vm_name, folder_name=folder_name)
        if vm_manager.vm is not None:
            raise AssertionError(
                f"VM '{vm_name}' was expected to be absent but was found in folder '{folder_name}'"
            )
        logger.info(f"Confirmed VM '{vm_name}' does not exist in folder '{folder_name}'")

    # ------------------------------------------------------------------ #
    #  Login
    # ------------------------------------------------------------------ #

    @keyword("Login To VM")
    def login_to_vm_keyword(
        self,
        guest_user: str,
        guest_pass: str,
        timeout: int = 1200,
    ):
        """Power on the current VM, wait for VMware Tools, and validate credentials.

        Fails if login does not succeed within *timeout* seconds.
        """
        self._require_vm()
        success = self._vm_manager.login(guest_user, guest_pass)
        if not success:
            raise AssertionError(
                f"Login to VM '{self._vm_manager.vm.name}' failed "
                f"(user={guest_user}, timeout={timeout}s)"
            )
        logger.info(f"Logged in to VM '{self._vm_manager.vm.name}' as '{guest_user}'")

    # ------------------------------------------------------------------ #
    #  Execute command
    # ------------------------------------------------------------------ #

    @keyword("Execute Command On VM")
    def execute_command_on_vm(
        self,
        command: str,
        capture_output: bool = True,
    ) -> dict:
        """Execute *command* inside the current VM via VMware Tools.

        Returns a dict with: pid, exit_code, stdout, stderr.
        Login To VM must be called first so that credentials are stored.
        """
        self._require_vm()
        logger.info(
            f"Executing on '{self._vm_manager.vm.name}': {command!r} (capture={capture_output})"
        )
        result = self._vm_manager.execute_command(command, capture_output=capture_output)
        self._last_result = result
        logger.info(
            f"Exit code: {result['exit_code']} | "
            f"stdout: {result['stdout'][:200]!r} | "
            f"stderr: {result['stderr'][:200]!r}"
        )
        return result

    @keyword("Get Last Execute Result")
    def get_last_execute_result(self) -> dict:
        """Return the result dict from the most recent Execute Command On VM call."""
        return self._last_result

    # ------------------------------------------------------------------ #
    #  Clone / Delete
    # ------------------------------------------------------------------ #

    @keyword("Clone VM To Folder")
    def clone_vm_to_folder(
        self,
        target_folder: str,
        new_vm_name: str,
        snapshot_name: str = None,
        power_on: bool = False,
    ) -> bool:
        """Clone the current VM to *target_folder* with name *new_vm_name*.

        If *snapshot_name* is provided, a linked clone is created from that
        snapshot; otherwise a full clone of the current state is performed.
        After a successful clone, the active VM context switches to the
        newly created VM so subsequent keywords operate on the clone.
        """
        self._require_vm()
        logger.info(
            f"Cloning '{self._vm_manager.vm.name}' -> '{new_vm_name}' "
            f"in folder '{target_folder}'"
            + (f" from snapshot '{snapshot_name}'" if snapshot_name else "")
        )
        success = self._vm_manager.clone(
            target_folder_name=target_folder,
            new_vm_name=new_vm_name,
            snapshot_name=snapshot_name,
            power_on=power_on,
        )
        if not success:
            raise AssertionError(
                f"Failed to clone VM '{self._vm_manager.vm.name}' "
                f"to folder '{target_folder}' as '{new_vm_name}'"
            )
        cloned_manager = self._vsphere.get_vm(new_vm_name, folder_name=target_folder)
        if cloned_manager.vm is None:
            raise AssertionError(
                f"Clone succeeded but cloned VM '{new_vm_name}' not found "
                f"in folder '{target_folder}'"
            )
        self._vm_manager = cloned_manager
        logger.info(f"Switched VM context to cloned VM: '{new_vm_name}'")
        return True

    @keyword("Delete VM In Folder")
    def delete_vm_in_folder(self, folder_name: str, vm_name: str) -> bool:
        """Power off then delete *vm_name* inside *folder_name*.

        Power-off is handled inside delete_vm(), which uses a fresh container
        view lookup — avoiding stale managed object references.  The active VM
        context is cleared when the deleted VM matches the current selection.
        """
        self._require_connection()

        # Capture whether this is the current VM context BEFORE any API calls
        # that could raise ManagedObjectNotFound on a stale reference.
        try:
            is_current_vm = (
                self._vm_manager is not None
                and self._vm_manager.vm is not None
                and self._vm_manager.vm.name == vm_name
            )
        except Exception:
            # Managed object is already gone; treat as current VM to clear context.
            is_current_vm = self._vm_manager is not None

        logger.info(f"Deleting VM '{vm_name}' from folder '{folder_name}'")
        success = self._vsphere.delete_vm(folder_name, vm_name)
        if not success:
            raise AssertionError(
                f"Failed to delete VM '{vm_name}' from folder '{folder_name}'"
            )
        if is_current_vm:
            self._vm_manager = None
        logger.info(f"VM '{vm_name}' deleted from folder '{folder_name}'")
        return True

    # ------------------------------------------------------------------ #
    #  Assertions on execute results
    # ------------------------------------------------------------------ #

    @keyword("Exit Code Should Be")
    def exit_code_should_be(self, expected_exit_code: int):
        """Assert that the last command finished with *expected_exit_code*."""
        actual = self._last_result.get("exit_code")
        if actual != int(expected_exit_code):
            raise AssertionError(
                f"Expected exit code {expected_exit_code} but got {actual}. "
                f"stderr: {self._last_result.get('stderr', '')}"
            )

    @keyword("Exit Code Should Not Be Zero")
    def exit_code_should_not_be_zero(self):
        """Assert that the last command finished with a non-zero exit code."""
        actual = self._last_result.get("exit_code")
        if actual == 0:
            raise AssertionError("Expected a non-zero exit code but got 0")

    @keyword("Stdout Should Contain")
    def stdout_should_contain(self, expected: str):
        """Assert that the captured stdout contains *expected*."""
        stdout = self._last_result.get("stdout", "")
        if expected not in stdout:
            raise AssertionError(
                f"Expected stdout to contain {expected!r}, but got:\n{stdout}"
            )

    @keyword("Stdout Should Not Be Empty")
    def stdout_should_not_be_empty(self):
        """Assert that captured stdout is non-empty."""
        stdout = self._last_result.get("stdout", "")
        if not stdout.strip():
            raise AssertionError("Expected stdout to be non-empty, but it was empty")

    @keyword("Stderr Should Be Empty")
    def stderr_should_be_empty(self):
        """Assert that captured stderr is empty."""
        stderr = self._last_result.get("stderr", "")
        if stderr.strip():
            raise AssertionError(
                f"Expected stderr to be empty, but got:\n{stderr}"
            )

    @keyword("Result Should Have Key")
    def result_should_have_key(self, key: str):
        """Assert that the last result dict contains *key*."""
        if key not in self._last_result:
            raise AssertionError(
                f"Result dict is missing key '{key}'. Keys present: {list(self._last_result)}"
            )

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _require_connection(self):
        if self._vsphere is None or self._vsphere._client.si is None:
            raise RuntimeError(
                "No active vCenter connection. Call 'Connect To VCenter' first."
            )

    def _require_vm(self):
        self._require_connection()
        if self._vm_manager is None:
            raise RuntimeError(
                "No VM selected. Call 'Find VM In Folder' or 'Find VM By Name' first."
            )
