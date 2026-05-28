from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from framework.reporters.base import Reporter
from framework.reporters.excel import (
    ExcelReporter,
    TestRecord,
    _parse_duration,
    collect_tests,
)
from framework.reporters.junit import JUnitReporter

# ── Shared XML fixtures ───────────────────────────────────────────────────────

# Minimal RF7 output.xml — only the attributes accessed by collect_tests/
# _parse_duration are present; real RF7 output also carries source, rpa,
# line, and generator attributes that are intentionally omitted here.
_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.0">
  <suite id="s1" name="Suite">
    <test id="s1-t1" name="7zip-x86 :: win10-x86 :: download-latest">
      <status status="PASS" elapsed="90.5"/>
    </test>
    <test id="s1-t2" name="7zip-x86 :: win10-x86 :: install-patch">
      <status status="FAIL" elapsed="45.2" message="result.code: got 1, expected 1005"/>
    </test>
    <test id="s1-t3" name="1password :: win11 :: check-defunct">
      <status status="PASS" elapsed="12.0"/>
    </test>
  </suite>
  <statistics/><errors/>
</robot>"""

_LEGACY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot>
  <suite id="s1" name="Suite">
    <test id="s1-t1" name="pkg :: env :: test1">
      <status status="PASS"
              starttime="20240101 10:00:00.000"
              endtime="20240101 10:01:30.500"/>
    </test>
  </suite>
  <statistics/><errors/>
</robot>"""

_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.0">
  <suite id="s1" name="Suite"/>
  <statistics/><errors/>
</robot>"""


@pytest.fixture
def sample_xml(tmp_path: Path) -> Path:
    p = tmp_path / "output.xml"
    p.write_text(_SAMPLE_XML, encoding="utf-8")
    return p


@pytest.fixture
def legacy_xml(tmp_path: Path) -> Path:
    p = tmp_path / "output.xml"
    p.write_text(_LEGACY_XML, encoding="utf-8")
    return p


@pytest.fixture
def empty_xml(tmp_path: Path) -> Path:
    p = tmp_path / "output.xml"
    p.write_text(_EMPTY_XML, encoding="utf-8")
    return p


def _parse(xml_str: str) -> ET.Element:
    return ET.fromstring(xml_str)


# ── TestParseDuration ─────────────────────────────────────────────────────────


class TestParseDuration:
    def test_rf7_elapsed_seconds(self) -> None:
        el = ET.fromstring('<status status="PASS" elapsed="1.5"/>')
        assert _parse_duration(el) == pytest.approx(1.5)

    def test_rf7_elapsed_zero(self) -> None:
        el = ET.fromstring('<status status="PASS" elapsed="0.0"/>')
        assert _parse_duration(el) == pytest.approx(0.0)

    def test_legacy_starttime_endtime(self) -> None:
        el = ET.fromstring(
            '<status status="PASS" starttime="20240101 10:00:00.000" endtime="20240101 10:01:30.500"/>',
        )
        assert _parse_duration(el) == pytest.approx(90.5)

    def test_missing_timing_returns_zero(self) -> None:
        el = ET.fromstring('<status status="PASS"/>')
        assert _parse_duration(el) == 0.0

    def test_invalid_elapsed_returns_zero(self) -> None:
        el = ET.fromstring('<status status="PASS" elapsed="not-a-number"/>')
        assert _parse_duration(el) == 0.0

    def test_invalid_starttime_returns_zero(self) -> None:
        el = ET.fromstring(
            '<status status="PASS" starttime="bad" endtime="also-bad"/>',
        )
        assert _parse_duration(el) == 0.0


# ── TestCollectTests ──────────────────────────────────────────────────────────


class TestCollectTests:
    def _records(self, xml_str: str) -> list[TestRecord]:
        return collect_tests(ET.fromstring(xml_str))

    def test_count(self) -> None:
        assert len(self._records(_SAMPLE_XML)) == 3

    def test_parses_product_env_testid(self) -> None:
        rec = self._records(_SAMPLE_XML)[0]
        assert rec.product == "7zip-x86"
        assert rec.environment == "win10-x86"
        assert rec.test_id == "download-latest"

    def test_full_name_preserved(self) -> None:
        rec = self._records(_SAMPLE_XML)[0]
        assert rec.full_name == "7zip-x86 :: win10-x86 :: download-latest"

    def test_pass_status(self) -> None:
        assert self._records(_SAMPLE_XML)[0].status == "PASS"

    def test_fail_status_with_message(self) -> None:
        rec = self._records(_SAMPLE_XML)[1]
        assert rec.status == "FAIL"
        assert "result.code" in rec.message

    def test_duration_rf7(self) -> None:
        assert self._records(_SAMPLE_XML)[0].duration_s == pytest.approx(90.5)

    def test_duration_legacy(self, legacy_xml: Path) -> None:
        records = collect_tests(ET.parse(legacy_xml).getroot())
        assert records[0].duration_s == pytest.approx(90.5)

    def test_name_with_fewer_parts(self) -> None:
        xml = """<robot><suite id="s1" name="S">
  <test id="s1-t1" name="only-one-part">
    <status status="PASS" elapsed="1.0"/>
  </test>
</suite><statistics/><errors/></robot>"""
        rec = self._records(xml)[0]
        assert rec.product == "only-one-part"
        assert rec.environment == ""
        assert rec.test_id == "only-one-part"

    def test_skips_test_without_status_element(self) -> None:
        xml = """<robot><suite id="s1" name="S">
  <test id="s1-t1" name="no-status"/>
