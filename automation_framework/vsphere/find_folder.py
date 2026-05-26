from pyVmomi import vim

def find_folder(client, folder_name):
    container_view = client.get_container_view([vim.Folder])

    for folder in container_view.view:
        if folder.name == folder_name:
            print(f"Found folder: {folder.name}")
            container_view.Destroy()
            return folder

    print(f"Folder '{folder_name}' not found.")
    container_view.Destroy()
    return None


# Example usage (run with: python -m vsphere.find_folder from pyvmomi_example/)
if __name__ == "__main__":
    from vcenter_client import VCenterClient
    with VCenterClient() as client:
        folder = find_folder(client, 'DON_Test')
