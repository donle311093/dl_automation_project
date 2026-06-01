"""FusionClient — HTTP client for VMware Fusion Pro REST API.

VMware Fusion Pro 13+ exposes a REST API (same as Workstation Pro) on port 8697.

Enable it via: VMware Fusion → Settings → Advanced → Enable REST API
Default URL:  http://<host>:8697/api
Auth:         HTTP Basic Auth (username / password set in Fusion preferences)
"""

import urllib3
import requests
from requests.auth import HTTPBasicAuth


class FusionClient:
    """Thin HTTP wrapper around the VMware Fusion Pro REST API."""

    _CONTENT_TYPE = "application/vnd.vmware.vmw.rest-v1+json"

    def __init__(self, host: str, port: int = 8697,
                 username: str = "", password: str = "",
                 verify_ssl: bool = False):
        """
        Args:
            host:       IP or hostname of the Mac running VMware Fusion Pro.
            port:       REST API port (default 8697).
            username:   Fusion REST API username.
            password:   Fusion REST API password.
            verify_ssl: Whether to verify SSL (usually False for self-signed certs).
        """
        self.host = host
        self.port = port
        self._base_url = f"http://{host}:{port}/api"
        self._auth = HTTPBasicAuth(username, password)
        self._verify_ssl = verify_ssl
        self._session: requests.Session | None = None

    def connect(self):
        """Open a session and verify the API is reachable."""
        if not self._verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({
            "Content-Type": self._CONTENT_TYPE,
            "Accept": self._CONTENT_TYPE,
        })
        self._session.verify = self._verify_ssl

        # Connectivity check
        resp = self._session.get(f"{self._base_url}/vms", timeout=10)
        resp.raise_for_status()
        return self

    def disconnect(self):
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None

    # --- HTTP helpers ---

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _check_connected(self):
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")

    def get(self, path: str):
        self._check_connected()
        resp = self._session.get(self._url(path), timeout=15)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def put(self, path: str, data=None):
        self._check_connected()
        resp = self._session.put(self._url(path), json=data, timeout=30)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def post(self, path: str, data=None):
        self._check_connected()
        resp = self._session.post(self._url(path), json=data, timeout=60)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def delete(self, path: str):
        self._check_connected()
        resp = self._session.delete(self._url(path), timeout=30)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
