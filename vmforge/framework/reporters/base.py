from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

__all__ = ["Reporter"]


class Reporter(ABC):
    @abstractmethod
    def generate(self, output_xml: Path, output_path: Path) -> None:
        """Generate a report from a Robot Framework output.xml file."""
