"""Example: Using VMManager directly for login and snapshot tests."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vsphere.vcenter_client import VCenterClient
from vsphere.vsphere_vm import VSphereVMManager as VMManager


# Set which test to run: "login" or "snapshot"
TEST = "snapshot"

with VCenterClient() as client:
    vm_manager = VMManager(client, 'Windows 10 64bit', folder_name='Personal VM')

    if not vm_manager.vm:
        print("VM not found.")
        exit(1)

    print(f"Power status: {vm_manager.get_power_status()}")

    print("Get vm info:")
    vm_info = vm_manager.get_vm_info()
    for key, value in vm_info.items():
        print(f"  {key}: {value}")

    if TEST == "login":
        print("\n--- Test: Login ---")
        vm_manager.set_annotation("Testing login via VMManager.")
        print(f"Annotation: {vm_manager.get_annotation()}")
        print(f"Guest tools status: {vm_manager.get_guest_tools_status()}")

        print("Attempting to log in to the VM...")
        if vm_manager.login('admin', 'admin'):
            print("Logged in successfully")
        else:
            print("Failed to log in")

        print("Executing command inside the VM...")
        result = vm_manager.execute_command('Get-Process')
        print(f"Exit Code: {result['exit_code']}")
        print(f"STDOUT:\n{result['stdout']}")
        print(f"STDERR:\n{result['stderr']}")

        vm_manager.set_annotation("")

    elif TEST == "snapshot":
        print("\n--- Test: Snapshot ---")

        print("Creating snapshot...")
        if vm_manager.create_snapshot("Test Snapshot", "Snapshot created by VMManager", memory=True, quiesce=True):
            print("Snapshot created successfully.")

        print("Reverting to current snapshot...")
        if vm_manager.revert_to_current_snapshot():
            print("Reverted to snapshot successfully.")

        print("Revert to specific snapshot...")
        if vm_manager.revert_to_snapshot("Test Snapshot"):
            print("Reverted to specific snapshot successfully.")

        print("List snapshots:")
        snapshots = vm_manager.get_snapshots()
        for snap in snapshots:
            print(f"  - {snap.name}")

        print("Deleting snapshot...")
        if vm_manager.delete_snapshot("Test Snapshot"):
            print("Snapshot deleted successfully.")

        print("List snapshots:")
        snapshots = vm_manager.get_snapshots()
        for snap in snapshots:
            print(f"  - {snap.name}")
