"""Example: Using VSphereManager to manage VMs."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vsphere.vsphere_manager import VSphereManager


with VSphereManager() as vsphere:
    # --- Example 1: Find all VMs in a folder, then pick one to manage ---
    print("=== Find VMs in folder ===")
    vms = vsphere.find_vms_in_folder('Personal VM')
    if vms:
        for vm in vms:
            print(f"  Found: {vm.name}")

        # Pick a VM by matching name
        target_name = 'Windows 10 64bit'
        match = next((vm for vm in vms if vm.name == target_name), None)
        if match:
            print(f"\nManaging VM: {match.name}")
            vm_manager = vsphere.get_vm(match.name, folder_name='Personal VM')
            print(f"  Power: {vm_manager.get_power_status()}")
            info = vm_manager.get_vm_info()
            for key, value in info.items():
                print(f"  {key}: {value}")

    # --- Example 2: Get a VMManager directly by name ---
    print("\n=== Direct VMManager ===")
    vm_manager = vsphere.get_vm('Windows 10 64bit', folder_name='Personal VM')
    if vm_manager.vm:
        print(f"VM: {vm_manager.vm.name}")
        print(f"Power: {vm_manager.get_power_status()}")
        print(f"Guest Tools: {vm_manager.get_guest_tools_status()}")

        # Login
        print("\nLogin to VM...")
        if vm_manager.login('admin', 'admin'):
            print("Logged in successfully")
        else:
            print("Failed to log in")

        # Execute command
        print("\nExecuting command inside the VM...")
        result = vm_manager.execute_command('Get-Process')
        print(f"Exit Code: {result['exit_code']}")
        print(f"STDOUT:\n{result['stdout']}")
        print(f"STDERR:\n{result['stderr']}")

    # --- Example 3: All VMs info via PropertyCollector ---
    print("\n=== All VMs ===")
    all_vms = vsphere.get_all_vm_info(properties=["name", "guest.ipAddress"])
    for v in all_vms:
        print(f"  {v.get('name')} - {v.get('guest.ipAddress', 'N/A')}")

    # --- Example 4: Datastore info ---
    print("\n=== Datastores ===")
    datastores = vsphere.get_datastore_info()
    for host, ds_dict in datastores.items():
        print(f"  Host: {host}")
        for ds_name, details in ds_dict.items():
            print(f"    {ds_name}: {details['capacity_human']}")
