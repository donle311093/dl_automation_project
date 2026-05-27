import json
from pathlib import Path
from .models import ProductConfig


def load(path: str | Path) -> ProductConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProductConfig.model_validate(data)


def load_all(directory: str | Path) -> list[ProductConfig]:
    return [load(p) for p in sorted(Path(directory).glob("*.json"))]
