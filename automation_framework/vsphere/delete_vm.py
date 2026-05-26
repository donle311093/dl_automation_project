from pyVmomi import vim
from pyVim.task import WaitForTask
from .find_folder import find_folder


def _power_off_if_needed(vm):
    """Power off *vm* if it is currently powered on, then wait for completion."""
    if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOff:
        print(f"Powering off VM '{vm.name}' before deletion...")
        task = vm.PowerOffVM_Task()
        WaitForTask(task)


# Delete a VM by name within a specific folder
def delete_vm_inside_folder(client, folder_name, vm_name):
    folder = find_folder(client, folder_name)
    if not folder:
        return False

    container_view = client.get_container_view([vim.VirtualMachine])
    for vm in container_view.view:
        if vm.name == vm_name and vm.parent == folder:
            print(f"Found VM: {vm.name}. Deleting...")
            try:
                _power_off_if_needed(vm)
                task = vm.Destroy_Task()
                WaitForTask(task)
                print(f"VM '{vm_name}' deleted successfully.")
                return True
            except Exception as e:
                print(f"Failed to delete VM '{vm_name}': {e}")
                return False

    print(f"VM '{vm_name}' not found in folder '{folder_name}'.")
    return False

def delete_all_vm_inside_folder(client, folder_name):
    container_view = client.get_container_view([vim.Folder])

    folder = find_folder(client, folder_name)
    if not folder:
        return False

    container_view = client.get_container_view([vim.VirtualMachine])
    deleted_vms = []
    for vm in container_view.view:
        if vm.parent == folder:
            print(f"Found VM: {vm.name}. Deleting...")
            try:
                task = vm.Destroy_Task()
                WaitForTask(task)
                print(f"VM '{vm.name}' deleted successfully.")
                deleted_vms.append(vm.name)
            except Exception as e:
                print(f"Failed to delete VM '{vm.name}': {e}")

    if not deleted_vms:
        print(f"No VMs found in folder '{folder_name}' to delete.")
        return False

    return True

def delete_all_vm_by_name(client, vm_name):
    container_view = client.get_container_view([vim.VirtualMachine])
    deleted_vms = []
    for vm in container_view.view:
        if vm.name == vm_name:
            folder = vm.parent if isinstance(vm.parent, vim.Folder) else None
            folder_name = folder.name if folder else "(unknown)"
            print(f"Found VM: {vm.name}  |  Folder: {folder_name}. Deleting...")
            try:
                task = vm.Destroy_Task()
                WaitForTask(task)
                print(f"VM '{vm.name}' deleted successfully.")
                deleted_vms.append(vm.name)
            except Exception as e:
                print(f"Failed to delete VM '{vm.name}': {e}")

    if not deleted_vms:
        print(f"VM '{vm_name}' not found in any folder to delete.")
        return False

    return True
