from pyVmomi import vim
from pyVim.task import WaitForTask

class SnapshotManager:
    def __init__(self, vm):
        self.vm = vm
    
    def list_all_snapshots(self):
        """List all snapshots of the VM."""
        if not self.vm or not hasattr(self.vm, 'snapshot') or not self.vm.snapshot:
            print(f"No snapshots found for VM '{self.vm.name}'.")
            return []
        
        snapshots = []
        def _traverse_snapshots(snap_tree):
            for snap in snap_tree:
                snapshots.append(snap)
                if snap.childSnapshotList:
                    _traverse_snapshots(snap.childSnapshotList)
        
        _traverse_snapshots(self.vm.snapshot.rootSnapshotList)
        return snapshots

    def find_snapshot_by_name(self, snapshot_name):
        """Find a snapshot MOR by name in the VM's snapshot tree."""
        if not self.vm or not hasattr(self.vm, 'snapshot') or not self.vm.snapshot:
            return None

        def _search(snap_list):
            for snap in snap_list:
                if snap.name == snapshot_name:
                    return snap.snapshot
                found = _search(snap.childSnapshotList)
                if found:
                    return found
            return None

        return _search(self.vm.snapshot.rootSnapshotList)

    def create_snapshot(self, name, description="", memory=False, quiesce=False):
        """Create a snapshot of the VM."""
        if not self.vm:
            print("VM not found. Cannot create snapshot.")
            return False
        
        task = self.vm.CreateSnapshot_Task(name=name, description=description, memory=memory, quiesce=quiesce)
        WaitForTask(task)
        if task.info.state == 'success':
            print(f"Snapshot '{name}' created successfully for VM '{self.vm.name}'.")
            return True
        else:
            print(f"Failed to create snapshot '{name}' for VM '{self.vm.name}'.")
            return False

    def revert_to_current_snapshot(self):
        """Revert the VM to the current snapshot."""
        if not self.vm or not hasattr(self.vm, 'snapshot') or not self.vm.snapshot:
            print(f"No snapshots found for VM '{self.vm.name}'. Cannot revert.")
            return False
        
        task = self.vm.RevertToCurrentSnapshot_Task()
        WaitForTask(task)
        if task.info.state == 'success':
            print(f"VM '{self.vm.name}' reverted to current snapshot successfully.")
            return True
        else:
            print(f"Failed to revert VM '{self.vm.name}' to current snapshot.")
            return False
        
    def revert_to_snapshot(self, snapshot_name):
        """Revert the VM to a specific snapshot by name."""
        snapshots = self.list_all_snapshots()
        target_snapshot = None
        for snap in snapshots:
            if snap.name == snapshot_name:
                target_snapshot = snap
                break
        if not target_snapshot:
            print(f"Snapshot '{snapshot_name}' not found for VM '{self.vm.name}'. Cannot revert.")
            return False
        
        task = target_snapshot.snapshot.RevertToSnapshot_Task()
        WaitForTask(task)
        if task.info.state == 'success':
            print(f"VM '{self.vm.name}' reverted to snapshot '{snapshot_name}' successfully.")
            return True
        else:
            print(f"Failed to revert VM '{self.vm.name}' to snapshot '{snapshot_name}'.")
            return False
        
    def delete_snapshot(self, snapshot_name):
        """Delete a specific snapshot by name."""
        snapshots = self.list_all_snapshots()
        target_snapshot = None
        for snap in snapshots:
            if snap.name == snapshot_name:
                target_snapshot = snap
                break
        if not target_snapshot:
            print(f"Snapshot '{snapshot_name}' not found for VM '{self.vm.name}'. Cannot delete.")
            return False
        
        task = target_snapshot.snapshot.RemoveSnapshot_Task(removeChildren=True)
        WaitForTask(task)
        if task.info.state == 'success':
            print(f"Snapshot '{snapshot_name}' deleted successfully for VM '{self.vm.name}'.")
            return True
        else:
            print(f"Failed to delete snapshot '{snapshot_name}' for VM '{self.vm.name}'.")
            return False
