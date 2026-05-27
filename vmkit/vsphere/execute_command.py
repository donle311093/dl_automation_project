import sys
import os

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import time
import base64
import warnings
import requests
from urllib3.exceptions import InsecureRequestWarning
from pyVmomi import vim

from vsphere.login import detect_ostype, OSTYPE

warnings.simplefilter('ignore', InsecureRequestWarning)


def _make_credentials(username, password):
    """Create a guest authentication object."""
    return vim.vm.guest.NamePasswordAuthentication(
        username=username, password=password
    )


def _check_tools(vm):
    """Raise if VMware Tools is not running."""
    tools_status = vm.guest.toolsStatus
    if tools_status in ('toolsNotInstalled', 'toolsNotRunning'):
        raise RuntimeError(
            f"VMware Tools is not running on '{vm.name}' (status: {tools_status})"
        )


def _wait_for_process(process_manager, vm, creds, pid, poll_interval=0.1, verbose=False):
    """Wait for a guest process to finish and return the exit code."""
    exit_code = process_manager.ListProcessesInGuest(vm, creds, [pid]).pop().exitCode
    while exit_code is None:
        if verbose:
            print(f"Program running, PID is {pid}")
        time.sleep(poll_interval)
        exit_code = process_manager.ListProcessesInGuest(vm, creds, [pid]).pop().exitCode
    return exit_code


def _read_guest_file(file_manager, vm, creds, remote_path):
    """Download a file from guest OS via the file manager."""
    file_info = file_manager.InitiateFileTransferFromGuest(vm, creds, remote_path)
    response = requests.get(file_info.url, verify=False)
    if len(response.content) != file_info.size:
        raise RuntimeError(
            f"File size mismatch for {remote_path}: "
            f"got {len(response.content)} bytes, expected {file_info.size} bytes"
        )
    return response.content


def _decode_clixml(data):
    """Decode output bytes and strip PowerShell CLIXML wrappers."""
    decoded = data.decode('utf-8', errors='replace')
    cleaned = re.sub(r'#< CLIXML\r?\n<Objs[\s\S]*?</Objs>', '', decoded).strip()
    return cleaned


def execute_command(client, vm, guest_user, guest_pass, command,
                    capture_output=True, poll_interval=0.1, verbose=False):
    """Execute a command inside a VM via VMware Tools.

    Auto-detects OS type: uses PowerShell on Windows, /bin/sh on Linux/macOS.
    Optionally captures stdout/stderr by redirecting to temp files.

    Args:
        client: A connected VCenterClient instance.
        vm: A vim.VirtualMachine managed object.
        guest_user: Guest OS username.
        guest_pass: Guest OS password.
        command: The command string to execute.
        capture_output: If True, capture and return stdout/stderr (Windows only).
        poll_interval: Seconds between poll attempts while waiting for completion.

    Returns:
        A dict with keys: pid, exit_code, stdout, stderr.
    """
    _check_tools(vm)

    content = client.si.RetrieveContent()
    creds = _make_credentials(guest_user, guest_pass)
    process_manager = content.guestOperationsManager.processManager
    ostype = detect_ostype(vm)

    if ostype == OSTYPE['WINDOWS']:
        if capture_output:
            ts = int(time.time())
            tmp_out = f"C:\\Windows\\TEMP\\vm_exec_out_{ts}"
            tmp_err = f"C:\\Windows\\TEMP\\vm_exec_err_{ts}"
            ps_script = f"& {{ {command} }} 1>'{tmp_out}' 2>'{tmp_err}'"
            encoded_command = base64.b64encode(ps_script.encode('utf-16le')).decode('ascii')
        else:
            encoded_command = base64.b64encode(command.encode('utf-16le')).decode('ascii')

        program_spec = vim.vm.guest.ProcessManager.ProgramSpec(
            programPath='C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
            arguments=f'-encodedCommand {encoded_command}'
        )
    else:
        # Linux / macOS
        program_spec = vim.vm.guest.ProcessManager.ProgramSpec(
            programPath='/bin/sh',
            arguments=f'-c "{command}"'
        )

    pid = process_manager.StartProgramInGuest(vm, creds, program_spec)
    if verbose:
        print(f"Program submitted, PID is {pid}")

    exit_code = _wait_for_process(process_manager, vm, creds, pid, poll_interval, verbose=verbose)

    if verbose:
        if exit_code == 0:
            print(f"Program {pid} completed with success")
        else:
            print(f"ERROR: Program {pid} completed with failure, exit code: {exit_code}")

    result = {"pid": pid, "exit_code": exit_code, "stdout": "", "stderr": ""}

    if capture_output and ostype == OSTYPE['WINDOWS']:
        file_manager = content.guestOperationsManager.fileManager
        raw_out = _read_guest_file(file_manager, vm, creds, tmp_out)
        raw_err = _read_guest_file(file_manager, vm, creds, tmp_err)
        result["stdout"] = _decode_clixml(raw_out)
        result["stderr"] = _decode_clixml(raw_err)

    return result


if __name__ == "__main__":
    from vsphere.vcenter_client import VCenterClient
    from vsphere.find_vm import find_vm_inside_folder
    from vsphere.login import login_to_vm

    with VCenterClient() as client:
        vm = find_vm_inside_folder(client, 'VCR Test', 'windows-10-64-autologin_autotest_01')
        if not vm:
            print("VM not found.")
            exit(1)

        # Login first
        if not login_to_vm(client, vm, 'admin', 'admin'):
            print("Failed to log in.")
            exit(1)

        # Execute with output capture
        result = execute_command(client, vm, 'admin', 'admin', 'Get-Process')
        print(f"Exit Code: {result['exit_code']}")
        print(f"STDOUT:\n{result['stdout']}")
        print(f"STDERR:\n{result['stderr']}")
