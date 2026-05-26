"""Example: VMware Fusion Pro VM management via REST API.

Requires:
    - VMware Fusion Pro 13+ on the target Mac
    - REST API enabled: Fusion → Settings → Advanced → Enable REST API
    - VMware Tools installed in guest (for execute_command)

Setup on Mac:
    1. Open VMware Fusion Pro → Settings → Advanced
    2. Enable "VMware Fusion REST API"
    3. Set a username and password for the REST API
    4. Note the port (default: 8697)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fusion_impl.fusion_manager import FusionManager
from core.factory import HypervisorFactory
from core.models import CloneConfigBuilder

# --- Configuration ---
FUSION_HOST = "192.168.1.100"    # IP of the Mac running VMware Fusion Pro
FUSION_PORT = 8697
FUSION_USER = "admin"
FUSION_PASS = "password"

VM_NAME = "Ubuntu 22.04"          # Display name of the VM in Fusion

# Choose what to test: info | power | snapshot | exec | clone | list | factory
TEST = "info"


def example_info(mgr):
    """Get detailed VM info."""
    vm = mgr.get_vm(VM_NAME)
    info = vm.get_vm_info()
    print("VM Info:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"  Power status:  {vm.get_power_status()}")
    print(f"  Guest tools:   {vm.get_guest_tools_status()}")
    print(f"  Annotation:    {vm.get_annotation()}")


def example_power(mgr):
    """Power operations."""
    vm = mgr.get_vm(VM_NAME)
    print(f"Power status: {vm.get_power_status()}")
    # vm.power_on()
    # vm.power_off()
    # vm.suspend()
    # vm.reboot()
    # vm.reset()


def example_snapshot(mgr):
    """Snapshot operations."""
    vm = mgr.get_vm(VM_NAME)

    snapshots = vm.get_snapshots()
    print(f"Snapshots ({len(snapshots)}):")
    for s in snapshots:
        print(f"  - [{s.get('id')}] {s.get('name')}: {s.get('description', '')}")

    # Create snapshot
    # vm.create_snapshot("before-update", description="Pre-patch baseline")

    # Revert to most recent snapshot
    # vm.revert_to_current_snapshot()

    # Revert to a specific snapshot
    # vm.revert_to_snapshot("before-update")

    # Delete a snapshot
    # vm.delete_snapshot("before-update")


def example_exec(mgr):
    """Execute a command inside the guest via VMware Tools."""
    vm = mgr.get_vm(VM_NAME)

    # Login stores credentials; detects guest OS automatically
    if not vm.login("devuser", "devpass"):
        print("Login failed.")
        return

    result = vm.execute_command("hostname && uname -r")
    print(f"Exit code: {result['exit_code']}")
    print(f"stdout:    {result['stdout']}")
    print(f"stderr:    {result['stderr']}")


def example_clone(mgr):
    """Clone a VM using the Builder pattern."""
    vm = mgr.get_vm(VM_NAME)

    config = (
        CloneConfigBuilder()
        .target_folder("")
        .name("ubuntu-22-clone")
        .annotation("Cloned via FusionManager")
        .cpus(2)
        .memory_mb(2048)
        .power_on(False)
        .build()
    )

    vm.clone_with_config(config)


def example_list(mgr):
    """List all VMs registered in Fusion."""
    all_vms = mgr.get_all_vm_info()
    print(f"Total VMs: {len(all_vms)}")
    for vm in all_vms:
        print(f"  [{vm['status']:10}] {vm['name']}  "
              f"CPU: {vm['num_cpu']}  RAM: {vm['memory_mb']} MB  "
              f"ID: {vm['id']}")


def example_factory():
    """Create a FusionManager via the HypervisorFactory (Factory Pattern)."""
    with HypervisorFactory.create("fusion", {
        "host":     FUSION_HOST,
        "port":     FUSION_PORT,
        "username": FUSION_USER,
        "password": FUSION_PASS,
    }) as mgr:
        example_list(mgr)


if __name__ == "__main__":
    tests = {
        "info":     example_info,
        "power":    example_power,
        "snapshot": example_snapshot,
        "exec":     example_exec,
        "clone":    example_clone,
        "list":     example_list,
        "factory":  lambda _: example_factory(),
    }

    test_func = tests.get(TEST)
    if not test_func:
        print(f"Unknown TEST: '{TEST}'. Choose from: {', '.join(tests)}")
        sys.exit(1)

    if TEST == "factory":
        test_func(None)
    else:
        with FusionManager(FUSION_HOST, FUSION_PORT, FUSION_USER, FUSION_PASS) as mgr:
            test_func(mgr)
