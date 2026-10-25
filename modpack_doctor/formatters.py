"""Diagnostic report formatters: Rich Terminal, Plain Text, JSON, and Markdown."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from modpack_doctor.models import (
    DiagnosisReport,
    DiagnosticIssue,
    IssueSeverity,
    ModInfo,
)


class BaseFormatter:
    """Base interface for report formatters."""

    def format_report(self, report: DiagnosisReport) -> str:
        raise NotImplementedError

    def format_diff(self, diffs: List[Dict[str, Any]]) -> str:
        raise NotImplementedError


class RichTerminalFormatter(BaseFormatter):
    """Outputs high-fidelity, colored terminal reports using Rich."""

    def __init__(self, color: bool = True, verbose: bool = False) -> None:
        self.color = color
        self.verbose = verbose

    def format_report(self, report: DiagnosisReport) -> str:
        """Format DiagnosisReport as rich terminal text."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=self.color, color_system="auto" if self.color else None, width=100)

        # 1. Header Banner
        is_healthy = not report.has_errors()
        status_color = "bold green" if is_healthy else "bold red"
        status_text = "PASSED: MODPACK HEALTHY" if is_healthy else f"FAILED: {report.critical_count} CRITICAL ISSUES DETECTED"

        banner_text = Text()
        banner_text.append(f"  {status_text}\n", style=status_color)
        banner_text.append(f"  Scanned: {report.scanned_path}\n", style="dim")
        banner_text.append(f"  Target: {report.target_env.upper()} | MC Version: {report.minecraft_version or 'Any'}\n", style="dim")
        banner_text.append(f"  Mods Analyzed: {len(report.mods)} | Time: {report.scan_duration_ms:.1f}ms", style="dim")

        console.print(Panel(banner_text, title="[bold cyan]MODPACK DOCTOR DIAGNOSTIC REPORT[/bold cyan]", border_style="cyan"))

        # 2. Mod Inventory Summary Table
        if self.verbose and report.mods:
            table = Table(title="Scanned Mod Inventory", header_style="bold magenta", border_style="dim")
            table.add_column("Mod ID", style="bold cyan")
            table.add_column("Name")
            table.add_column("Version", style="green")
            table.add_column("Loader", style="yellow")
            table.add_column("Side", style="blue")
            table.add_column("File")

            for mod in sorted(report.mods, key=lambda m: m.id):
                table.add_row(
                    mod.id,
                    mod.name[:30],
                    mod.version,
                    mod.loader.value,
                    mod.environment.value,
                    mod.file_name,
                )
            console.print(table)
            console.print()

        # 3. Diagnostic Issues Section
        if report.issues:
            issues_table = Table(title="Diagnostic Findings", header_style="bold", border_style="dim")
            issues_table.add_column("Sev", justify="center", width=8)
            issues_table.add_column("Code", style="bold", width=22)
            issues_table.add_column("Mod ID", style="cyan", width=16)
            issues_table.add_column("Description & Recommendation", style="white")

            for issue in report.issues:
                if issue.severity == IssueSeverity.CRITICAL:
                    sev_style = "bold white on red"
                    sev_label = "CRIT"
                elif issue.severity == IssueSeverity.WARNING:
                    sev_style = "bold black on yellow"
                    sev_label = "WARN"
                else:
                    sev_style = "bold white on blue"
                    sev_label = "INFO"

                desc_text = Text()
                desc_text.append(f"{issue.message}\n")
                if issue.recommendation:
                    desc_text.append(f"  -> Fix: {issue.recommendation}", style="dim green")
                if issue.file_path:
                    desc_text.append(f"\n  -> In: {issue.file_path}", style="dim")

                issues_table.add_row(
                    Text(sev_label, style=sev_style),
                    issue.code.value,
                    issue.mod_id or "-",
                    desc_text,
                )

            console.print(issues_table)
            console.print()
        else:
            console.print("[bold green]✔ No issues, conflicts, or missing dependencies found![/bold green]\n")

        # 4. Summary counts
        console.print(
            f"[bold]Summary:[/bold] {len(report.mods)} mods, "
            f"[red]{report.critical_count} critical[/red], "
            f"[yellow]{report.warning_count} warnings[/yellow], "
            f"[blue]{report.info_count} info[/blue]"
        )

        return buf.getvalue()

    def format_diff(self, diffs: List[Dict[str, Any]]) -> str:
        """Format modpack diff table."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=self.color, color_system="auto" if self.color else None, width=100)

        table = Table(title="Modpack Differences", header_style="bold magenta")
        table.add_column("Status", width=12)
        table.add_column("Mod ID", style="bold cyan")
        table.add_column("Old Version", style="yellow")
        table.add_column("New Version", style="green")
        table.add_column("Details", style="dim")

        for d in diffs:
            status = d["status"]
            if status == "added":
                status_text = Text("+ ADDED", style="bold green")
            elif status == "removed":
                status_text = Text("- REMOVED", style="bold red")
            elif status == "changed":
                status_text = Text("~ CHANGED", style="bold yellow")
            else:
                status_text = Text("  SAME", style="dim")

            table.add_row(
                status_text,
                d["mod_id"],
                d.get("old_version") or "-",
                d.get("new_version") or "-",
                d.get("new_file") or d.get("old_file") or "",
            )

        console.print(table)
        return buf.getvalue()


class PlainTerminalFormatter(BaseFormatter):
    """Outputs plain text without ANSI escape sequences."""

    def format_report(self, report: DiagnosisReport) -> str:
        lines: List[str] = [
            "=" * 70,
            "MODPACK DOCTOR DIAGNOSTIC REPORT",
            "=" * 70,
            f"Path:            {report.scanned_path}",
            f"Target Env:      {report.target_env.upper()}",
            f"Minecraft Ver:   {report.minecraft_version or 'Any'}",
            f"Total Mods:      {len(report.mods)}",
            f"Scan Time:       {report.scan_duration_ms:.1f}ms",
            f"Status:          {'HEALTHY' if not report.has_errors() else 'CRITICAL ISSUES FOUND'}",
            "-" * 70,
        ]

        if not report.issues:
            lines.append("No issues found. Modpack is healthy.")
        else:
            lines.append("ISSUES FOUND:")
            for idx, issue in enumerate(report.issues, 1):
                lines.append(f"[{issue.severity.value}] #{idx} {issue.code.value} - Mod: {issue.mod_id or 'General'}")
                lines.append(f"  Message: {issue.message}")
                if issue.recommendation:
                    lines.append(f"  Action:  {issue.recommendation}")
                if issue.file_path:
                    lines.append(f"  File:    {issue.file_path}")
                lines.append("")

        lines.extend([
            "-" * 70,
            f"Summary: {len(report.mods)} mods | {report.critical_count} critical | {report.warning_count} warnings | {report.info_count} info",
            "=" * 70,
        ])
        return "\n".join(lines)

    def format_diff(self, diffs: List[Dict[str, Any]]) -> str:
        lines = [
            "=" * 70,
            "MODPACK COMPARISON (DIFF)",
            "=" * 70,
        ]
        for d in diffs:
            status = d["status"].upper()
            mod_id = d["mod_id"]
            old_v = d.get("old_version") or "None"
            new_v = d.get("new_version") or "None"
            lines.append(f"[{status:9}] {mod_id:25} {old_v} -> {new_v}")
        lines.append("=" * 70)
        return "\n".join(lines)


class JsonFormatter(BaseFormatter):
    """Outputs machine-readable JSON for CI pipelines."""

    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    def format_report(self, report: DiagnosisReport) -> str:
        return json.dumps(report.to_dict(), indent=self.indent)

    def format_diff(self, diffs: List[Dict[str, Any]]) -> str:
        return json.dumps({"diff": diffs, "total_changes": sum(1 for d in diffs if d["status"] != "unchanged")}, indent=self.indent)


class MarkdownFormatter(BaseFormatter):
    """Outputs GitHub Flavored Markdown report suitable for CI pull requests."""

    def format_report(self, report: DiagnosisReport) -> str:
        lines: List[str] = [
            "# 🩺 Modpack Doctor Diagnostic Report",
            "",
            f"- **Target Environment:** `{report.target_env}`",
            f"- **Minecraft Version:** `{report.minecraft_version or 'Any'}`",
            f"- **Total Mods Scanned:** `{len(report.mods)}`",
            f"- **Scan Duration:** `{report.scan_duration_ms:.1f}ms`",
            "",
        ]

        if not report.has_errors():
            lines.extend([
                "> [!NOTE]",
                "> **All checks passed!** No critical dependency or version conflicts were found.",
                "",
            ])
        else:
            lines.extend([
                "> [!CAUTION]",
                f"> **Modpack validation failed!** Discovered **{report.critical_count}** critical errors.",
                "",
            ])

        if report.issues:
            lines.extend([
                "## ⚠️ Issues & Diagnostic Findings",
                "",
                "| Severity | Code | Mod ID | Details | Fix / Recommendation |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ])
            for issue in report.issues:
                sev_icon = "🔴" if issue.severity == IssueSeverity.CRITICAL else ("🟡" if issue.severity == IssueSeverity.WARNING else "🔵")
                rec = issue.recommendation or "-"
                lines.append(
                    f"| {sev_icon} **{issue.severity.value}** | `{issue.code.value}` | `{issue.mod_id or '-'}` | {issue.message} | {rec} |"
                )
            lines.append("")

        if report.mods:
            lines.extend([
                "<details>",
                "<summary><b>📦 Scanned Mods Inventory (" + str(len(report.mods)) + ")</b></summary>",
                "",
                "| Mod ID | Name | Version | Loader | Side | File |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for mod in sorted(report.mods, key=lambda m: m.id):
                lines.append(
                    f"| `{mod.id}` | {mod.name} | `{mod.version}` | {mod.loader.value} | {mod.environment.value} | `{mod.file_name}` |"
                )
            lines.extend(["", "</details>", ""])

        return "\n".join(lines)

    def format_diff(self, diffs: List[Dict[str, Any]]) -> str:
        lines = [
            "# 🔄 Modpack Diff Comparison",
            "",
            "| Status | Mod ID | Old Version | New Version | File |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for d in diffs:
            icon = "🟢" if d["status"] == "added" else ("🔴" if d["status"] == "removed" else ("🟡" if d["status"] == "changed" else "⚪"))
            lines.append(
                f"| {icon} `{d['status']}` | `{d['mod_id']}` | `{d.get('old_version') or '-'}` | `{d.get('new_version') or '-'}` | `{d.get('new_file') or d.get('old_file') or '-'}` |"
            )
        lines.append("")
        return "\n".join(lines)


def get_formatter(fmt_name: str, color: bool = True, verbose: bool = False) -> BaseFormatter:
    """Formatter factory."""
    norm = fmt_name.strip().lower()
    if norm == "json":
        return JsonFormatter()
    if norm == "markdown" or norm == "md":
        return MarkdownFormatter()
    if norm == "plain" or not color:
        return PlainTerminalFormatter()
    return RichTerminalFormatter(color=color, verbose=verbose)
