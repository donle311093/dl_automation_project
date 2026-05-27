from __future__ import annotations

from ...core.schema.models import AssertItem
from .suite_builder import RobotSuite, RobotTestCase

__all__ = ["render_suite", "suite_filename"]

_INDENT = "    "

_EXEC_KEYWORD: dict[str, str] = {
    "powershell": "Execute PS",
    "ssh": "Execute SSH",
}


def suite_filename(suite: RobotSuite) -> str:
    """Suggested output filename: <product_id>__<env_id>.robot"""
    return f"{suite.product_id}__{suite.env_id}.robot"


def _exec_kw(executor: str) -> str:
    return _EXEC_KEYWORD.get(executor, "Execute Command")


def _last_capture(step_lines: list[tuple[str | None, str]]) -> str | None:
    for capture_var, _ in reversed(step_lines):
        if capture_var is not None:
            return capture_var
    return None


def _render_assert(item: AssertItem, capture_var: str) -> str:
    expected = f"={item.equals_field}" if item.equals_field is not None else str(item.equals)
    return f"{_INDENT}Check Field    ${{{capture_var}}}    {item.path}    {expected}"


def _render_test_case(tc: RobotTestCase, exec_kw: str, snapshot: str) -> list[str]:
    lines: list[str] = [tc.name]
    lines.append(f"{_INDENT}[Tags]    {'    '.join(tc.tags)}")
    lines.append(f"{_INDENT}[Setup]    Revert Snapshot    {snapshot}")

    for cmd in tc.setup_cmds:
        lines.append(f"{_INDENT}{exec_kw}    {cmd}")

    for capture_var, cmd in tc.step_lines:
        if capture_var is not None:
            lines.append(f"{_INDENT}${{{capture_var}}}=    {exec_kw}    {cmd}")
        else:
            lines.append(f"{_INDENT}{exec_kw}    {cmd}")

    capture_var = _last_capture(tc.step_lines)
    if tc.assert_items:
        if capture_var is None:
            raise ValueError(
                f"Test case {tc.name!r} has {len(tc.assert_items)} assertion(s) but no step uses capture_as"
            )
        for item in tc.assert_items:
            lines.append(_render_assert(item, capture_var))

    if len(tc.teardown_cmds) == 1:
        lines.append(f"{_INDENT}[Teardown]    {exec_kw}    {tc.teardown_cmds[0]}")
    elif tc.teardown_cmds:
        kw_calls = "    AND    ".join(f"{exec_kw}    {cmd}" for cmd in tc.teardown_cmds)
        lines.append(f"{_INDENT}[Teardown]    Run Keywords    {kw_calls}")

    return lines


def render_suite(suite: RobotSuite) -> str:
    """Return the complete .robot file text for one product x environment suite."""
    exec_kw = _exec_kw(suite.executor)
    lines: list[str] = []

    lines.append("*** Settings ***")
    lines.append(
        f"Library    vmforge.framework.robot.keywords.VmForgeKeywords"
        f"    platform={suite.platform}    executor={suite.executor}"
    )
    lines.append(f"Suite Setup       Clone VM    {suite.template}    {suite.snapshot}")
    lines.append("Suite Teardown    Teardown VM")
    lines.append("")

    lines.append("*** Test Cases ***")
    for i, tc in enumerate(suite.test_cases):
        if i > 0:
            lines.append("")
        lines.extend(_render_test_case(tc, exec_kw, suite.snapshot))

    lines.append("")
    return "\n".join(lines)
