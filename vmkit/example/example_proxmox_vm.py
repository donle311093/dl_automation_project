"""Example: Proxmox VM management using ProxmoxManager and ProxmoxVMManager."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proxmox_impl.proxmox_manager import ProxmoxManager

# --- Configuration ---
PROXMOX_HOST = "10.40.164.95"
PROXMOX_USER = "root@pam"
PROXMOX_PASS = "P@ssw0rd123456"
PROXMOX_PORT = 8006

VM_NAME = "VM 100"
NODE_NAME = "don"  # Optional: specify node, or None for auto-detect

# Choose what to test:  info | power | snapshot | exec | clone | list
TEST = "info"


def example_info(mgr):
    """Get VM info."""
    vm = mgr.get_vm(VM_NAME, NODE_NAME)
    info = vm.get_vm_info()
    print("VM Info:")
    for k, v in info.items():
        print(f"  {k}: {v}")

    tools_status = vm.get_guest_tools_status()
    print(f"  Guest Agent: {tools_status}")


def example_power(mgr):
    """Power operations."""
    vm = mgr.get_vm(VM_NAME, NODE_NAME)
    print(f"Power status: {vm.get_power_status()}")
    # vm.power_on()
    # vm.power_off()
    # vm.reboot()


def example_snapshot(mgr):
    """Snapshot operations."""
    vm = mgr.get_vm(VM_NAME, NODE_NAME)

    # List snapshots
    snapshots = vm.get_snapshots()
    print(f"Snapshots ({len(snapshots)}):")
    for s in snapshots:
        print(f"  - {s.get('name')}: {s.get('description', '')}")

    # Create snapshot
    # vm.create_snapshot("test-snap", description="Created from script")

    # Revert to snapshot
    # vm.revert_to_snapshot("test-snap")

    # Delete snapshot
    # vm.delete_snapshot("test-snap")


def example_exec(mgr):
    """Execute command via QEMU Guest Agent."""
    vm = mgr.get_vm(VM_NAME, NODE_NAME)

    # Login (verifies guest agent is running)
    if vm.login("opswat", "admin"):
        result = vm.execute_command("hostname")
        print(f"Exit code: {result['exit_code']}")
        print(f"stdout: {result['stdout']}")
        print(f"stderr: {result['stderr']}")


def example_clone(mgr):
    """Clone a VM."""
    vm = mgr.get_vm(VM_NAME, NODE_NAME)
    vm.clone(
        target_folder_name=NODE_NAME,
        new_vm_name="cloned-vm",
        annotation="Cloned from script",
        num_cpus=2,
        memory_mb=2048,
    )


def example_list(mgr):
    """List all VMs across all nodes."""
    all_vms = mgr.get_all_vm_info()
    print(f"Total VMs: {len(all_vms)}")
    for vm in all_vms:
        print(f"  [{vm['node']}] {vm['name']} (VMID: {vm['vmid']}) - {vm['status']}")

    # Storage info
    print("\nStorage:")
    storage = mgr.get_datastore_info()
    for node, stores in storage.items():
        print(f"  Node: {node}")
        for s in stores:
            print(f"    {s['storage']} ({s['type']}): {s['avail']} avail / {s['total']} total")


if __name__ == "__main__":
    with ProxmoxManager(PROXMOX_HOST, PROXMOX_USER, PROXMOX_PASS, PROXMOX_PORT) as mgr:
        tests = {
            "info": example_info,
            "power": example_power,
            "snapshot": example_snapshot,
            "exec": example_exec,
            "clone": example_clone,
            "list": example_list,
        }

        test_func = tests.get(TEST)
        if test_func:
            test_func(mgr)
        else:
            print(f"Unknown TEST: '{TEST}'. Choose from: {', '.join(tests.keys())}")
