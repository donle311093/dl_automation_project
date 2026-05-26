from pyVmomi import vim


def find_datastore_by_name(client, datastore_name):
    """Find a datastore by name.

    Args:
        client: A connected VCenterClient instance.
        datastore_name: Name of the datastore to find.

    Returns:
        The datastore managed object, or None if not found.
    """
    view = client.get_container_view([vim.Datastore])
    try:
        for ds in view.view:
            if ds.name == datastore_name:
                return ds
    finally:
        view.Destroy()
    return None
