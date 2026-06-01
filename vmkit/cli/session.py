from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

if TYPE_CHECKING:
    from core.interfaces import IHypervisorManager, IVMManager

_log = logging.getLogger(__name__)
_T = TypeVar("_T")


def safe_call(session: "SessionState", fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    """Call fn; on connection error reconnect once and retry."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        err_lower = str(e).lower()
        if any(k in err_lower for k in ("not authenticated", "session", "connection", "disconnected")):
            _log.warning("Connection lost, attempting reconnect: %s", e)
            try:
                session.manager.connect()
                return fn(*args, **kwargs)
            except Exception as retry_exc:
                raise retry_exc from e
        raise


@dataclass
class SessionState:
    platform: str = "vsphere"
    host: str = ""
    manager: Optional["IHypervisorManager"] = None
    current_vm: Optional["IVMManager"] = None
    guest_user: Optional[str] = None
    guest_pass: Optional[str] = None
    ssl_verify: bool = False
    debug: bool = False
    output_format: str = "table"    # "table" | "json" | "yaml"
    no_log: bool = False
