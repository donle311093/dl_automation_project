from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import Reporter

__all__ = ["JUnitReporter"]


class JUnitReporter(Reporter):
    """Produce JUnit XML from a Robot Framework output.xml using rebot --xunit.

    Robot Framework natively produces JUnit-compatible XML. This reporter is a
    thin wrapper so the CLI can call it uniformly alongside ExcelReporter.
    """

    def generate(self, output_xml: Path, output_path: Path) -> None:
        if not output_xml.is_file():
            raise FileNotFoundError(f"output XML not found: {output_xml}")
        rebot = shutil.which("rebot")
        if rebot is None:
            raise FileNotFoundError("rebot not found on PATH; install robotframework")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                rebot,
                "--xunit", str(output_path),
                "--output", "NONE",
                "--log", "NONE",
                "--report", "NONE",
                str(output_xml),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, rebot, output=result.stdout, stderr=result.stderr
            )
