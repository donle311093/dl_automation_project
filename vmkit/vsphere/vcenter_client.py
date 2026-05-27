from pyVim.connect import SmartConnect, Disconnect
import ssl
import configparser
import os


class VCenterClient:
    def __init__(self, config_path=None, host=None, user=None, password=None,
                 port=443, ssl_verify=False):
        """Prepare vCenter credentials either from direct params or a config file.

        Priority: direct params (host/user/password) > config file.
        ssl_verify=False skips certificate verification (needed for self-signed certs).
        """
        if host and user and password:
            self.host = host
            self.user = user
            self.password = password
            self.port = port
        else:
            if config_path is None:
                config_path = os.path.join(os.path.dirname(__file__), ".config")

            _config = configparser.ConfigParser()
            files_read = _config.read(config_path)

            if not files_read:
                raise FileNotFoundError(
                    f"Config file not found at: {os.path.abspath(config_path)}"
                )

            if "vcenter" not in _config:
                raise ValueError(
                    f"Config file at {os.path.abspath(config_path)} is missing [vcenter] section"
                )

            vc = _config["vcenter"]
            self.host = vc["host"]
            self.user = vc["user"]
            self.password = vc["password"]
            self.port = int(vc.get("port", 443))
            # ssl_verify in config file takes precedence over the param default
            ssl_verify = vc.get("ssl_verify", "false").lower() == "true"

        self._context = ssl.create_default_context()
        if not ssl_verify:
            self._context.check_hostname = False
            self._context.verify_mode = ssl.CERT_NONE
        self.si = None

    def connect(self):
        """Establish a connection to vCenter and return the ServiceInstance."""
        self.si = SmartConnect(
            host=self.host,
            user=self.user,
            pwd=self.password,
            port=self.port,
            sslContext=self._context,
        )
        return self.si

    def disconnect(self):
        """Disconnect from vCenter if a session is active."""
        if self.si:
            Disconnect(self.si)
            self.si = None

    def get_container_view(self, obj_types):
        """Return a container view for the given vSphere object types.

        Args:
            obj_types: List of pyVmomi vim types to include (e.g. [vim.Folder]).
        """
        content = self.si.RetrieveContent()
        return content.viewManager.CreateContainerView(
            content.rootFolder, obj_types, True
        )

    def __enter__(self):
        """Connect when entering a 'with' block."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Disconnect when exiting a 'with' block."""
        self.disconnect()
