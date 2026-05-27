from pyVmomi import vim
from pyVim.task import WaitForTask
from enum import StrEnum


class PowerStatus(StrEnum):
    ON = "Powered On"
    OFF = "Powered Off"
    SUSPENDED = "Suspended"
    UNKNOWN = "Unknown"


class PowerManager:
    def __init__(self, vm):
        self.vm = vm

    def status(self):
        """Return the power status of the VM."""
        state = self.vm.runtime.powerState
        if state == vim.VirtualMachinePowerState.poweredOn:
            return PowerStatus.ON
        elif state == vim.VirtualMachinePowerState.poweredOff:
            return PowerStatus.OFF
        elif state == vim.VirtualMachinePowerState.suspended:
            return PowerStatus.SUSPENDED
        else:
            return PowerStatus.UNKNOWN

    def power_on(self):
        """Power on the VM."""
        if self.status() != PowerStatus.ON:
            task = self.vm.PowerOnVM_Task()
            WaitForTask(task)
            if task.info.state == 'success':
                print(f"VM '{self.vm.name}' powered on successfully.")
                return True
            else:
                print(f"Failed to power on VM '{self.vm.name}'.")
                return False
        else:
            print(f"VM '{self.vm.name}' is already powered on.")
            return True

    def power_off(self):
        """Power off the VM."""
        if self.status() != PowerStatus.OFF:
            task = self.vm.PowerOffVM_Task()
            WaitForTask(task)
            if task.info.state == 'success':
                print(f"VM '{self.vm.name}' powered off successfully.")
                return True
            else:
                print(f"Failed to power off VM '{self.vm.name}'.")
                return False
        else:
            print(f"VM '{self.vm.name}' is already powered off.")
            return True

    def suspend(self):
        """Suspend the VM."""
        if self.status() != PowerStatus.SUSPENDED:
            task = self.vm.SuspendVM_Task()
            WaitForTask(task)
            if task.info.state == 'success':
                print(f"VM '{self.vm.name}' suspended successfully.")
                return True
            else:
                print(f"Failed to suspend VM '{self.vm.name}'.")
                return False
        else:
            print(f"VM '{self.vm.name}' is already suspended.")
            return True
    
    def reboot(self):
        """Reboot the VM."""
        if self.status() == PowerStatus.ON:
            task = self.vm.RebootGuest()
            WaitForTask(task)
            if task.info.state == 'success':
                print(f"VM '{self.vm.name}' rebooted successfully.")
                return True
            else:
                print(f"Failed to reboot VM '{self.vm.name}'.")
                return False
        else:
            print(f"VM '{self.vm.name}' must be powered on to reboot.")
            return False
        
    def reset(self):
        """Reset the VM."""
        if self.status() == PowerStatus.ON:
            task = self.vm.ResetVM_Task()
            WaitForTask(task)
            if task.info.state == 'success':
                print(f"VM '{self.vm.name}' reset successfully.")
                return True
            else:
                print(f"Failed to reset VM '{self.vm.name}'.")
                return False
        else:
            print(f"VM '{self.vm.name}' must be powered on to reset.")
            return False