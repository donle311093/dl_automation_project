from pyVmomi import vim
from .vcenter_client import VCenterClient
from .find_folder import find_folder

# Find a VM by name within a specific folder
def find_vm_inside_folder(client, folder_name, vm_name):
    container_view = client.get_container_view([vim.Folder])

    folder = find_folder(client, folder_name)
    if not folder:
        return None

    container_view = client.get_container_view([vim.VirtualMachine])
    for vm in container_view.view:
        if vm.name == vm_name and vm.parent == folder:
            print(f"Found VM: {vm.name}")
            container_view.Destroy()
            return vm

    print(f"VM '{vm_name}' not found in folder '{folder_name}'.")
    container_view.Destroy()
    return None

# Find all VMs inside a specific folder
def find_all_vm_inside_folder(client, folder_name):
    container_view = client.get_container_view([vim.Folder])

    folder = find_folder(client, folder_name)
    if not folder:
        return None

    container_view = client.get_container_view([vim.VirtualMachine])
    vms_in_folder = []
    for vm in container_view.view:
        if vm.parent == folder:
            print(f"Found VM: {vm.name}")
            vms_in_folder.append(vm)

    if not vms_in_folder:
        print(f"No VMs found in folder '{folder_name}'.")

    container_view.Destroy()
    return vms_in_folder

# Find all VMs with a given name across all folders
def find_all_vm_by_name(client, vm_name):
    container_view = client.get_container_view([vim.VirtualMachine])
    try:
        results = []
        for vm in container_view.view:
            if vm.name == vm_name:
                folder = vm.parent if isinstance(vm.parent, vim.Folder) else None
                folder_name = folder.name if folder else "(unknown)"
                print(f"Found VM: {vm.name}  |  Folder: {folder_name}")
                results.append({"vm": vm, "folder": folder})
    finally:
        container_view.Destroy()

    if not results:
        print(f"VM '{vm_name}' not found in any folder.")
    return results

if __name__ == "__main__":
    with VCenterClient() as client:
        vm = find_vm_inside_folder(client, 'Personal VM', 'Windows-11-Don')
        vms = find_all_vm_inside_folder(client, 'VM_Template')
