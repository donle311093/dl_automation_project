"""ProxmoxTaskWaiter — Strategy Pattern for waiting on async Proxmox tasks.

Design Pattern: Strategy
- Encapsulates the task-polling algorithm so it can be reused by both
  ProxmoxVMManager and ProxmoxManager without code duplication.
"""

import time


class ProxmoxTaskWaiter:
    """Polls a Proxmox task until it completes or times out.

    Design Pattern: Strategy — the waiting algorithm is extracted into its own
    class so any object that needs it can compose it rather than duplicate code.
    """

    def __init__(self, api, node: str, timeout: int = 300, poll_interval: int = 2):
        """
        Args:
            api:           The proxmoxer root API object.
            node:          Proxmox node name where the task runs.
            timeout:       Maximum seconds to wait before giving up.
            poll_interval: Seconds between status checks.
        """
        self._api = api
        self._node = node
        self._timeout = timeout
        self._poll_interval = poll_interval

    def wait(self, upid: str) -> bool:
        """Block until the Proxmox task identified by *upid* finishes.

        Args:
            upid: The task UPID string returned by Proxmox API calls.

        Returns:
            True if the task succeeded, False if it failed or timed out.
        """
        elapsed = 0
        while elapsed < self._timeout:
            task_status = self._api.nodes(self._node).tasks(upid).status.get()
            if task_status.get("status") == "stopped":
                ok = task_status.get("exitstatus") == "OK"
                if not ok:
                    print(f"Task failed: {task_status.get('exitstatus')}")
                return ok
            time.sleep(self._poll_interval)
            elapsed += self._poll_interval

        print("Task timed out.")
        return False
