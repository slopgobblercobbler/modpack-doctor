"""Tests for mod manifest parsers."""

import pytest
from modpack_doctor.manifest_parser import ManifestParser
from modpack_doctor.models import DepType, Environment, LoaderType


def test_parse_manifest_unknown():
    with pytest.raises(ValueError, match="Unrecognized manifest type"):
        ManifestParser.parse_manifest_content("{}", "unknown.json")


def test_fabric_parsing_full():
    content = """{
        "schemaVersion": 1,
        "id": "fabric_test",
        "name": "Fabric Test Mod",
        "version": "1.2.3",
        "environment": "client",
        "description": "Awesome Fabric Mod",
        "depends": {
            "fabricloader": ">=0.14.0",
            "minecraft": ["1.20", "1.20.1"]
        },
        "recommends": {
            "modmenu": "*"
        },
        "suggests": ["optifabric"],
        "conflicts": {
            "badmod": "*"
        },
        "breaks": {
            "brokenmod": "<1.0"
        },
        "provides": ["fabric_test_alias"],
        "mixins": [
            "fabric_test.mixins.json",
            {"config": "fabric_test_client.mixins.json", "environment": "client"}
        ],
        "entrypoints": {
            "main": ["com.example.Main"],
            "client": [{"value": "com.example.Client"}]
        },
        "jars": [
            {"file": "META-INF/jars/nested.jar"}
        ],
        "authors": [
            "AuthorA",
            {"name": "AuthorB"}
        ]
    }"""

    mods = ManifestParser.parse_manifest_content(content, "fabric.mod.json", jar_filename="fabric_test.jar")
    assert len(mods) == 1
    mod = mods[0]
    assert mod.id == "fabric_test"
    assert mod.name == "Fabric Test Mod"
    assert mod.version == "1.2.3"
    assert mod.loader == LoaderType.FABRIC
    assert mod.environment == Environment.CLIENT
    assert mod.description == "Awesome Fabric Mod"
    assert mod.provides == ["fabric_test_alias"]
    assert len(mod.mixin_configs) == 2
    assert mod.mixin_configs[0].config_file == "fabric_test.mixins.json"
    assert mod.mixin_configs[1].config_file == "fabric_test_client.mixins.json"
    assert mod.entrypoints["main"] == ["com.example.Main"]
    assert mod.entrypoints["client"] == ["com.example.Client"]
    assert mod.nested_jars == ["META-INF/jars/nested.jar"]
    assert mod.authors == ["AuthorA", "AuthorB"]

    # Verify dependencies
    dep_types = {d.mod_id: d.dep_type for d in mod.dependencies}
    assert dep_types["fabricloader"] == DepType.REQUIRED
    assert dep_types["minecraft"] == DepType.REQUIRED
    assert dep_types["modmenu"] == DepType.RECOMMENDED
    assert dep_types["optifabric"] == DepType.SUGGESTED
    assert dep_types["badmod"] == DepType.CONFLICT
    assert dep_types["brokenmod"] == DepType.BREAKS


def test_fabric_provides_dict():
    content = """{
        "id": "prov_mod",
        "provides": {"sub_alias": "1.0.0"}
    }"""
    mod = ManifestParser.parse_fabric(content)
    assert "sub_alias" in mod.provides


def test_fabric_missing_id():
    with pytest.raises(ValueError, match="Missing 'id'"):
        ManifestParser.parse_fabric('{"name": "No ID"}')


def test_fabric_version_resolution():
    content = '{"id": "test_res", "version": "${file.jarVersion}"}'
    # Test from manifest.mf
    mf = "Manifest-Version: 1.0\nImplementation-Version: 2.3.4\n"
    mod = ManifestParser.parse_fabric(content, jar_filename="test.jar", manifest_mf=mf)
    assert mod.version == "2.3.4"

    # Test from specification version
    mf_spec = "Manifest-Version: 1.0\nSpecification-Version: 3.4.5\n"
    mod_spec = ManifestParser.parse_fabric(content, jar_filename="test.jar", manifest_mf=mf_spec)
    assert mod_spec.version == "3.4.5"

    # Test from filename
    mod_fn = ManifestParser.parse_fabric(content, jar_filename="my-mod-1.20.1-4.5.6.jar")
    assert mod_fn.version == "1.20.1-4.5.6"

    # Fallback default
    mod_def = ManifestParser.parse_fabric(content, jar_filename="plain.jar")
    assert mod_def.version == "1.0.0"


