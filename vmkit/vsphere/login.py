import sys
import os

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from pyVmomi import vim

OSTYPE = {
    'WINDOWS': 'windows',
    'LINUX': 'linux',
    'MACOS': 'macos',
}

SHELL = {
    'POWERSHELL': 'powershell',
    'SH': 'sh',
}


def detect_ostype(vm):
    """Detect the OS type of a VM from its guest_id."""
    from vsphere.vm_info import get_vm_info
    info = get_vm_info(vm)
    guest_id = (info.get("guest_id") or "").lower()
    if "win" in guest_id:
        return OSTYPE['WINDOWS']
    elif "darwin" in guest_id or "mac" in guest_id:
        return OSTYPE['MACOS']
    return OSTYPE['LINUX']


def shell_autoconfig(ostype):
    """Return the appropriate shell for the given OS type."""
    return SHELL['POWERSHELL'] if ostype == OSTYPE['WINDOWS'] else SHELL['SH']


def validate_credentials(content, vm, guest_user, guest_pass, interactive_session=False):
    """Validate guest credentials via VMware Tools."""
    auth = vim.vm.guest.NamePasswordAuthentication(
        username=guest_user,
        password=guest_pass,
        interactiveSession=interactive_session,
    )
    content.guestOperationsManager.authManager.ValidateCredentialsInGuest(
        vm=vm, auth=auth
    )


def login_to_vm(client, vm, guest_user, guest_pass, ostype=None,
                interactive_session=False, timeout=1200, sleep_time=1):
    """Power on a VM, wait for VMware Tools, and validate guest credentials.

    Args:
        client: A connected VCenterClient instance.
        vm: A vim.VirtualMachine managed object.
        guest_user: Guest OS username.
        guest_pass: Guest OS password.
        ostype: One of OSTYPE values ('windows', 'linux', 'macos').
                If None, auto-detected from the VM's guest ID.
        interactive_session: Whether to use an interactive session for auth.
        timeout: Max seconds to wait for a successful login.
        sleep_time: Seconds between retries.

    Returns:
        True if login succeeded, False otherwise.
    """
    if vm is None:
        return False

    if ostype is None:
        ostype = detect_ostype(vm)

    content = client.si.RetrieveContent()
    remaining = timeout

    while remaining > 0:
        try:
            # Power on if needed
            if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
                from pyVim.task import WaitForTask
                task = vm.PowerOnVM_Task()
                WaitForTask(task)

            # Wait for VMware Tools to be running
            tools_wait = 600
            while tools_wait > 0 and (
                vm.guest.toolsStatus == "toolsNotRunning"
                or vm.guest.guestState is None
                or vm.guest.guestState != "running"
            ):
                time.sleep(sleep_time)
                tools_wait -= sleep_time

            if tools_wait <= 0:
                print(f"VMware Tools did not start on \"{vm.name}\"")
                return False

            validate_credentials(content, vm, guest_user, guest_pass, interactive_session)
            return True
        except Exception as e:
            print(f"Login attempt failed: {e}")
            remaining -= sleep_time
            time.sleep(sleep_time)

    return False


if __name__ == "__main__":
    from vsphere.vcenter_client import VCenterClient
    from vsphere.find_vm import find_vm_inside_folder

    with VCenterClient() as client:
        vm = find_vm_inside_folder(client, 'VCR Test', 'windows-10-64-autologin_autotest_01')
        if vm:
            print(f"VM found: {vm.name}")
            success = login_to_vm(client, vm, 'admin', 'admin')
            if success:
                print("Logged in successfully")
            else:
                print("Failed to log in")
        else:
            print("VM not found.")
