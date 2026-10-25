"""Tests for streaming JAR reader and directory scanner."""

import io
import zipfile
from pathlib import Path
import pytest
from .conftest import (
    make_fabric_jar_bytes,
    make_forge_jar_bytes,
    make_neoforge_jar_bytes,
    make_quilt_jar_bytes,
)
from modpack_doctor.models import IssueCode, LoaderType
from modpack_doctor.reader import JarReader, ModpackScanner


def test_read_fabric_jar(tmp_path: Path):
    jar_bytes = make_fabric_jar_bytes(
        mod_id="test_fabric",
        version="1.2.3",
        mixins=["fabric.mixins.json"],
        mixin_files={
            "fabric.mixins.json": {
                "package": "com.test.mixin",
                "mixins": ["TestMixin"],
            }
        },
    )
    jar_file = tmp_path / "test_fabric.jar"
    jar_file.write_bytes(jar_bytes)

    mods, issues = JarReader.read_jar_file(jar_file)
    assert len(issues) == 0
    assert len(mods) == 1
    mod = mods[0]
    assert mod.id == "test_fabric"
    assert mod.version == "1.2.3"
    assert mod.loader == LoaderType.FABRIC
    assert len(mod.mixin_configs) == 1
    assert mod.mixin_configs[0].package == "com.test.mixin"
    assert mod.mixin_configs[0].mixins == ["TestMixin"]


def test_read_forge_jar(tmp_path: Path):
    jar_bytes = make_forge_jar_bytes(
        mod_id="test_forge",
        version="2.0.0",
        mixin_configs=["forge.mixins.json"],
        mixin_files={
            "forge.mixins.json": {
                "package": "com.forge.mixin",
                "mixins": ["ForgeMixin"],
            }
        },
    )
    jar_file = tmp_path / "test_forge.jar"
    jar_file.write_bytes(jar_bytes)

    mods, issues = JarReader.read_jar_file(jar_file)
    assert len(issues) == 0
    assert len(mods) == 1
    mod = mods[0]
    assert mod.id == "test_forge"
    assert mod.loader == LoaderType.FORGE
    assert len(mod.mixin_configs) == 1
    assert mod.mixin_configs[0].mixins == ["ForgeMixin"]


def test_read_neoforge_jar(tmp_path: Path):
    jar_bytes = make_neoforge_jar_bytes(mod_id="test_neoforge", version="3.0.0")
    jar_file = tmp_path / "test_neoforge.jar"
    jar_file.write_bytes(jar_bytes)

    mods, issues = JarReader.read_jar_file(jar_file)
    assert len(issues) == 0
    assert len(mods) == 1
    assert mods[0].loader == LoaderType.NEOFORGE


def test_read_quilt_jar(tmp_path: Path):
    jar_bytes = make_quilt_jar_bytes(mod_id="test_quilt", version="4.0.0")
    jar_file = tmp_path / "test_quilt.jar"
    jar_file.write_bytes(jar_bytes)

    mods, issues = JarReader.read_jar_file(jar_file)
    assert len(issues) == 0
    assert len(mods) == 1
    assert mods[0].loader == LoaderType.QUILT


def test_read_nested_jars(tmp_path: Path):
    nested_bytes = make_fabric_jar_bytes(mod_id="nested_mod", version="0.1.0")
    parent_bytes = make_fabric_jar_bytes(
        mod_id="parent_mod",
        version="1.0.0",
        jars=[{"file": "META-INF/jars/nested.jar"}],
        nested_jar_files={"META-INF/jars/nested.jar": nested_bytes},
    )
    jar_file = tmp_path / "parent.jar"
    jar_file.write_bytes(parent_bytes)

    mods, issues = JarReader.read_jar_file(jar_file)
    assert len(issues) == 0
    mod_ids = {m.id for m in mods}
    assert "parent_mod" in mod_ids
    assert "nested_mod" in mod_ids


def test_read_nonexistent_file(tmp_path: Path):
    missing_file = tmp_path / "does_not_exist.jar"
    mods, issues = JarReader.read_jar_file(missing_file)
    assert len(mods) == 0
    assert len(issues) == 1
    assert issues[0].code == IssueCode.CORRUPT_JAR


def test_read_corrupt_zip(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.jar"
    corrupt_file.write_bytes(b"PK\x03\x04not a valid zip archive")
    mods, issues = JarReader.read_jar_file(corrupt_file)
    assert len(mods) == 0
    assert len(issues) == 1
    assert issues[0].code == IssueCode.CORRUPT_JAR


def test_read_missing_manifest(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("some/other/file.txt", "hello")
    empty_jar = tmp_path / "plain_lib.jar"
    empty_jar.write_bytes(buf.getvalue())

    mods, issues = JarReader.read_jar_file(empty_jar)
    assert len(mods) == 0
    assert len(issues) == 1
    assert issues[0].code == IssueCode.INVALID_MANIFEST


def test_read_invalid_json_manifest(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fabric.mod.json", "{invalid json syntax")
    bad_jar = tmp_path / "bad_syntax.jar"
    bad_jar.write_bytes(buf.getvalue())

    mods, issues = JarReader.read_jar_file(bad_jar)
    assert len(mods) == 0
    assert len(issues) == 1
    assert issues[0].code == IssueCode.INVALID_MANIFEST


def test_scanner_directory(tmp_path: Path):
    # Create two jar files
    jar1 = tmp_path / "mod1.jar"
    jar1.write_bytes(make_fabric_jar_bytes("mod1"))

    sub = tmp_path / "sub"
    sub.mkdir()
    jar2 = sub / "mod2.jar"
    jar2.write_bytes(make_fabric_jar_bytes("mod2"))

    # Non-recursive
    mods, _ = ModpackScanner.scan_directory(tmp_path, recursive=False)
    assert len(mods) == 1
    assert mods[0].id == "mod1"

    # Recursive
    mods_rec, _ = ModpackScanner.scan_directory(tmp_path, recursive=True)
    assert len(mods_rec) == 2

    # Single file passed to scan_directory
    mods_single, _ = ModpackScanner.scan_directory(jar1)
    assert len(mods_single) == 1
    assert mods_single[0].id == "mod1"

    # Nonexistent directory
    mods_err, issues_err = ModpackScanner.scan_directory(tmp_path / "nonexistent")
    assert len(mods_err) == 0
    assert len(issues_err) == 1
