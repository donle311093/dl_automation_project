"""Example: Using SSHVMManager to manage a machine via SSH."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ssh.ssh_vm import SSHVMManager


# Target machine IP and SSH port
HOST = "10.40.164.21"
PORT = 22

# Guest credentials
USERNAME = "dev"
PASSWORD = "dev"

vm = SSHVMManager(HOST, PORT)

# Login via SSH
print(f"Connecting to {HOST}...")
if not vm.login(USERNAME, PASSWORD):
    print("Failed to connect.")
    exit(1)

# Get machine info
print("\nMachine info:")
info = vm.get_vm_info()
for key, value in info.items():
    print(f"  {key}: {value}")

print(f"\nConnection status: {vm.get_guest_tools_status()}")

# Execute a command
print("\nExecuting command...")
result = vm.execute_command("whoami")
print(f"  Exit Code: {result['exit_code']}")
print(f"  STDOUT: {result['stdout'].strip()}")

# Another command
print("\nDisk usage:")
result = vm.execute_command("df -h" if info.get("os_type") != "windows" else "wmic logicaldisk get size,freespace,caption")
print(f"  {result['stdout']}")

# Disconnect
vm.disconnect()
print("Disconnected.")
