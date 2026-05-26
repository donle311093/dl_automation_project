from pyVmomi import vim
from pyVim.task import WaitForTask

def get_annotation(vm):
    """Return the annotation of a VM as a string."""
    if vm.config and hasattr(vm.config, 'annotation') and vm.config.annotation:
        return vm.config.annotation
    else:
        return "No annotation set."

def set_annotation(vm, annotation):
    """Set the annotation of a VM."""
    spec = vim.vm.ConfigSpec()
    spec.annotation = annotation
    task = vm.ReconfigVM_Task(spec)
    WaitForTask(task)
    return task.info.state == 'success'