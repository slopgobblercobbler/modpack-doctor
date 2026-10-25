"""Tests for CLI subcommands."""

import json
from pathlib import Path
from click.testing import CliRunner
from .conftest import make_fabric_jar_bytes
from modpack_doctor.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_cli_scan_healthy(tmp_path: Path):
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1", version="1.0.0"))

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "PASSED: MODPACK HEALTHY" in result.output or "No issues" in result.output


def test_cli_scan_fail_on_error(tmp_path: Path):
    # Missing required dependency
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1", depends={"missing_mod": ">=1.0.0"}))

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])
    assert result.exit_code == 1
    assert "MISSING_DEPENDENCY" in result.output


def test_cli_scan_fail_on_warning(tmp_path: Path):
    # Two identical mods -> duplicate warning
    jar1 = tmp_path / "mod1.jar"
    jar2 = tmp_path / "mod2.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1", version="1.0.0"))
    jar2.write_bytes(make_fabric_jar_bytes("mod1", version="1.0.0"))

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--fail-on-warning"])
    assert result.exit_code == 2
    assert "DUPLICATE_MOD" in result.output


def test_cli_scan_output_file_and_formats(tmp_path: Path):
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1"))
    out_file = tmp_path / "report.json"

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "-f", "json", "-o", str(out_file), "-v"])
    assert result.exit_code == 0
    assert out_file.exists()
    parsed = json.loads(out_file.read_text(encoding="utf-8"))
    assert parsed["summary"]["total_mods"] == 1


def test_cli_scan_plain_and_markdown(tmp_path: Path):
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1"))

    runner = CliRunner()
    res_plain = runner.invoke(main, ["scan", str(tmp_path), "-f", "plain", "--no-color"])
    assert res_plain.exit_code == 0
    assert "MODPACK DOCTOR DIAGNOSTIC REPORT" in res_plain.output

    res_md = runner.invoke(main, ["scan", str(tmp_path), "-f", "markdown"])
    assert res_md.exit_code == 0
    assert "# 🩺 Modpack Doctor Diagnostic Report" in res_md.output


def test_cli_scan_no_fail_on_error(tmp_path: Path):
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1", depends={"missing_mod": ">=1.0.0"}))

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--no-fail-on-error"])
    assert result.exit_code == 0


