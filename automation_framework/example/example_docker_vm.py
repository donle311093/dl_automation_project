"""Example: Using DockerVMManager to manage a Docker container like a VM."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docker_impl.docker_vm import DockerVMManager


# Container name or ID
CONTAINER = "test-container"

vm = DockerVMManager(CONTAINER)

if not vm._container:
    print("Container not found.")
    exit(1)

# Power status
print(f"Power status: {vm.get_power_status()}")

# Login (start container if needed)
vm.login("", "")

# Get info
print("\nContainer info:")
info = vm.get_vm_info()
for key, value in info.items():
    print(f"  {key}: {value}")

# Execute command
print("\nExecute 'whoami':")
result = vm.execute_command("whoami")
print(f"  Exit Code: {result['exit_code']}")
print(f"  STDOUT: {result['stdout'].strip()}")

# Execute another command
print("\nExecute 'ls /':")
result = vm.execute_command("ls /")
print(f"  {result['stdout']}")

# Create snapshot (docker commit)
print("\nCreating snapshot...")
vm.create_snapshot("test_snapshot", description="Test snapshot")

# List snapshots
print("Snapshots:")
for snap in vm.get_snapshots():
    print(f"  {snap['name']} ({snap['id']})")

# Clone container
print("\nCloning container...")
vm.clone(
    target_folder_name="",
    new_vm_name="cloned-container",
    num_cpus=2,
    memory_mb=512,
    annotation="Cloned from my-container",
    power_on=False,
)

# Cleanup
vm.disconnect()
print("\nDone.")