</suite><statistics/><errors/></robot>"""
        assert self._records(xml) == []


# ── TestExcelReporter ─────────────────────────────────────────────────────────


class TestExcelReporter:
    def _generate(self, sample_xml: Path, tmp_path: Path) -> openpyxl.Workbook:
        out = tmp_path / "result.xlsx"
        ExcelReporter().generate(sample_xml, out)
        return openpyxl.load_workbook(out)

    def test_creates_output_file(self, sample_xml: Path, tmp_path: Path) -> None:
        out = tmp_path / "result.xlsx"
        ExcelReporter().generate(sample_xml, out)
        assert out.exists()

    def test_creates_output_dir_if_missing(self, sample_xml: Path, tmp_path: Path) -> None:
        out = tmp_path / "new" / "dir" / "result.xlsx"
        ExcelReporter().generate(sample_xml, out)
        assert out.exists()

    def test_results_sheet_exists(self, sample_xml: Path, tmp_path: Path) -> None:
        wb = self._generate(sample_xml, tmp_path)
        assert "Results" in wb.sheetnames

    def test_summary_sheet_exists(self, sample_xml: Path, tmp_path: Path) -> None:
        wb = self._generate(sample_xml, tmp_path)
        assert "Summary" in wb.sheetnames

    def test_header_row_values(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Results"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, 8)]
        assert headers[0] == "Product"
        assert headers[4] == "Status"
        assert headers[6] == "Failure Message"

    def test_data_rows_count(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Results"]
        assert ws.max_row == 4  # 1 header + 3 data rows

    def test_pass_row_written(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Results"]
        assert ws.cell(row=2, column=1).value == "7zip-x86"
        assert ws.cell(row=2, column=5).value == "PASS"

    def test_fail_row_has_message(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Results"]
        assert ws.cell(row=3, column=5).value == "FAIL"
        assert "result.code" in (ws.cell(row=3, column=7).value or "")

    def test_duration_written(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Results"]
        assert ws.cell(row=2, column=6).value == pytest.approx(90.5)

    def test_summary_totals(self, sample_xml: Path, tmp_path: Path) -> None:
        ws = self._generate(sample_xml, tmp_path)["Summary"]
        assert ws.cell(row=1, column=2).value == 3   # Total
        assert ws.cell(row=2, column=2).value == 2   # Passed
        assert ws.cell(row=3, column=2).value == 1   # Failed

    def test_empty_xml_produces_workbook(self, empty_xml: Path, tmp_path: Path) -> None:
        out = tmp_path / "result.xlsx"
        ExcelReporter().generate(empty_xml, out)
        wb = openpyxl.load_workbook(out)
        assert wb["Summary"].cell(row=5, column=2).value == "N/A"
        assert wb["Results"].max_row == 1  # header row only

    def test_malformed_xml_raises_value_error(self, tmp_path: Path) -> None:
        xml = tmp_path / "bad.xml"
        xml.write_text("not valid xml <<<", encoding="utf-8")
        out = tmp_path / "result.xlsx"
        with pytest.raises(ValueError, match="Failed to parse"):
            ExcelReporter().generate(xml, out)

    def test_is_reporter_subclass(self) -> None:
        assert issubclass(ExcelReporter, Reporter)


# ── TestJUnitReporter ─────────────────────────────────────────────────────────


class TestJUnitReporter:
    def test_calls_rebot_with_correct_args(self, tmp_path: Path) -> None:
        xml = tmp_path / "output.xml"
        xml.write_text("<robot/>")
        out = tmp_path / "junit.xml"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result) as mock_run,
        ):
            JUnitReporter().generate(xml, out)
        mock_run.assert_called_once_with(
            [
                "/usr/bin/rebot",
                "--xunit", str(out),
                "--output", "NONE",
                "--log", "NONE",
                "--report", "NONE",
                str(xml),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        xml = tmp_path / "output.xml"
        xml.write_text("<robot/>")
        out = tmp_path / "new" / "junit.xml"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result),
        ):
            JUnitReporter().generate(xml, out)
        assert out.parent.is_dir()

    def test_raises_on_rebot_failure(self, tmp_path: Path) -> None:
        xml = tmp_path / "output.xml"
        xml.write_text("<robot/>")
        out = tmp_path / "junit.xml"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "rebot error"
        with (
            patch("framework.reporters.junit.shutil.which", return_value="/usr/bin/rebot"),
            patch("framework.reporters.junit.subprocess.run", return_value=mock_result),
            pytest.raises(subprocess.CalledProcessError),
        ):
            JUnitReporter().generate(xml, out)

    def test_raises_when_rebot_not_found(self, tmp_path: Path) -> None:
        xml = tmp_path / "output.xml"
        xml.write_text("<robot/>")
        out = tmp_path / "junit.xml"
        with (
            patch("framework.reporters.junit.shutil.which", return_value=None),
            pytest.raises(FileNotFoundError, match="rebot not found"),
        ):
            JUnitReporter().generate(xml, out)

    def test_raises_when_output_xml_missing(self, tmp_path: Path) -> None:
        xml = tmp_path / "does_not_exist.xml"
        out = tmp_path / "junit.xml"
        with pytest.raises(FileNotFoundError, match="output XML not found"):
            JUnitReporter().generate(xml, out)

    def test_is_reporter_subclass(self) -> None:
        assert issubclass(JUnitReporter, Reporter)
