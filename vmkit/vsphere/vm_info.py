from pyVmomi import vim, vmodl
from .annotation import get_annotation


DEFAULT_VM_PROPERTIES = [
    "name",
    "config.uuid",
    "config.hardware.numCPU",
    "config.hardware.memoryMB",
    "guest.guestState",
    "guest.ipAddress",
    "config.guestFullName",
    "config.guestId",
    "config.version",
]


def get_vm_info(vm):
    """Return a dictionary with basic information about the VM."""
    config = vm.config
    info = {
        "name": vm.name,
        "power_state": vm.runtime.powerState,
        "num_cpu": config.hardware.numCPU if config else None,
        "memory_mb": config.hardware.memoryMB if config else None,
        "ip_address": vm.guest.ipAddress if vm.guest else None,
        "guest_id": config.guestId if config else None,
        "guest_full_name": config.guestFullName if config else None,
        "annotation": get_annotation(vm),
    }
    return info

def get_vmtools_status(vm):
    """Return the VMware Tools status of the VM."""
    if not vm or not hasattr(vm, 'guest') or not vm.guest:
        return "VMware Tools status unknown (VM or guest info not available)"
    
    tools_status = vm.guest.toolsStatus
    return tools_status if tools_status else "VMware Tools status unknown"

def get_all_vm_info(client, properties=None):
    """Collect properties for all VMs using the PropertyCollector.

    Args:
        client: A connected VCenterClient instance.
        properties: List of property paths to collect (e.g. ["name", "config.uuid"]).
                    Defaults to DEFAULT_VM_PROPERTIES.

    Returns:
        A list of dicts, one per VM, mapping property paths to their values.
    """
    if properties is None:
        properties = DEFAULT_VM_PROPERTIES

    content = client.si.RetrieveContent()
    view = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )

    try:
        # Build the PropertyCollector filter spec
        traversal_spec = vmodl.query.PropertyCollector.TraversalSpec(
            name="traverseEntities",
            path="view",
            skip=False,
            type=vim.view.ContainerView,
        )
        obj_spec = vmodl.query.PropertyCollector.ObjectSpec(
            obj=view,
            skip=True,
            selectSet=[traversal_spec],
        )
        prop_spec = vmodl.query.PropertyCollector.PropertySpec(
            type=vim.VirtualMachine,
            all=False,
            pathSet=properties,
        )
        filter_spec = vmodl.query.PropertyCollector.FilterSpec(
            objectSet=[obj_spec],
            propSet=[prop_spec],
        )

        result = content.propertyCollector.RetrieveContents([filter_spec])

        vm_data = []
        for obj in result:
            vm_dict = {}
            for prop in obj.propSet:
                vm_dict[prop.name] = prop.val
            vm_data.append(vm_dict)

        return vm_data
    finally:
        view.Destroy()