def test_cli_inspect_valid_and_json(tmp_path: Path):
    # Mod with dependencies, mixins, nested jars, provides
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(
        make_fabric_jar_bytes(
            "mod1",
            version="1.2.3",
            description="Inspect test",
            provides=["alias1"],
            depends={"dep1": ">=1.0"},
            mixins=["mod1.mixins.json"],
            jars=[{"file": "META-INF/jars/sub.jar"}],
        )
    )

    runner = CliRunner()
    # Plain inspect with all metadata present
    res_plain = runner.invoke(main, ["inspect", str(jar1)])
    assert res_plain.exit_code == 0
    assert "MOD JAR INSPECTION" in res_plain.output
    assert "Mod ID:       mod1" in res_plain.output
    assert "Provides:     alias1" in res_plain.output
    assert "[REQUIRED] dep1" in res_plain.output
    assert "mod1.mixins.json" in res_plain.output
    assert "META-INF/jars/sub.jar" in res_plain.output

    # Inspect mod with no dependencies/mixins/nested jars
    jar_empty = tmp_path / "empty.jar"
    jar_empty.write_bytes(make_fabric_jar_bytes("empty_mod"))
    res_empty = runner.invoke(main, ["inspect", str(jar_empty)])
    assert res_empty.exit_code == 0
    assert "(None)" in res_empty.output

    # JSON inspect
    res_json = runner.invoke(main, ["inspect", str(jar1), "-f", "json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["mods"][0]["id"] == "mod1"


def test_cli_inspect_invalid(tmp_path: Path):
    bad_jar = tmp_path / "bad.jar"
    bad_jar.write_bytes(b"not a zip")

    runner = CliRunner()
    res = runner.invoke(main, ["inspect", str(bad_jar)])
    assert res.exit_code == 1
    assert "Error inspecting JAR" in res.output


def test_cli_graph(tmp_path: Path):
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1", depends={"mod2": "*"}))
    jar2 = tmp_path / "mod2.jar"
    jar2.write_bytes(make_fabric_jar_bytes("mod2"))

    runner = CliRunner()

    # Tree
    res_tree = runner.invoke(main, ["graph", str(tmp_path), "-f", "tree"])
    assert res_tree.exit_code == 0
    assert "mod1" in res_tree.output

    # Tree with root
    res_tree_root = runner.invoke(main, ["graph", str(tmp_path), "-f", "tree", "-r", "mod1"])
    assert res_tree_root.exit_code == 0
    assert "mod1" in res_tree_root.output

    # Mermaid
    res_mermaid = runner.invoke(main, ["graph", str(tmp_path), "-f", "mermaid"])
    assert res_mermaid.exit_code == 0
    assert "graph TD" in res_mermaid.output

    # DOT with output file
    dot_file = tmp_path / "graph.dot"
    res_dot = runner.invoke(main, ["graph", str(tmp_path), "-f", "dot", "-o", str(dot_file)])
    assert res_dot.exit_code == 0
    assert dot_file.exists()
    assert "digraph ModpackDependencies" in dot_file.read_text(encoding="utf-8")


def test_cli_diff(tmp_path: Path):
    dir1 = tmp_path / "pack1"
    dir2 = tmp_path / "pack2"
    dir1.mkdir()
    dir2.mkdir()

    (dir1 / "mod_a.jar").write_bytes(make_fabric_jar_bytes("mod_a", version="1.0.0"))
    (dir2 / "mod_a.jar").write_bytes(make_fabric_jar_bytes("mod_a", version="1.1.0"))
    (dir2 / "mod_b.jar").write_bytes(make_fabric_jar_bytes("mod_b", version="2.0.0"))

    runner = CliRunner()
    res = runner.invoke(main, ["diff", str(dir1), str(dir2), "--no-color"])
    assert res.exit_code == 0
    assert "mod_a" in res.output
    assert "mod_b" in res.output

    # Output to file with json format
    out_file = tmp_path / "diff.json"
    res_json = runner.invoke(main, ["diff", str(dir1), str(dir2), "-f", "json", "-o", str(out_file)])
    assert res_json.exit_code == 0
    assert out_file.exists()


def test_cli_verify(tmp_path: Path):
    # Clean pack
    jar_ok = tmp_path / "ok.jar"
    jar_ok.write_bytes(make_fabric_jar_bytes("ok_mod"))

    runner = CliRunner()
    res_ok = runner.invoke(main, ["verify", str(tmp_path)])
    assert res_ok.exit_code == 0

    # Failing pack
    jar_bad = tmp_path / "bad.jar"
    jar_bad.write_bytes(make_fabric_jar_bytes("bad_mod", depends={"missing": "*"}))

    res_fail = runner.invoke(main, ["verify", str(tmp_path)])
    assert res_fail.exit_code == 1

    # Verify with output file
    v_out = tmp_path / "verify.md"
    res_md = runner.invoke(main, ["verify", str(tmp_path), "-f", "markdown", "-o", str(v_out)])
    assert res_md.exit_code == 1
    assert v_out.exists()


def test_cli_verify_fail_on_warning(tmp_path: Path):
    # Two identical mods -> duplicate warning
    dir_warn = tmp_path / "warn_pack"
    dir_warn.mkdir()
    (dir_warn / "m1.jar").write_bytes(make_fabric_jar_bytes("m1", version="1.0.0"))
    (dir_warn / "m2.jar").write_bytes(make_fabric_jar_bytes("m1", version="1.0.0"))

    runner = CliRunner()
    res = runner.invoke(main, ["verify", str(dir_warn), "--fail-on-warning"])
    assert res.exit_code == 2
