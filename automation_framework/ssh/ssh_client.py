import paramiko


class SSHClient:
    """SSH client for connecting to a remote machine."""

    def __init__(self, host, port=22):
        self.host = host
        self.port = port
        self._client = None

    def connect(self, username, password):
        """Connect to the remote machine via SSH."""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self.host,
            port=self.port,
            username=username,
            password=password,
        )
        return self

    def disconnect(self):
        """Close the SSH connection."""
        if self._client:
            self._client.close()
            self._client = None

    def execute(self, command, timeout=None):
        """Execute a command and return stdout, stderr, exit code.

        Returns:
            A dict with keys: exit_code, stdout, stderr.
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")

        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return {
            "exit_code": exit_code,
            "stdout": stdout.read().decode('utf-8', errors='replace'),
            "stderr": stderr.read().decode('utf-8', errors='replace'),
        }

    @property
    def is_connected(self):
        """Check if the SSH connection is active."""
        if not self._client:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
