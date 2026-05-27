import configparser
import getpass
import os
from pathlib import Path

from cli.session import SessionState
from core.factory import HypervisorFactory

_LOCAL_CONFIG = os.path.join(os.path.dirname(__file__), "..", "vsphere", ".config")


def _load_ini_config(path) -> dict:
    cfg = configparser.ConfigParser()
    read = cfg.read(path)
    if not read:
        raise FileNotFoundError(f"Config file not found: {os.path.abspath(path)}")
    if "vcenter" not in cfg:
        raise ValueError(f"Config file missing [vcenter] section: {os.path.abspath(path)}")
    vc = cfg["vcenter"]
    result = {
        "host": vc.get("host", ""),
        "user": vc.get("user", ""),
        "password": vc.get("password", ""),
        "port": int(vc.get("port", 443)),
        "ssl_verify": vc.get("ssl_verify", "false").lower() == "true",
    }
    return result


def _prompt_credentials() -> dict:
    print("No credentials found. Please enter vCenter connection details.")
    host = input("Host: ").strip()
    user = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    port_str = input("Port [443]: ").strip()
    port = int(port_str) if port_str else 443
    no_ssl = input("Skip SSL verification? [Y/n]: ").strip().lower()
    ssl_verify = no_ssl == "n"

    save = input("Save to local config? [y/N]: ").strip().lower()
    if save == "y":
        cfg = configparser.ConfigParser()
        cfg["vcenter"] = {
            "host": host,
            "user": user,
            "port": str(port),
        }
        config_path = os.path.abspath(_LOCAL_CONFIG)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            cfg.write(f)
        os.chmod(config_path, 0o600)
        print(f"Saved to {config_path} (password not saved — will be prompted on next login)")

    return {"host": host, "user": user, "password": password, "port": port, "ssl_verify": ssl_verify}


def auth(args) -> SessionState:
    """Resolve credentials and return a connected SessionState.

    Priority:
    1. Env vars (VSPHERE_HOST / VSPHERE_USER / VSPHERE_PASS)
    2. --profile arg or VMK_PROFILE env var → ~/.vmkit/profiles/<name>.config
    3. Local config file: vsphere/.config
    4. Interactive prompt
    """
    config = {}
    platform = getattr(args, "platform", "vsphere") or "vsphere"

    # 1. Environment variables
    env_host = os.environ.get("VSPHERE_HOST")
    env_user = os.environ.get("VSPHERE_USER")
    env_pass = os.environ.get("VSPHERE_PASS")
    if env_host and env_user and env_pass:
        config = {
            "host": env_host,
            "user": env_user,
            "password": env_pass,
            "port": int(os.environ.get("VSPHERE_PORT", 443)),
            "ssl_verify": os.environ.get("VSPHERE_NO_SSL_VERIFY", "") != "1",
        }

    # 2. Profile
    if not config:
        profile_name = getattr(args, "profile", None) or os.environ.get("VMK_PROFILE")
        if profile_name:
            profile_path = Path.home() / ".vmkit" / "profiles" / f"{profile_name}.config"
            config = _load_ini_config(str(profile_path))

    # 3. Local config file
    if not config:
        local_cfg = os.path.abspath(_LOCAL_CONFIG)
        if os.path.exists(local_cfg):
            config = _load_ini_config(local_cfg)

    # 4. Interactive prompt
    if not config:
        config = _prompt_credentials()

    ssl_verify = config.get("ssl_verify", False)
    if getattr(args, "no_verify_ssl", False):
        ssl_verify = False
        config["ssl_verify"] = False
    debug = getattr(args, "debug", False)
    output_format = getattr(args, "output", "table") or "table"
    no_log = getattr(args, "no_log", False)

    manager = HypervisorFactory.create(platform, config)
    manager.connect()

    session = SessionState(
        platform=platform,
        host=config.get("host", ""),
        manager=manager,
        ssl_verify=ssl_verify,
        debug=debug,
        output_format=output_format,
        no_log=no_log,
    )
    return session
