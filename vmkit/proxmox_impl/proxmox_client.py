from proxmoxer import ProxmoxAPI


class ProxmoxClient:
    """Wrapper around Proxmox API client."""

    def __init__(self, host, user, password, port=8006, verify_ssl=False):
        """
        Args:
            host: Proxmox host IP or hostname.
            user: Proxmox user (e.g. 'root@pam').
            password: Proxmox password.
            port: API port (default 8006).
            verify_ssl: Whether to verify SSL certificates.
        """
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.verify_ssl = verify_ssl
        self._api = None

    def connect(self):
        """Connect to the Proxmox API."""
        self._api = ProxmoxAPI(
            self.host,
            user=self.user,
            password=self.password,
            port=self.port,
            verify_ssl=self.verify_ssl,
        )
        return self

    def disconnect(self):
        """Proxmoxer doesn't require explicit disconnect."""
        self._api = None

    @property
    def api(self):
        if not self._api:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._api

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
