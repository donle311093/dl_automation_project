"""HypervisorFactory — Factory Pattern for creating IHypervisorManager instances.

Design Pattern: Factory
- Centralises the creation logic for all supported hypervisor platforms.
- Callers need only supply a platform name and a configuration dict.
- Adding a new platform requires only registering it here — existing code is unchanged.

Supported platforms:
    "vsphere"  — VMware vSphere / vCenter
    "proxmox"  — Proxmox VE
    "fusion"   — VMware Fusion Pro (Mac)
    "docker"   — Docker (treated as a hypervisor with containers as VMs)
    "ssh"      — Direct SSH access (no real hypervisor)

Usage:
    # Create a vSphere manager
    mgr = HypervisorFactory.create("vsphere")

    # Create a Proxmox manager
    mgr = HypervisorFactory.create("proxmox", {
        "host": "10.0.0.1",
        "user": "root@pam",
        "password": "secret",
        "port": 8006,
        "verify_ssl": False,
    })

    # Use the manager
    with mgr as m:
        vm = m.get_vm("my-vm")
        print(vm.get_power_status())
"""

from core.interfaces import IHypervisorManager


class HypervisorFactory:
    """Factory for creating IHypervisorManager concrete instances.

    Design Pattern: Factory Method / Static Factory
    """

    # Registry maps platform name → (module_path, class_name, required_keys)
    _REGISTRY = {
        "vsphere": {
            "module": "vsphere.vsphere_manager",
            "class": "VSphereManager",
            "required_keys": [],
            "optional_keys": ["config_path"],
        },
        "proxmox": {
            "module": "proxmox_impl.proxmox_manager",
            "class": "ProxmoxManager",
            "required_keys": ["host", "user", "password"],
            "optional_keys": ["port", "verify_ssl"],
        },
        "fusion": {
            "module": "fusion_impl.fusion_manager",
            "class": "FusionManager",
            "required_keys": ["host"],
            "optional_keys": ["port", "username", "password", "verify_ssl"],
        },
    }

    @staticmethod
    def create(platform: str, config: dict = None) -> IHypervisorManager:
        """Create and return an IHypervisorManager for the given platform.

        Args:
            platform: One of "vsphere", "proxmox".
            config:   Platform-specific configuration dict. See module docstring.

        Returns:
            An IHypervisorManager instance (not yet connected).

        Raises:
            ValueError: If platform is unsupported or required config keys are missing.
        """
        platform = platform.lower()
        config = config or {}

        if platform not in HypervisorFactory._REGISTRY:
            supported = ", ".join(sorted(HypervisorFactory._REGISTRY))
            raise ValueError(
                f"Unsupported platform '{platform}'. "
                f"Supported platforms: {supported}"
            )

        meta = HypervisorFactory._REGISTRY[platform]

        # Validate required config keys
        missing = [k for k in meta["required_keys"] if k not in config]
        if missing:
            raise ValueError(
                f"Missing required config keys for '{platform}': {missing}"
            )

        # Lazy import the concrete class
        import importlib
        module = importlib.import_module(meta["module"])
        cls = getattr(module, meta["class"])

        return HypervisorFactory._instantiate(platform, cls, config)

    @staticmethod
    def _instantiate(platform: str, cls, config: dict) -> IHypervisorManager:
        """Instantiate the manager with platform-specific arguments."""
        if platform == "vsphere":
            return cls(
                config_path=config.get("config_path"),
                host=config.get("host"),
                user=config.get("user"),
                password=config.get("password"),
                port=config.get("port", 443),
                ssl_verify=config.get("ssl_verify", False),
            )

        if platform == "proxmox":
            return cls(
                host=config["host"],
                user=config["user"],
                password=config["password"],
                port=config.get("port", 8006),
                verify_ssl=config.get("verify_ssl", False),
            )

        if platform == "fusion":
            return cls(
                host=config["host"],
                port=config.get("port", 8697),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", False),
            )

        raise ValueError(f"No instantiation logic for platform '{platform}'.")

    @staticmethod
    def supported_platforms() -> list:
        """Return a list of supported platform names."""
        return sorted(HypervisorFactory._REGISTRY.keys())
