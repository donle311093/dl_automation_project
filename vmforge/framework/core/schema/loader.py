import json
import logging
from pathlib import Path

from pydantic import ValidationError

from .models import ProductConfig

logger = logging.getLogger(__name__)


class ConfigLoadError(Exception):
    """Raised when a VMForge config file cannot be loaded or validated."""


def load(path: str | Path) -> ProductConfig:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigLoadError(f"Config file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(f"Malformed JSON in {p}: {exc}") from exc
    try:
        return ProductConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"Schema validation failed for {p}:\n{exc}") from exc


def load_all(directory: str | Path) -> list[ProductConfig]:
    d = Path(directory)
    if not d.exists():
        raise ConfigLoadError(f"Config directory not found: {d}")
    configs = [load(p) for p in sorted(d.glob("*.json"))]
    if not configs:
        logger.warning("No JSON config files found in %s", d)
    return configs
