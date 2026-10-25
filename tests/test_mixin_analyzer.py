"""Tests for mixin analyzer."""

from modpack_doctor.mixin_analyzer import MixinAnalyzer
from modpack_doctor.models import IssueCode, IssueSeverity, LoaderType, MixinInfo, ModInfo


def test_parse_mixin_json_valid():
    content = """{
        "required": true,
        "package": "com.example.mod.mixin",
        "compatibilityLevel": "JAVA_17",
        "mixins": [
            "CommonMixin"
        ],
        "client": [
            "ClientMixin"
        ],
        "server": [
            "ServerMixin"
        ]
    }"""
    info = MixinAnalyzer.parse_mixin_json(content, "mod.mixins.json")
    assert info.config_file == "mod.mixins.json"
    assert info.package == "com.example.mod.mixin"
    assert info.compatibility_level == "JAVA_17"
    assert info.mixins == ["CommonMixin"]
    assert info.client_mixins == ["ClientMixin"]
    assert info.server_mixins == ["ServerMixin"]
    assert len(info.all_mixins()) == 3


def test_parse_mixin_json_invalid():
    info = MixinAnalyzer.parse_mixin_json("NOT_JSON", "corrupt.json")
    assert info.config_file == "corrupt.json"
    assert info.package == ""
    assert info.mixins == []


def test_detect_collisions_generic_name():
    # Two mods using "mixins.json"
    mod1 = ModInfo(
        id="mod_a",
        name="Mod A",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_a.jar",
        file_name="mod_a.jar",
        mixin_configs=[MixinInfo(config_file="mixins.json")],
    )
    mod2 = ModInfo(
        id="mod_b",
        name="Mod B",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_b.jar",
        file_name="mod_b.jar",
        mixin_configs=[MixinInfo(config_file="mixins.json")],
    )
    issues = MixinAnalyzer.detect_collisions([mod1, mod2])
    assert len(issues) == 1
    assert issues[0].code == IssueCode.MIXIN_COLLISION
    assert issues[0].severity == IssueSeverity.CRITICAL


def test_detect_collisions_custom_name():
    # Two mods using "shared.mixins.json"
    mod1 = ModInfo(
        id="mod_a",
        name="Mod A",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_a.jar",
        file_name="mod_a.jar",
        mixin_configs=[MixinInfo(config_file="shared.mixins.json")],
    )
    mod2 = ModInfo(
        id="mod_b",
        name="Mod B",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_b.jar",
        file_name="mod_b.jar",
        mixin_configs=[MixinInfo(config_file="shared.mixins.json")],
    )
    issues = MixinAnalyzer.detect_collisions([mod1, mod2])
    assert len(issues) == 1
    assert issues[0].severity == IssueSeverity.WARNING


def test_detect_collisions_identical_mixin_class():
    mod1 = ModInfo(
        id="mod_a",
        name="Mod A",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_a.jar",
        file_name="mod_a.jar",
        mixin_configs=[
            MixinInfo(
                config_file="a.mixins.json",
                package="com.example.common",
                mixins=["DuplicatedMixin"],
            )
        ],
    )
    mod2 = ModInfo(
        id="mod_b",
        name="Mod B",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_b.jar",
        file_name="mod_b.jar",
        mixin_configs=[
            MixinInfo(
                config_file="b.mixins.json",
                package="com.example.common",
                mixins=["DuplicatedMixin"],
            )
        ],
    )
    issues = MixinAnalyzer.detect_collisions([mod1, mod2])
    assert any(i.code == IssueCode.MIXIN_COLLISION and "Identical Mixin class name" in i.message for i in issues)


def test_detect_collisions_none():
    mod1 = ModInfo(
        id="mod_a",
        name="Mod A",
        version="1.0.0",
        loader=LoaderType.FABRIC,
        file_path="mod_a.jar",
        file_name="mod_a.jar",
        mixin_configs=[
            MixinInfo(
                config_file="a.mixins.json",
                package="com.example.a",
                mixins=["AMixin"],
            )
        ],
    )
    issues = MixinAnalyzer.detect_collisions([mod1])
    assert len(issues) == 0
