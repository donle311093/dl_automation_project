"""
Datastore information helpers for vSphere.

Based on William Lam's script (www.virtuallyghetto.com).
"""

from pyVmomi import vim


def sizeof_fmt(num):
    """Return the human-readable version of a file size."""
    for item in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0:
            return "%.1f%s" % (num, item)
        num /= 1024.0
    return "%.1f%s" % (num, 'TB')


def get_datastore_info(client):
    """Return datastore info for all ESXi hosts visible to the connected vCenter.

    Args:
        client: A connected VCenterClient instance.

    Returns:
        A dict keyed by ESXi host name. Each value is a dict of VMFS datastores
        with details like uuid, capacity, vmfs_version, local, ssd, and extents.
    """
    content = client.si.RetrieveContent()
    objview = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True
    )

    try:
        datastores = {}
        for esxi_host in objview.view:
            storage_system = esxi_host.configManager.storageSystem
            mount_info_list = storage_system.fileSystemVolumeInfo.mountInfo

            datastore_dict = {}
            for host_mount_info in mount_info_list:
                if host_mount_info.volume.type == "VMFS":
                    extents = host_mount_info.volume.extent
                    datastore_details = {
                        'uuid': host_mount_info.volume.uuid,
                        'capacity': host_mount_info.volume.capacity,
                        'capacity_human': sizeof_fmt(host_mount_info.volume.capacity),
                        'vmfs_version': host_mount_info.volume.version,
                        'local': host_mount_info.volume.local,
                        'ssd': host_mount_info.volume.ssd,
                        'extents': [e.diskName for e in extents],
                    }
                    datastore_dict[host_mount_info.volume.name] = datastore_details

            datastores[esxi_host.name] = datastore_dict

        return datastores
    finally:
        objview.Destroy()


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from vsphere.vcenter_client import VCenterClient

    with VCenterClient() as client:
        datastores = get_datastore_info(client)
        for host_name, ds_dict in datastores.items():
            print(f"ESXi Host: {host_name}")
            for ds_name, details in ds_dict.items():
                print(f"  Datastore: {ds_name}")
                print(f"    UUID:         {details['uuid']}")
                print(f"    Capacity:     {details['capacity_human']}")
                print(f"    VMFS Version: {details['vmfs_version']}")
                print(f"    Local:        {details['local']}")
                print(f"    SSD:          {details['ssd']}")
                print(f"    Extents:      {details['extents']}")
            print()