def test_quilt_parsing():
    content = """{
        "schema_version": 1,
        "quilt_loader": {
            "id": "quilt_sample",
            "version": "1.0.0",
            "metadata": {
                "name": "Quilt Sample Mod",
                "description": "Quilt desc"
            },
            "depends": [
                "quilt_loader",
                {"id": "minecraft", "versions": ["1.20.1"]}
            ],
            "breaks": [
                "conflict_mod",
                {"id": "broken_mod", "versions": "<1.0"}
            ],
            "mixin": [
                "quilt.mixins.json"
            ]
        }
    }"""
    mods = ManifestParser.parse_manifest_content(content, "quilt.mod.json")
    assert len(mods) == 1
    m = mods[0]
    assert m.id == "quilt_sample"
    assert m.name == "Quilt Sample Mod"
    assert m.loader == LoaderType.QUILT
    assert len(m.mixin_configs) == 1
    assert m.mixin_configs[0].config_file == "quilt.mixins.json"
    dep_ids = {d.mod_id: d.dep_type for d in m.dependencies}
    assert dep_ids["quilt_loader"] == DepType.REQUIRED
    assert dep_ids["minecraft"] == DepType.REQUIRED
    assert dep_ids["conflict_mod"] == DepType.BREAKS
    assert dep_ids["broken_mod"] == DepType.BREAKS


def test_quilt_single_mixin_string():
    content = """{
        "quilt_loader": {
            "id": "q1",
            "mixin": "single.mixins.json"
        }
    }"""
    m = ManifestParser.parse_quilt(content)
    assert len(m.mixin_configs) == 1
    assert m.mixin_configs[0].config_file == "single.mixins.json"


def test_quilt_missing_id():
    with pytest.raises(ValueError, match="Missing 'quilt_loader.id'"):
        ManifestParser.parse_quilt('{"quilt_loader": {}}')


def test_forge_parsing_multiple_mods():
    toml_str = """
modLoader="javafml"
loaderVersion="[40,)"

[[mods]]
modId="forge_first"
version="1.0.0"
displayName="Forge First"
displayTest="IGNORE_SERVER_VERSION"
authors="Dev1, Dev2"

[[mods]]
modId="forge_second"
version="2.0.0"
displayName="Forge Second"
displayTest="MATCH_VERSION"

[[dependencies.forge_first]]
modId="forge"
mandatory=true
versionRange="[40.0,)"
ordering="NONE"
side="BOTH"

[[dependencies.forge_first]]
modId="optional_dep"
mandatory=false
versionRange="*"
side="CLIENT"
"""
    mods = ManifestParser.parse_manifest_content(toml_str, "META-INF/mods.toml")
    assert len(mods) == 2

    m1 = mods[0]
    assert m1.id == "forge_first"
    assert m1.environment == Environment.CLIENT
    assert m1.authors == ["Dev1", "Dev2"]
    assert len(m1.dependencies) == 2
    assert m1.dependencies[0].mod_id == "forge"
    assert m1.dependencies[0].dep_type == DepType.REQUIRED
    assert m1.dependencies[1].mod_id == "optional_dep"
    assert m1.dependencies[1].dep_type == DepType.OPTIONAL
    assert m1.dependencies[1].side == Environment.CLIENT

    m2 = mods[1]
    assert m2.id == "forge_second"
    assert m2.environment == Environment.UNIVERSAL


def test_forge_missing_mods_section():
    with pytest.raises(ValueError, match="No \\[\\[mods\\]\\] section found"):
        ManifestParser.parse_forge_toml('modLoader="javafml"')


def test_neoforge_parsing():
    toml_str = """
modLoader="javafml"
loaderVersion="[1,)"

[[mods]]
modId="neoforge_mod"
version="1.0.0"
displayName="NeoForge Mod"
clientOnly=true
authors="NeoDev"

[[dependencies.neoforge_mod]]
modId="neoforge"
type="required"
versionRange="[20.4,)"
side="BOTH"

[[dependencies.neoforge_mod]]
modId="opt_neo"
type="optional"
versionRange="*"

[[dependencies.neoforge_mod]]
modId="bad_neo"
type="incompatible"
versionRange="*"

[[dependencies.neoforge_mod]]
modId="disc_neo"
type="discouraged"
versionRange="*"

[[dependencies.neoforge_mod]]
modId="other_neo"
type="custom"
versionRange="*"
"""
    mods = ManifestParser.parse_manifest_content(toml_str, "META-INF/neoforge.mods.toml")
    assert len(mods) == 1
    m = mods[0]
    assert m.id == "neoforge_mod"
    assert m.loader == LoaderType.NEOFORGE
    assert m.environment == Environment.CLIENT

    types = {d.mod_id: d.dep_type for d in m.dependencies}
    assert types["neoforge"] == DepType.REQUIRED
    assert types["opt_neo"] == DepType.OPTIONAL
    assert types["bad_neo"] == DepType.CONFLICT
    assert types["disc_neo"] == DepType.DISCOURAGED
    assert types["other_neo"] == DepType.REQUIRED


