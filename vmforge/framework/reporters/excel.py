from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import defusedxml
import defusedxml.ElementTree as defused_ET
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

from .base import Reporter

__all__ = ["ExcelReporter", "TestRecord", "collect_tests", "_parse_duration"]

# ── Styles ────────────────────────────────────────────────────────────────────

_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="E2EFDA")  # light green
_PASS_FONT = Font(bold=True, color="70AD47", italic=True)         # green
_FAIL_FONT = Font(bold=True, color="FF0000", italic=True)         # red
_SKIP_FONT = Font(bold=True, color="FFC000", italic=True)         # amber

_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_VCENTER = Alignment(vertical="center", wrap_text=True)

_HEADERS = ["Product", "Environment", "Test ID", "Full Name", "Status", "Duration (s)", "Failure Message"]
_COL_WIDTHS = [25, 20, 30, 55, 10, 13, 70]

# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class TestRecord:
    product: str
    environment: str
    test_id: str
    full_name: str
    status: str       # "PASS" | "FAIL" | "SKIP"
    duration_s: float
    message: str


# ── XML parsing helpers ───────────────────────────────────────────────────────


def _parse_duration(status_el: ET.Element) -> float:
    """Return elapsed seconds from a <status> element.

    Supports RF7+ (elapsed="1.234" in seconds) and RF5 and earlier
    (starttime/endtime as "YYYYMMDD HH:MM:SS.fff").
    """
    elapsed = status_el.get("elapsed")
    if elapsed is not None:
        try:
            return float(elapsed)
        except ValueError:
            return 0.0
    start = status_el.get("starttime", "")
    end = status_el.get("endtime", "")
    if start and end:
        fmt = "%Y%m%d %H:%M:%S.%f"
        try:
            return (
                datetime.strptime(end, fmt) - datetime.strptime(start, fmt)
            ).total_seconds()
        except ValueError:
            return 0.0
    return 0.0


def collect_tests(root: ET.Element) -> list[TestRecord]:
    """Walk the output.xml element tree and return one TestRecord per <test>."""
    records: list[TestRecord] = []
    for test_el in root.iter("test"):
        full_name = test_el.get("name", "")
        parts = [p.strip() for p in full_name.split("::")]
        product = parts[0]
        env = parts[1] if len(parts) > 1 else ""
        test_id = parts[2] if len(parts) > 2 else full_name

        status_el = test_el.find("status")
        if status_el is None:
            continue
        records.append(
            TestRecord(
                product=product,
                environment=env,
                test_id=test_id,
                full_name=full_name,
                status=status_el.get("status", "FAIL"),
                duration_s=_parse_duration(status_el),
                message=status_el.get("message", ""),
            )
        )
    return records


# ── Reporter ──────────────────────────────────────────────────────────────────


class ExcelReporter(Reporter):
    """Generate a styled Excel workbook from a Robot Framework output.xml."""

    def generate(self, output_xml: Path, output_path: Path) -> None:
        if not output_xml.is_file():
            raise FileNotFoundError(f"output XML not found: {output_xml}")
        try:
            root = defused_ET.parse(output_xml).getroot()
        except (ET.ParseError, defusedxml.common.DefusedXmlException) as exc:
            raise ValueError(
                f"Failed to parse Robot output XML {output_xml}: {exc}"
            ) from exc
        records = collect_tests(root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_workbook(records, output_path)


def _write_workbook(records: list[TestRecord], output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None  # openpyxl always sets active on Workbook() init
    _write_results_sheet(ws, records)
    _write_summary_sheet(wb.create_sheet("Summary"), records)
    wb.save(output_path)


def _write_results_sheet(ws: Worksheet, records: list[TestRecord]) -> None:
    ws.title = "Results"

    hdr_font = Font(bold=True, size=11)
    hdr_align = Alignment(horizontal="center", vertical="center")
    for col, (header, width) in enumerate(
        zip(_HEADERS, _COL_WIDTHS, strict=True), start=1
    ):
        c = ws.cell(row=1, column=col, value=header)
        c.font = hdr_font
        c.fill = _HEADER_FILL
        c.border = _BORDER
        c.alignment = hdr_align
        ws.column_dimensions[c.column_letter].width = width
    ws.row_dimensions[1].height = 20
    ws.freeze_panes = "A2"

    for row, rec in enumerate(records, start=2):
        _wcell(ws, row, 1, rec.product, alignment=_VCENTER)
        _wcell(ws, row, 2, rec.environment, alignment=_VCENTER)
        _wcell(ws, row, 3, rec.test_id, alignment=_VCENTER)
        _wcell(ws, row, 4, rec.full_name, alignment=_VCENTER)

        status_font = (
            _PASS_FONT
            if rec.status == "PASS"
            else _SKIP_FONT
            if rec.status == "SKIP"
            else _FAIL_FONT
        )
        _wcell(ws, row, 5, rec.status, font=status_font, alignment=_CENTER)
        _wcell(ws, row, 6, round(rec.duration_s, 3), alignment=_CENTER)
        _wcell(ws, row, 7, rec.message, alignment=_VCENTER)


def _write_summary_sheet(ws: Worksheet, records: list[TestRecord]) -> None:
    ws.title = "Summary"
    passed = sum(1 for r in records if r.status == "PASS")
    failed = sum(1 for r in records if r.status == "FAIL")
    skipped = sum(1 for r in records if r.status == "SKIP")
    total = len(records)

    summary_rows = [
        ("Total", total),
        ("Passed", passed),
        ("Failed", failed),
        ("Skipped", skipped),
        ("Pass rate", f"{passed / total * 100:.1f}%" if total else "N/A"),
    ]
    hdr_font = Font(bold=True, size=11)
    for r, (label, value) in enumerate(summary_rows, start=1):
        c_label = ws.cell(row=r, column=1, value=label)
        c_label.font = hdr_font
        c_label.border = _BORDER
        c_label.fill = _HEADER_FILL
        c_value = ws.cell(row=r, column=2, value=value)
        c_value.border = _BORDER
        if label == "Passed":
            c_value.font = _PASS_FONT
        elif label == "Failed":
            c_value.font = _FAIL_FONT
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 10


def _wcell(
    ws: Worksheet,
    row: int,
    col: int,
    value: object,
    *,
    font: Font | None = None,
    alignment: Alignment | None = None,
) -> None:
    c = ws.cell(row=row, column=col, value=value)
    c.border = _BORDER
    if font is not None:
        c.font = font
    if alignment is not None:
        c.alignment = alignment
