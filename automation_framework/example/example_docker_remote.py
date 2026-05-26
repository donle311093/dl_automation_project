"""Example: Using DockerVMManager to manage a container on the local Docker host."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docker_impl.docker_vm import DockerVMManager


# Local WSL Docker host via Unix socket
DOCKER_HOST = "unix:///var/run/docker.sock"

# Container name on the host
CONTAINER = "test-container"

vm = DockerVMManager(CONTAINER, base_url=DOCKER_HOST)

if not vm._container:
    print("Container not found on remote host.")
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
print("\nExecute 'hostname':")
result = vm.execute_command("hostname")
print(f"  STDOUT: {result['stdout'].strip()}")

# Cleanup
vm.disconnect()
print("\nDone.")
