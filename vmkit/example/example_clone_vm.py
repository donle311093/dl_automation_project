"""Example: Clone a VM to another folder."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vsphere.vcenter_client import VCenterClient
from vsphere.vsphere_vm import VSphereVMManager as VMManager


with VCenterClient() as client:
    vm_manager = VMManager(client, 'windows-11-64', folder_name='VM_Template')

    if not vm_manager.vm:
        print("VM not found.")
        exit(1)

    print(f"Source VM: {vm_manager.vm.name}")
    print(f"Power status: {vm_manager.get_power_status()}")

    # Clone VM to 'Personal VM' folder
    print("\nCloning VM...")
    success = vm_manager.clone(
        target_folder_name='Personal VM',
        new_vm_name='cloned-windows-11-64',
        annotation='Cloned from VM_Template',
    )

    if success:
        print("Clone completed.")
    else:
        print("Clone failed.")
