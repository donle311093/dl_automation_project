from pyVmomi import vim
from pyVim.task import WaitForTask
from .find_folder import find_folder
from .snapshot import SnapshotManager
from .datastore import find_datastore_by_name


def clone_vm(client, vm, target_folder_name, new_vm_name,
             snapshot_name=None, datastore_name=None, annotation=None,
             num_cpus=None, memory_mb=None, power_on=False):
    """Clone a VM to a target folder.

    Args:
        client: A connected VCenterClient instance.
        vm: The source vim.VirtualMachine managed object.
        target_folder_name: Name of the destination folder.
        new_vm_name: Name for the cloned VM.
        snapshot_name: If provided, clone from this snapshot (linked clone).
                       If None, clone the current state (full clone).
        datastore_name: If provided, place the clone on this datastore.
                        If None, use the same datastore as the source VM.
        annotation: If provided, set this annotation on the cloned VM.
        num_cpus: If provided, set the number of CPUs on the cloned VM.
                  If None, keep the same as the source VM.
        memory_mb: If provided, set the memory (MB) on the cloned VM.
                   If None, keep the same as the source VM.
        power_on: Whether to power on the clone after creation.

    Returns:
        True if clone succeeded, False otherwise.
    """
    target_folder = find_folder(client, target_folder_name)
    if not target_folder:
        print(f"Target folder '{target_folder_name}' not found.")
        return False

    relocate_spec = vim.vm.RelocateSpec()

    # Datastore
    if datastore_name:
        datastore = find_datastore_by_name(client, datastore_name)
        if not datastore:
            print(f"Datastore '{datastore_name}' not found.")
            return False
        relocate_spec.datastore = datastore

    clone_spec = vim.vm.CloneSpec()
    clone_spec.location = relocate_spec
    clone_spec.powerOn = power_on
    clone_spec.template = False

    # Snapshot
    if snapshot_name:
        snapshot_mgr = SnapshotManager(vm)
        snapshot = snapshot_mgr.find_snapshot_by_name(snapshot_name)
        if not snapshot:
            print(f"Snapshot '{snapshot_name}' not found in VM '{vm.name}'.")
            return False
        clone_spec.snapshot = snapshot

    # Annotation / CPU / RAM
    if annotation is not None or num_cpus is not None or memory_mb is not None:
        config_spec = vim.vm.ConfigSpec()
        if annotation is not None:
            config_spec.annotation = annotation
        if num_cpus is not None:
            config_spec.numCPUs = num_cpus
        if memory_mb is not None:
            config_spec.memoryMB = memory_mb
        clone_spec.config = config_spec

    print(f"Cloning VM '{vm.name}' -> '{new_vm_name}' in folder '{target_folder_name}'...")
    task = vm.CloneVM_Task(folder=target_folder, name=new_vm_name, spec=clone_spec)
    WaitForTask(task)

    if task.info.state == 'success':
        print(f"Clone '{new_vm_name}' completed successfully.")
        return True
    else:
        print(f"Clone '{new_vm_name}' failed: {task.info.error}")
        return False
