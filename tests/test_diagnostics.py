"""Tests for diagnostic engine."""

from pathlib import Path
from modpack_doctor.diagnostics import DiagnosticEngine, diff_modpacks
from modpack_doctor.models import (
    Dependency,
    DepType,
    Environment,
    IssueCode,
    IssueSeverity,
    LoaderType,
    ModInfo,
)


def make_mod(
    mod_id: str,
    version: str = "1.0.0",
    deps=None,
    env=Environment.UNIVERSAL,
    entrypoints=None,
    file_name=None,
) -> ModInfo:
    return ModInfo(
        id=mod_id,
        name=mod_id.capitalize(),
        version=version,
        loader=LoaderType.FABRIC,
        file_path=file_name or f"{mod_id}.jar",
        file_name=file_name or f"{mod_id}.jar",
        environment=env,
        dependencies=deps or [],
        entrypoints=entrypoints or {},
    )


def test_diagnose_empty_mods():
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([])
    assert issues == []


def test_missing_dependency():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b", version_range=">=1.0.0")])
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod_a])
    assert any(i.code == IssueCode.MISSING_DEPENDENCY and i.related_mod_id == "mod_b" for i in issues)


def test_incompatible_version():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b", version_range=">=2.0.0")])
    mod_b = make_mod("mod_b", version="1.0.0")
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod_a, mod_b])
    assert any(i.code == IssueCode.INCOMPATIBLE_VERSION and i.related_mod_id == "mod_b" for i in issues)


def test_conflict_breaks():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b", version_range="*", dep_type=DepType.BREAKS)])
    mod_b = make_mod("mod_b", version="1.0.0")
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod_a, mod_b])
    assert any(i.code == IssueCode.CONFLICT_DETECTED and i.related_mod_id == "mod_b" for i in issues)


def test_recommended_optional_info():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="opt_mod", dep_type=DepType.RECOMMENDED)])
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod_a])
    assert any(i.code == IssueCode.MISSING_DEPENDENCY and i.severity == IssueSeverity.INFO for i in issues)


def test_virtual_minecraft_dep():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="minecraft", version_range=">=1.20.0")])
    # Case 1: matching MC version
    engine_ok = DiagnosticEngine(minecraft_version="1.20.1")
    issues_ok = engine_ok.diagnose_mods([mod_a])
    assert not any(i.related_mod_id == "minecraft" for i in issues_ok)

    # Case 2: incompatible MC version
    engine_bad = DiagnosticEngine(minecraft_version="1.19.4")
    issues_bad = engine_bad.diagnose_mods([mod_a])
    assert any(i.code == IssueCode.INCOMPATIBLE_VERSION and i.related_mod_id == "minecraft" for i in issues_bad)


def test_virtual_java_and_loader_dep():
    mod_a = make_mod(
        "mod_a",
        deps=[
            Dependency(mod_id="java", version_range=">=17"),
            Dependency(mod_id="fabricloader", version_range=">=0.15.0"),
        ],
    )
    # Test java mismatch
    engine_java = DiagnosticEngine(java_version="16")
    issues_java = engine_java.diagnose_mods([mod_a])
    assert any(i.related_mod_id == "java" for i in issues_java)

    # Test loader mismatch
    engine_loader = DiagnosticEngine(loader_version="0.14.20")
    issues_loader = engine_loader.diagnose_mods([mod_a])
    assert any(i.related_mod_id == "fabricloader" for i in issues_loader)


def test_duplicate_mods():
    mod1 = make_mod("dup_mod", version="1.0.0", file_name="dup_mod-1.0.jar")
    mod2 = make_mod("dup_mod", version="2.0.0", file_name="dup_mod-2.0.jar")
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod1, mod2])
    assert any(i.code == IssueCode.DUPLICATE_MOD and i.severity == IssueSeverity.CRITICAL for i in issues)

    # Same version
    mod3 = make_mod("dup_mod2", version="1.0.0", file_name="dup1.jar")
    mod4 = make_mod("dup_mod2", version="1.0.0", file_name="dup2.jar")
    issues_same = engine.diagnose_mods([mod3, mod4])
    assert any(i.code == IssueCode.DUPLICATE_MOD and i.severity == IssueSeverity.WARNING for i in issues_same)


def test_environment_mismatches():
    # Client-only mod on server
    mod_client = make_mod("client_hud", env=Environment.CLIENT)
    engine_server = DiagnosticEngine(target_env="server")
    issues_server = engine_server.diagnose_mods([mod_client])
    assert any(i.code == IssueCode.CLIENT_MOD_ON_SERVER for i in issues_server)

    # Client-only entrypoints on server
    mod_ep = make_mod("client_ep", env=Environment.UNIVERSAL, entrypoints={"client": ["com.example.Client"]})
    issues_ep = engine_server.diagnose_mods([mod_ep])
    assert any(i.code == IssueCode.CLIENT_MOD_ON_SERVER for i in issues_ep)

    # Server-only mod on client
    mod_server = make_mod("server_tool", env=Environment.SERVER)
    engine_client = DiagnosticEngine(target_env="client")
    issues_client = engine_client.diagnose_mods([mod_server])
    assert any(i.code == IssueCode.SERVER_MOD_ON_CLIENT for i in issues_client)


def test_skip_side_dependencies():
    # Mod A requires Client Dep only on client side.
    # When target is server, missing client-side dependency should be skipped.
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="client_dep", side=Environment.CLIENT)])
    engine_server = DiagnosticEngine(target_env="server")
    issues = engine_server.diagnose_mods([mod_a])
    assert not any(i.related_mod_id == "client_dep" for i in issues)

    # When target is client, server-side dependency is skipped
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="server_dep", side=Environment.SERVER)])
    engine_client = DiagnosticEngine(target_env="client")
    issues_c = engine_client.diagnose_mods([mod_b])
    assert not any(i.related_mod_id == "server_dep" for i in issues_c)


def test_circular_dependency():
    mod_a = make_mod("mod_a", deps=[Dependency(mod_id="mod_b")])
    mod_b = make_mod("mod_b", deps=[Dependency(mod_id="mod_a")])
    engine = DiagnosticEngine()
    issues = engine.diagnose_mods([mod_a, mod_b])
    assert any(i.code == IssueCode.CIRCULAR_DEPENDENCY for i in issues)


def test_diff_modpacks():
    mods_a = [
        make_mod("common_same", version="1.0.0"),
        make_mod("common_upgraded", version="1.0.0"),
        make_mod("removed_mod", version="1.0.0"),
    ]
    mods_b = [
        make_mod("common_same", version="1.0.0"),
        make_mod("common_upgraded", version="2.0.0"),
        make_mod("added_mod", version="1.5.0"),
    ]
    diffs = diff_modpacks(mods_a, mods_b)
    diff_map = {d["mod_id"]: d["status"] for d in diffs}
    assert diff_map["common_same"] == "unchanged"
    assert diff_map["common_upgraded"] == "changed"
    assert diff_map["removed_mod"] == "removed"
    assert diff_map["added_mod"] == "added"