def test_fabric_corner_cases():
    content = """{
        "id": "corner_mod",
        "depends": {"int_dep": 123},
        "recommends": null,
        "entrypoints": {
            "main": "com.example.DirectString",
            "ignored": 123
        },
        "mixins": [{"not_config": "foo"}, 42],
        "jars": [{"no_file": "bar"}, "string_jar"],
        "authors": [{"no_name": "baz"}, 123]
    }"""
    mod = ManifestParser.parse_fabric(content)
    assert mod.id == "corner_mod"
    assert mod.entrypoints["main"] == ["com.example.DirectString"]
    assert "ignored" not in mod.entrypoints
    assert mod.dependencies[0].mod_id == "int_dep"
    assert mod.dependencies[0].version_range == "*"
    assert len(mod.mixin_configs) == 0
    assert len(mod.nested_jars) == 0
    assert len(mod.authors) == 0


def test_quilt_corner_cases():
    content = """{
        "quilt_loader": {
            "id": "quilt_corner",
            "depends": [42, {"id": "str_ver_dep", "versions": ">=1.0"}],
            "breaks": [99],
            "mixin": [123]
        }
    }"""
    mod = ManifestParser.parse_quilt(content)
    assert mod.id == "quilt_corner"
    assert len(mod.dependencies) == 1
    assert mod.dependencies[0].mod_id == "str_ver_dep"
    assert mod.dependencies[0].version_range == ">=1.0"
    assert len(mod.mixin_configs) == 0


def test_forge_corner_cases():
    toml_str = """
modLoader="javafml"

[[mods]]
# Missing modId -> skipped

[[mods]]
modId="valid_mod"
# Missing version -> resolved to default

[dependencies]
# dependencies is not list
valid_mod = "not_a_list"
"""
    mods = ManifestParser.parse_forge_toml(toml_str)
    assert len(mods) == 1
    assert mods[0].id == "valid_mod"
    assert mods[0].version == "1.0.0"

    # Dependency with empty modId
    deps = []
    ManifestParser._parse_forge_dep(deps, {"modId": ""})
    assert len(deps) == 0


def test_neoforge_missing_mods():
    with pytest.raises(ValueError, match="No \\[\\[mods\\]\\] section found"):
        ManifestParser.parse_neoforge_toml('modLoader="javafml"')


def test_fabric_null_fields():
    content = """{
        "id": "null_fields_mod",
        "provides": null,
        "mixins": null,
        "entrypoints": null,
        "jars": null,
        "authors": null
    }"""
    mod = ManifestParser.parse_fabric(content)
    assert mod.id == "null_fields_mod"
    assert mod.provides == []
    assert mod.mixin_configs == []
    assert mod.entrypoints == {}
    assert mod.nested_jars == []
    assert mod.authors == []


def test_quilt_null_fields():
    content = """{
        "quilt_loader": {
            "id": "quilt_null",
            "depends": null,
            "breaks": null,
            "mixin": null
        }
    }"""
    mod = ManifestParser.parse_quilt(content)
    assert mod.id == "quilt_null"
    assert mod.dependencies == []
    assert mod.mixin_configs == []


def test_forge_non_dict_dep_entry():
    toml_str = """
modLoader="javafml"
[[mods]]
modId="forge_test"

[dependencies]
forge_test = ["not_a_dict"]
"""
    mods = ManifestParser.parse_forge_toml(toml_str)
    assert len(mods) == 1
    assert len(mods[0].dependencies) == 0


def test_neoforge_non_dict_dep_entry():
    toml_str = """
modLoader="javafml"
[[mods]]
# Skipped because no modId
displayName="No ModId"

[[mods]]
modId="no_version_mod"

[[mods]]
modId="neoforge_test"
version="1.0.0"

[dependencies]
# String not list to test 412->417
no_version_mod = "not_a_list"
# List with both non-dict and valid dict to cover 414->413
neoforge_test = ["not_a_dict", { modId = "neo_dep" }]
"""
    mods = ManifestParser.parse_neoforge_toml(toml_str)
    assert len(mods) == 2
    assert mods[0].id == "no_version_mod"
    assert mods[0].version == "1.0.0"
    assert len(mods[0].dependencies) == 0
    assert mods[1].id == "neoforge_test"
    assert len(mods[1].dependencies) == 1
    assert mods[1].dependencies[0].mod_id == "neo_dep"

    # Test _parse_neoforge_dep with no modId to hit line 447
    deps = []
    ManifestParser._parse_neoforge_dep(deps, {"type": "required"})
    assert len(deps) == 0


def test_resolve_version_manifest_lines():
    # Lines without colon and irrelevant keys
    mf = "Manifest-Version: 1.0\nCreated-By: Gradle\nSomeLineWithoutColon\n"
    ver = ManifestParser._resolve_version("", "mod.jar", mf)
    assert ver == "1.0.0"

