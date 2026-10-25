"""Tests for report formatters."""

import json
import pytest
from modpack_doctor.formatters import (
    BaseFormatter,
    JsonFormatter,
    MarkdownFormatter,
    PlainTerminalFormatter,
    RichTerminalFormatter,
    get_formatter,
)
from modpack_doctor.models import (
    DiagnosisReport,
    DiagnosticIssue,
    Environment,
    IssueCode,
    IssueSeverity,
    LoaderType,
    ModInfo,
)


def sample_report(healthy: bool = False) -> DiagnosisReport:
    mod1 = ModInfo(
        id="mod_a",
        name="Mod A",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="/mods/mod_a.jar",
        file_name="mod_a.jar",
        environment=Environment.UNIVERSAL,
    )
    issues = []
    if not healthy:
        issues = [
            DiagnosticIssue(
                code=IssueCode.MISSING_DEPENDENCY,
                severity=IssueSeverity.CRITICAL,
                message="Missing mod_b",
                mod_id="mod_a",
                related_mod_id="mod_b",
                file_path="/mods/mod_a.jar",
                recommendation="Install mod_b",
            ),
            DiagnosticIssue(
                code=IssueCode.DUPLICATE_MOD,
                severity=IssueSeverity.WARNING,
                message="Duplicate mod",
                mod_id="mod_a",
            ),
            DiagnosticIssue(
                code=IssueCode.MISSING_DEPENDENCY,
                severity=IssueSeverity.INFO,
                message="Optional mod recommended",
                mod_id="mod_a",
            ),
        ]
    return DiagnosisReport(
        scanned_path="/test/mods",
        target_env="both",
        minecraft_version="1.20.1",
        mods=[mod1],
        issues=issues,
        scan_duration_ms=12.3,
    )


def sample_diffs():
    return [
        {"mod_id": "mod_a", "status": "added", "new_version": "1.0.0", "new_file": "mod_a.jar"},
        {"mod_id": "mod_b", "status": "removed", "old_version": "2.0.0", "old_file": "mod_b.jar"},
        {"mod_id": "mod_c", "status": "changed", "old_version": "1.0.0", "new_version": "1.1.0"},
        {"mod_id": "mod_d", "status": "unchanged", "old_version": "3.0.0", "new_version": "3.0.0"},
    ]


def test_base_formatter():
    base = BaseFormatter()
    with pytest.raises(NotImplementedError):
        base.format_report(sample_report())
    with pytest.raises(NotImplementedError):
        base.format_diff([])


def test_rich_formatter():
    fmt = RichTerminalFormatter(color=False, verbose=True)
    report_out = fmt.format_report(sample_report(healthy=False))
    assert "MODPACK DOCTOR DIAGNOSTIC REPORT" in report_out
    assert "CRITICAL ISSUES DETECTED" in report_out
    assert "Missing mod_b" in report_out

    # Healthy report
    healthy_out = fmt.format_report(sample_report(healthy=True))
    assert "PASSED: MODPACK HEALTHY" in healthy_out

    # Diff
    diff_out = fmt.format_diff(sample_diffs())
    assert "Modpack Differences" in diff_out
    assert "mod_a" in diff_out


def test_plain_formatter():
    fmt = PlainTerminalFormatter()
    out = fmt.format_report(sample_report(healthy=False))
    assert "CRITICAL ISSUES FOUND" in out
    assert "Missing mod_b" in out

    out_healthy = fmt.format_report(sample_report(healthy=True))
    assert "No issues found" in out_healthy

    diff_out = fmt.format_diff(sample_diffs())
    assert "MODPACK COMPARISON (DIFF)" in diff_out
    assert "ADDED" in diff_out


def test_json_formatter():
    fmt = JsonFormatter()
    out = fmt.format_report(sample_report(healthy=False))
    parsed = json.loads(out)
    assert parsed["scanned_path"] == "/test/mods"
    assert parsed["summary"]["critical_issues"] == 1
    assert parsed["summary"]["warning_issues"] == 1
    assert parsed["summary"]["info_issues"] == 1

    diff_out = fmt.format_diff(sample_diffs())
    parsed_diff = json.loads(diff_out)
    assert parsed_diff["total_changes"] == 3


def test_markdown_formatter():
    fmt = MarkdownFormatter()
    out_err = fmt.format_report(sample_report(healthy=False))
    assert "# 🩺 Modpack Doctor Diagnostic Report" in out_err
    assert "Discovered **1** critical errors" in out_err
    assert "MISSING_DEPENDENCY" in out_err

    out_ok = fmt.format_report(sample_report(healthy=True))
    assert "All checks passed!" in out_ok

    diff_out = fmt.format_diff(sample_diffs())
    assert "# 🔄 Modpack Diff Comparison" in diff_out
    assert "mod_a" in diff_out


def test_get_formatter_factory():
    assert isinstance(get_formatter("json"), JsonFormatter)
    assert isinstance(get_formatter("markdown"), MarkdownFormatter)
    assert isinstance(get_formatter("md"), MarkdownFormatter)
    assert isinstance(get_formatter("plain"), PlainTerminalFormatter)
    assert isinstance(get_formatter("rich", color=False), PlainTerminalFormatter)
    assert isinstance(get_formatter("rich", color=True), RichTerminalFormatter)
