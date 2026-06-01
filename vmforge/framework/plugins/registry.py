from functools import lru_cache
from typing import Any

from .base import ExecutorPlugin, PlatformPlugin


@lru_cache(maxsize=None)
def _platform_registry() -> dict[str, type[PlatformPlugin]]:
    from .platforms.ssh_direct import SshDirectPlatform
    from .platforms.vsphere import VspherePlatform

    return {
        "vsphere": VspherePlatform,
        "ssh_direct": SshDirectPlatform,
    }


@lru_cache(maxsize=None)
def _executor_registry() -> dict[str, type[ExecutorPlugin]]:
    from .executors.powershell import PowershellExecutor
    from .executors.ssh import SshExecutor

    return {
        "powershell": PowershellExecutor,
        "ssh": SshExecutor,
    }


def get_platform(name: str, **kwargs: Any) -> PlatformPlugin:
    cls = _platform_registry().get(name)
    if cls is None:
        raise KeyError(f"Unknown platform {name!r}. Available: {list(_platform_registry())}")
    return cls(**kwargs)


def get_executor(name: str, **kwargs: Any) -> ExecutorPlugin:
    cls = _executor_registry().get(name)
    if cls is None:
        raise KeyError(f"Unknown executor {name!r}. Available: {list(_executor_registry())}")
    return cls(**kwargs)
