"""Command-line interface for modpack-doctor."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from modpack_doctor import __version__
from modpack_doctor.diagnostics import DiagnosticEngine, diff_modpacks
from modpack_doctor.formatters import get_formatter
from modpack_doctor.graph import ModDependencyGraph
from modpack_doctor.models import LoaderType
from modpack_doctor.reader import JarReader, ModpackScanner


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="modpack-doctor")
def main() -> None:
    """Modpack Doctor: Comprehensive Minecraft Modpack & Dependency Diagnostic CLI.

    Diagnoses missing dependencies, version conflicts, duplicate libraries,
    Mixin collisions, and client/server environment mismatches.
    """
    pass


# =====================================================================
# SCAN COMMAND
# =====================================================================

@main.command("scan")
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("-t", "--target", type=click.Choice(["both", "client", "server"], case_sensitive=False), default="both", help="Target execution environment side.")
@click.option("-m", "--mc-version", help="Target Minecraft version to validate against (e.g., 1.20.1).")
@click.option("-l", "--loader-version", help="Mod loader version to validate against.")
@click.option("-f", "--format", "output_format", type=click.Choice(["rich", "plain", "json", "markdown"], case_sensitive=False), default="rich", help="Output report format.")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write report to file instead of stdout.")
@click.option("-r", "--recursive", is_flag=True, help="Scan subdirectories recursively.")
@click.option("--fail-on-warning", is_flag=True, help="Exit with non-zero code if any warnings are detected.")
@click.option("--fail-on-error/--no-fail-on-error", default=True, help="Exit with non-zero code if critical errors are detected.")
@click.option("-v", "--verbose", is_flag=True, help="Display verbose details including full mod inventory.")
@click.option("--no-color", is_flag=True, help="Disable colored output.")
def scan_cmd(
    directory: Path,
    target: str,
    mc_version: Optional[str],
    loader_version: Optional[str],
    output_format: str,
    output: Optional[Path],
    recursive: bool,
    fail_on_warning: bool,
    fail_on_error: bool,
    verbose: bool,
    no_color: bool,
) -> None:
    """Scan a directory of mod JARs and run full diagnostic suite."""
    engine = DiagnosticEngine(
        target_env=target,
        minecraft_version=mc_version,
        loader_version=loader_version,
    )
    report = engine.diagnose_directory(directory, recursive=recursive)

    formatter = get_formatter(output_format, color=not no_color, verbose=verbose)
    rendered = formatter.format_report(report)

    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"Report successfully written to {output}")
    else:
        click.echo(rendered)

    if fail_on_error and report.has_errors():
        sys.exit(1)
    if fail_on_warning and report.has_warnings():
        sys.exit(2)
    sys.exit(0)


# =====================================================================
# VERIFY COMMAND (CI / CD OPTIMIZED)
# =====================================================================

@main.command("verify")
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("-t", "--target", type=click.Choice(["both", "client", "server"], case_sensitive=False), default="both", help="Target environment.")
@click.option("-m", "--mc-version", help="Target Minecraft version.")
@click.option("-f", "--format", "output_format", type=click.Choice(["rich", "plain", "json", "markdown"], case_sensitive=False), default="rich", help="Output format.")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="File path to save result.")
@click.option("--fail-on-warning", is_flag=True, help="Fail CI pipeline on warnings as well as critical errors.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
def verify_cmd(
    directory: Path,
    target: str,
    mc_version: Optional[str],
    output_format: str,
    output: Optional[Path],
    fail_on_warning: bool,
    verbose: bool,
) -> None:
    """Strict validation designed for CI pipelines (returns exit code 0 on pass, 1 on fail)."""
    engine = DiagnosticEngine(
        target_env=target,
        minecraft_version=mc_version,
    )
    report = engine.diagnose_directory(directory, recursive=False)

    formatter = get_formatter(output_format, color=True, verbose=verbose)
    rendered = formatter.format_report(report)

    if output:
        output.write_text(rendered, encoding="utf-8")
    else:
        click.echo(rendered)

    if report.has_errors():
        sys.exit(1)
    if fail_on_warning and report.has_warnings():
        sys.exit(2)
    sys.exit(0)


# =====================================================================
# INSPECT COMMAND
# =====================================================================

@main.command("inspect")
@click.argument("jar_path", type=click.Path(exists=True, path_type=Path))
@click.option("-f", "--format", "output_format", type=click.Choice(["plain", "json"], case_sensitive=False), default="plain", help="Output format.")
def inspect_cmd(jar_path: Path, output_format: str) -> None:
    """Deep inspect a single mod JAR file."""
    mods, issues = JarReader.read_jar_file(jar_path)

    if not mods and issues:
        click.echo(f"Error inspecting JAR: {issues[0].message}", err=True)
        sys.exit(1)

    if output_format == "json":
        import json
        out_dict = {
            "file": str(jar_path),
            "mods": [m.to_dict() for m in mods],
            "issues": [i.to_dict() for i in issues],
        }
        click.echo(json.dumps(out_dict, indent=2))
        return

    # Plain text detailed inspection
    click.echo("=" * 60)
    click.echo(f"MOD JAR INSPECTION: {jar_path.name}")
    click.echo("=" * 60)
    for mod in mods:
        click.echo(f"Mod ID:       {mod.id}")
        click.echo(f"Name:         {mod.name}")
        click.echo(f"Version:      {mod.version}")
        click.echo(f"Loader:       {mod.loader.value.upper()}")
        click.echo(f"Environment:  {mod.environment.value.upper()}")
        click.echo(f"Authors:      {', '.join(mod.authors) or 'None'}")
        click.echo(f"Description:  {mod.description.strip()[:100] or 'None'}")

        if mod.provides:
            click.echo(f"Provides:     {', '.join(mod.provides)}")

        click.echo("\nDependencies:")
        if not mod.dependencies:
            click.echo("  (None)")
        else:
            for dep in mod.dependencies:
                click.echo(f"  - [{dep.dep_type.value.upper()}] {dep.mod_id} ({dep.version_range}) [side={dep.side.value}]")

        click.echo("\nMixin Configs:")
        if not mod.mixin_configs:
            click.echo("  (None)")
        else:
            for m in mod.mixin_configs:
                click.echo(f"  - {m.config_file} (pkg: {m.package or 'default'}, {len(m.all_mixins())} mixins)")

        if mod.nested_jars:
            click.echo("\nNested JARs:")
            for j in mod.nested_jars:
                click.echo(f"  - {j}")
        click.echo("-" * 60)


# =====================================================================
# GRAPH COMMAND
# =====================================================================

@main.command("graph")
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("-f", "--format", "graph_format", type=click.Choice(["tree", "mermaid", "dot"], case_sensitive=False), default="tree", help="Graph output format.")
@click.option("-r", "--root", help="Filter dependency tree from a specific root mod ID.")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write graph to file.")
def graph_cmd(
    directory: Path,
    graph_format: str,
    root: Optional[str],
    output: Optional[Path],
) -> None:
    """Visualize or export the modpack dependency graph."""
    mods, _ = ModpackScanner.scan_directory(directory)
    graph = ModDependencyGraph.from_mods(mods)

    if graph_format == "tree":
        rendered = graph.to_ascii_tree(root_id=root)
    elif graph_format == "mermaid":
        rendered = graph.to_mermaid()
    else:  # dot
        rendered = graph.to_dot()

    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"Graph written to {output}")
    else:
        click.echo(rendered)


# =====================================================================
# DIFF COMMAND
# =====================================================================

@main.command("diff")
@click.argument("dir1", type=click.Path(exists=True, path_type=Path))
@click.argument("dir2", type=click.Path(exists=True, path_type=Path))
@click.option("-f", "--format", "output_format", type=click.Choice(["rich", "plain", "json", "markdown"], case_sensitive=False), default="rich", help="Output format.")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write diff to file.")
@click.option("--no-color", is_flag=True, help="Disable colored output.")
def diff_cmd(
    dir1: Path,
    dir2: Path,
    output_format: str,
    output: Optional[Path],
    no_color: bool,
) -> None:
    """Compare two modpack directories (added, removed, updated mods)."""
    mods1, _ = ModpackScanner.scan_directory(dir1)
    mods2, _ = ModpackScanner.scan_directory(dir2)

    diffs = diff_modpacks(mods1, mods2)
    formatter = get_formatter(output_format, color=not no_color)
    rendered = formatter.format_diff(diffs)

    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"Diff written to {output}")
    else:
        click.echo(rendered)


if __name__ == "__main__":
    main()
