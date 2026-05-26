from pyVmomi import vim
from pyVim.task import WaitForTask

def delete_folder(client, folder_name):
    container_view = client.get_container_view([vim.Folder])

    for folder in container_view.view:
        if folder.name == folder_name:
            print(f"Found folder: {folder.name}. Deleting...")
            try:
                task = folder.Destroy_Task()
                WaitForTask(task)
                print(f"Folder '{folder_name}' deleted successfully.")
                return True
            except Exception as e:
                print(f"Failed to delete folder '{folder_name}': {e}")
                return False

    print(f"Folder '{folder_name}' not found.")
    return False

# Example usage
if __name__ == "__main__":
    from vcenter_client import VCenterClient
    with VCenterClient() as client:
        folder = delete_folder(client, 'DON_Test')