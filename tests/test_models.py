"""Tests for data models."""

from modpack_doctor.models import (
    Dependency,
    DepType,
    DiagnosisReport,
    DiagnosticIssue,
    Environment,
    IssueCode,
    IssueSeverity,
    LoaderType,
    MixinInfo,
    ModInfo,
)


def test_environment_from_str():
    assert Environment.from_str(None) == Environment.UNIVERSAL
    assert Environment.from_str("") == Environment.UNIVERSAL
    assert Environment.from_str("client") == Environment.CLIENT
    assert Environment.from_str("client_only") == Environment.CLIENT
    assert Environment.from_str("clientonly") == Environment.CLIENT
    assert Environment.from_str("server") == Environment.SERVER
    assert Environment.from_str("server_only") == Environment.SERVER
    assert Environment.from_str("dedicated_server") == Environment.SERVER
    assert Environment.from_str("both") == Environment.UNIVERSAL
    assert Environment.from_str("*") == Environment.UNIVERSAL
    assert Environment.from_str("unknown_side") == Environment.UNIVERSAL


def test_dependency_to_dict():
    dep = Dependency(
        mod_id="test_dep",
        version_range=">=1.0.0",
        dep_type=DepType.REQUIRED,
        side=Environment.CLIENT,
        ordering="BEFORE",
    )
    d = dep.to_dict()
    assert d["mod_id"] == "test_dep"
    assert d["version_range"] == ">=1.0.0"
    assert d["dep_type"] == "required"
    assert d["side"] == "client"
    assert d["ordering"] == "BEFORE"


def test_mixin_info():
    mixin = MixinInfo(
        config_file="test.mixins.json",
        package="com.example.mixin",
        mixins=["CommonMixin"],
        client_mixins=["ClientMixin"],
        server_mixins=["ServerMixin"],
        compatibility_level="JAVA_17",
    )
    assert mixin.all_mixins() == ["CommonMixin", "ClientMixin", "ServerMixin"]
    d = mixin.to_dict()
    assert d["config_file"] == "test.mixins.json"
    assert d["package"] == "com.example.mixin"
    assert "CommonMixin" in d["mixins"]
    assert "ClientMixin" in d["client_mixins"]
    assert "ServerMixin" in d["server_mixins"]
    assert d["compatibility_level"] == "JAVA_17"


def test_mod_info_to_dict():
    mod = ModInfo(
        id="sample_mod",
        name="Sample Mod",
        version="2.0.0",
        loader=LoaderType.FABRIC,
        file_path="/mods/sample.jar",
        file_name="sample.jar",
        file_size=12345,
        environment=Environment.UNIVERSAL,
        dependencies=[Dependency(mod_id="fabric-api")],
        provides=["sample-alias"],
        mixin_configs=[MixinInfo(config_file="sample.mixins.json")],
        entrypoints={"main": ["com.sample.Mod"]},
        description="A great mod",
        authors=["Author 1"],
        nested_jars=["META-INF/jars/sub.jar"],
    )
    d = mod.to_dict()
    assert d["id"] == "sample_mod"
    assert d["name"] == "Sample Mod"
    assert d["version"] == "2.0.0"
    assert d["loader"] == "fabric"
    assert d["file_size"] == 12345
    assert len(d["dependencies"]) == 1
    assert d["provides"] == ["sample-alias"]
    assert len(d["mixin_configs"]) == 1
    assert d["entrypoints"]["main"] == ["com.sample.Mod"]
    assert d["authors"] == ["Author 1"]
    assert d["nested_jars"] == ["META-INF/jars/sub.jar"]


def test_diagnostic_issue_to_dict():
    issue = DiagnosticIssue(
        code=IssueCode.MISSING_DEPENDENCY,
        severity=IssueSeverity.CRITICAL,
        message="Missing mod fabric-api",
        mod_id="appleskin",
        related_mod_id="fabric-api",
        file_path="appleskin.jar",
        recommendation="Install fabric-api",
    )
    d = issue.to_dict()
    assert d["code"] == "MISSING_DEPENDENCY"
    assert d["severity"] == "CRITICAL"
    assert d["mod_id"] == "appleskin"
    assert d["related_mod_id"] == "fabric-api"
    assert d["file_path"] == "appleskin.jar"
    assert d["recommendation"] == "Install fabric-api"


def test_diagnosis_report():
    crit_issue = DiagnosticIssue(
        code=IssueCode.MISSING_DEPENDENCY,
        severity=IssueSeverity.CRITICAL,
        message="Missing dep",
    )
    warn_issue = DiagnosticIssue(
        code=IssueCode.DUPLICATE_MOD,
        severity=IssueSeverity.WARNING,
        message="Duplicate mod",
    )
    info_issue = DiagnosticIssue(
        code=IssueCode.MISSING_DEPENDENCY,
        severity=IssueSeverity.INFO,
        message="Optional missing",
    )
    mod1 = ModInfo(
        id="mod1",
        name="Mod 1",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod1.jar",
        file_name="mod1.jar",
    )
    mod2 = ModInfo(
        id="mod2",
        name="Mod 2",
        version="1.0.0",
        loader=LoaderType.FORGE,
        file_path="mod2.jar",
        file_name="mod2.jar",
    )

    report = DiagnosisReport(
        scanned_path="/test/mods",
        target_env="client",
        minecraft_version="1.20.1",
        mods=[mod1, mod2],
        issues=[crit_issue, warn_issue, info_issue],
        scan_duration_ms=42.5,
    )

    assert report.critical_count == 1
    assert report.warning_count == 1
    assert report.info_count == 1
    assert report.has_errors() is True
    assert report.has_warnings() is True

    d = report.to_dict()
    assert d["scanned_path"] == "/test/mods"
    assert d["target_env"] == "client"
    assert d["minecraft_version"] == "1.20.1"
    assert d["summary"]["total_mods"] == 2
    assert d["summary"]["loaders"]["fabric"] == 1
    assert d["summary"]["loaders"]["forge"] == 1
    assert d["summary"]["critical_issues"] == 1
    assert d["summary"]["warning_issues"] == 1
    assert d["summary"]["info_issues"] == 1
    assert d["summary"]["healthy"] is False


def test_diagnosis_report_healthy():
    report = DiagnosisReport(scanned_path="/empty")
    assert report.has_errors() is False
    assert report.has_warnings() is False
    d = report.to_dict()
    assert d["summary"]["healthy"] is True
