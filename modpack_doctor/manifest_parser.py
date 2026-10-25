"""Manifest parsers for Fabric, Forge, NeoForge, and Quilt mods."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib  # type: ignore[import-not-found]
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from modpack_doctor.models import (
    Dependency,
    DepType,
    Environment,
    LoaderType,
    MixinInfo,
    ModInfo,
)


class ManifestParser:
    """Parses various mod loader manifest formats into standardized ModInfo."""

    @classmethod
    def parse_manifest_content(
        cls,
        content: str,
        manifest_filename: str,
        jar_filename: str = "",
        jar_path: str = "",
        manifest_mf: str = "",
        file_size: int = 0,
    ) -> List[ModInfo]:
        """Parse raw manifest content string based on manifest filename."""
        fname = manifest_filename.replace("\\", "/").strip().lower()

        if fname.endswith("fabric.mod.json"):
            return [cls.parse_fabric(content, jar_filename, jar_path, manifest_mf, file_size)]
        if fname.endswith("quilt.mod.json"):
            return [cls.parse_quilt(content, jar_filename, jar_path, manifest_mf, file_size)]
        if fname.endswith("neoforge.mods.toml"):
            return cls.parse_neoforge_toml(content, jar_filename, jar_path, manifest_mf, file_size)
        if fname.endswith("mods.toml"):
            return cls.parse_forge_toml(content, jar_filename, jar_path, manifest_mf, file_size)

        raise ValueError(f"Unrecognized manifest type: {manifest_filename}")

    # ==========================
    # FABRIC PARSER
    # ==========================

    @classmethod
    def parse_fabric(
        cls,
        json_content: str,
        jar_filename: str = "",
        jar_path: str = "",
        manifest_mf: str = "",
        file_size: int = 0,
    ) -> ModInfo:
        """Parse fabric.mod.json."""
        data = json.loads(json_content)
        mod_id = data.get("id", "")
        if not mod_id:
            raise ValueError("Missing 'id' in fabric.mod.json")

        name = data.get("name", mod_id)
        version = data.get("version", "")
        if not version or version.startswith("${"):
            version = cls._resolve_version(version, jar_filename, manifest_mf)

        # Environment
        env_raw = data.get("environment", "*")
        env = Environment.from_str(env_raw)

        # Dependencies
        dependencies: List[Dependency] = []
        cls._add_fabric_deps(dependencies, data.get("depends", {}), DepType.REQUIRED)
        cls._add_fabric_deps(dependencies, data.get("recommends", {}), DepType.RECOMMENDED)
        cls._add_fabric_deps(dependencies, data.get("suggests", {}), DepType.SUGGESTED)
        cls._add_fabric_deps(dependencies, data.get("conflicts", {}), DepType.CONFLICT)
        cls._add_fabric_deps(dependencies, data.get("breaks", {}), DepType.BREAKS)

        # Provides
        provides_list: List[str] = []
        provides_raw = data.get("provides", [])
        if isinstance(provides_raw, list):
            provides_list.extend(str(p) for p in provides_raw)
        elif isinstance(provides_raw, dict):
            provides_list.extend(str(k) for k in provides_raw.keys())

        # Mixins
        mixin_infos: List[MixinInfo] = []
        mixins_raw = data.get("mixins", [])
        if isinstance(mixins_raw, list):
            for m in mixins_raw:
                if isinstance(m, str):
                    mixin_infos.append(MixinInfo(config_file=m))
                elif isinstance(m, dict) and "config" in m:
                    mixin_infos.append(MixinInfo(config_file=m["config"]))

        # Entrypoints
        entrypoints: Dict[str, List[str]] = {}
        raw_ep = data.get("entrypoints", {})
        if isinstance(raw_ep, dict):
            for ep_name, ep_val in raw_ep.items():
                if isinstance(ep_val, list):
                    entrypoints[ep_name] = [
                        (v.get("value", "") if isinstance(v, dict) else str(v))
                        for v in ep_val
                    ]
                elif isinstance(ep_val, str):
                    entrypoints[ep_name] = [ep_val]

        # Nested JARs
        nested: List[str] = []
        jars_raw = data.get("jars", [])
        if isinstance(jars_raw, list):
            for item in jars_raw:
                if isinstance(item, dict) and "file" in item:
                    nested.append(item["file"])

        # Authors
        authors: List[str] = []
        authors_raw = data.get("authors", [])
        if isinstance(authors_raw, list):
            for a in authors_raw:
                if isinstance(a, str):
                    authors.append(a)
                elif isinstance(a, dict) and "name" in a:
                    authors.append(a["name"])

        return ModInfo(
            id=mod_id,
            name=name,
            version=version,
            loader=LoaderType.FABRIC,
            file_path=jar_path,
            file_name=jar_filename,
            file_size=file_size,
            environment=env,
            dependencies=dependencies,
            provides=provides_list,
            mixin_configs=mixin_infos,
            entrypoints=entrypoints,
            description=data.get("description", ""),
            authors=authors,
            nested_jars=nested,
            raw_metadata=data,
        )

    @classmethod
    def _add_fabric_deps(
        cls,
        dep_list: List[Dependency],
        raw: Any,
        dep_type: DepType,
    ) -> None:
        """Helper to append Fabric dependencies from dict or list."""
        if isinstance(raw, dict):
            for dep_id, ver_spec in raw.items():
                if isinstance(ver_spec, list):
                    ver_spec = " ".join(str(v) for v in ver_spec)
                elif not isinstance(ver_spec, str):
                    ver_spec = "*"
                dep_list.append(
                    Dependency(
                        mod_id=dep_id,
                        version_range=ver_spec or "*",
                        dep_type=dep_type,
                    )
                )
        elif isinstance(raw, list):
            for dep_id in raw:
                dep_list.append(
                    Dependency(
                        mod_id=str(dep_id),
                        version_range="*",
                        dep_type=dep_type,
                    )
                )

    # ==========================
    # QUILT PARSER
    # ==========================

    @classmethod
    def parse_quilt(
        cls,
        json_content: str,
        jar_filename: str = "",
        jar_path: str = "",
        manifest_mf: str = "",
        file_size: int = 0,
    ) -> ModInfo:
        """Parse quilt.mod.json."""
        data = json.loads(json_content)
        loader_data = data.get("quilt_loader", {})
        mod_id = loader_data.get("id", "")
        if not mod_id:
            raise ValueError("Missing 'quilt_loader.id' in quilt.mod.json")

        meta = loader_data.get("metadata", {})
        name = meta.get("name", mod_id)
        version = loader_data.get("version", "")
        if not version or version.startswith("${"):
            version = cls._resolve_version(version, jar_filename, manifest_mf)

        # Quilt dependencies
        dependencies: List[Dependency] = []
        raw_deps = loader_data.get("depends", [])
        if isinstance(raw_deps, list):
            for item in raw_deps:
                if isinstance(item, str):
                    dependencies.append(Dependency(mod_id=item, dep_type=DepType.REQUIRED))
                elif isinstance(item, dict) and "id" in item:
                    ver_range = item.get("versions", "*")
                    if isinstance(ver_range, list):
                        ver_range = " ".join(str(v) for v in ver_range)
                    dependencies.append(
                        Dependency(
                            mod_id=item["id"],
                            version_range=str(ver_range),
                            dep_type=DepType.REQUIRED,
                        )
                    )

        raw_breaks = loader_data.get("breaks", [])
        if isinstance(raw_breaks, list):
            for item in raw_breaks:
                if isinstance(item, str):
                    dependencies.append(Dependency(mod_id=item, dep_type=DepType.BREAKS))
                elif isinstance(item, dict) and "id" in item:
                    dependencies.append(
                        Dependency(
                            mod_id=item["id"],
                            version_range=str(item.get("versions", "*")),
                            dep_type=DepType.BREAKS,
                        )
                    )

        # Mixins
        mixin_infos: List[MixinInfo] = []
        raw_mixins = loader_data.get("mixin", [])
        if isinstance(raw_mixins, str):
            mixin_infos.append(MixinInfo(config_file=raw_mixins))
        elif isinstance(raw_mixins, list):
            for m in raw_mixins:
                if isinstance(m, str):
                    mixin_infos.append(MixinInfo(config_file=m))

        return ModInfo(
            id=mod_id,
            name=name,
            version=version,
            loader=LoaderType.QUILT,
            file_path=jar_path,
            file_name=jar_filename,
            file_size=file_size,
            environment=Environment.UNIVERSAL,
            dependencies=dependencies,
            provides=[],
            mixin_configs=mixin_infos,
            entrypoints={},
            description=meta.get("description", ""),
            authors=[],
            nested_jars=[],
            raw_metadata=data,
        )

    # ==========================
    # FORGE TOML PARSER
    # ==========================

    @classmethod
    def parse_forge_toml(
        cls,
        toml_content: str,
        jar_filename: str = "",
        jar_path: str = "",
        manifest_mf: str = "",
        file_size: int = 0,
    ) -> List[ModInfo]:
        """Parse Forge META-INF/mods.toml (may contain multiple [[mods]])."""
        data = tomllib.loads(toml_content)
        mods_raw = data.get("mods", [])
        if not mods_raw:
            raise ValueError("No [[mods]] section found in mods.toml")

        # Global dependencies map: [dependencies.<modId>] or [[dependencies.<modId>]]
        raw_deps_map = data.get("dependencies", {})

        result: List[ModInfo] = []
        for mod_dict in mods_raw:
            mod_id = mod_dict.get("modId", "")
            if not mod_id:
                continue

            name = mod_dict.get("displayName", mod_id)
            version = mod_dict.get("version", "")
            if not version or version.startswith("${"):
                version = cls._resolve_version(version, jar_filename, manifest_mf)

            # Forge environment detection from displayTest
            # "IGNORE_SERVER_VERSION" typically means client-only mod (e.g. Sodium/Rubidium, AppleSkin)
            display_test = mod_dict.get("displayTest", "")
            env = Environment.UNIVERSAL
            if display_test == "IGNORE_SERVER_VERSION":
                env = Environment.CLIENT

            # Dependencies for this modId
            dependencies: List[Dependency] = []
            mod_deps = raw_deps_map.get(mod_id, [])
            if isinstance(mod_deps, list):
                for dep_entry in mod_deps:
                    if isinstance(dep_entry, dict):
                        cls._parse_forge_dep(dependencies, dep_entry)

            # Authors
            authors_str = mod_dict.get("authors", "")
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]

            result.append(
                ModInfo(
                    id=mod_id,
                    name=name,
                    version=version,
                    loader=LoaderType.FORGE,
                    file_path=jar_path,
                    file_name=jar_filename,
                    file_size=file_size,
                    environment=env,
                    dependencies=dependencies,
                    provides=[],
                    mixin_configs=[],
                    entrypoints={},
                    description=mod_dict.get("description", ""),
                    authors=authors,
                    nested_jars=[],
                    raw_metadata=mod_dict,
                )
            )

        return result

    @classmethod
    def _parse_forge_dep(cls, dep_list: List[Dependency], dep_dict: Dict[str, Any]) -> None:
        dep_id = dep_dict.get("modId")
        if not dep_id:
            return

        mandatory = dep_dict.get("mandatory", True)
        version_range = dep_dict.get("versionRange", "*")
        ordering = dep_dict.get("ordering", "NONE")
        side_raw = dep_dict.get("side", "BOTH")

        dep_type = DepType.REQUIRED if mandatory else DepType.OPTIONAL
        side = Environment.from_str(side_raw)

        dep_list.append(
            Dependency(
                mod_id=dep_id,
                version_range=version_range,
                dep_type=dep_type,
                side=side,
                ordering=ordering,
            )
        )

    # ==========================
    # NEOFORGE TOML PARSER
    # ==========================

    @classmethod
    def parse_neoforge_toml(
        cls,
        toml_content: str,
        jar_filename: str = "",
        jar_path: str = "",
        manifest_mf: str = "",
        file_size: int = 0,
    ) -> List[ModInfo]:
        """Parse NeoForge META-INF/neoforge.mods.toml."""
        data = tomllib.loads(toml_content)
        mods_raw = data.get("mods", [])
        if not mods_raw:
            raise ValueError("No [[mods]] section found in neoforge.mods.toml")

        raw_deps_map = data.get("dependencies", {})
        result: List[ModInfo] = []

        for mod_dict in mods_raw:
            mod_id = mod_dict.get("modId", "")
            if not mod_id:
                continue

            name = mod_dict.get("displayName", mod_id)
            version = mod_dict.get("version", "")
            if not version or version.startswith("${"):
                version = cls._resolve_version(version, jar_filename, manifest_mf)

            # Client only flag
            client_only = mod_dict.get("clientOnly", False)
            env = Environment.CLIENT if client_only else Environment.UNIVERSAL

            # Dependencies
            dependencies: List[Dependency] = []
            mod_deps = raw_deps_map.get(mod_id, [])
            if isinstance(mod_deps, list):
                for dep_entry in mod_deps:
                    if isinstance(dep_entry, dict):
                        cls._parse_neoforge_dep(dependencies, dep_entry)

            authors_str = mod_dict.get("authors", "")
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]

            result.append(
                ModInfo(
                    id=mod_id,
                    name=name,
                    version=version,
                    loader=LoaderType.NEOFORGE,
                    file_path=jar_path,
                    file_name=jar_filename,
                    file_size=file_size,
                    environment=env,
                    dependencies=dependencies,
                    provides=[],
                    mixin_configs=[],
                    entrypoints={},
                    description=mod_dict.get("description", ""),
                    authors=authors,
                    nested_jars=[],
                    raw_metadata=mod_dict,
                )
            )

        return result

    @classmethod
    def _parse_neoforge_dep(cls, dep_list: List[Dependency], dep_dict: Dict[str, Any]) -> None:
        dep_id = dep_dict.get("modId")
        if not dep_id:
            return

        type_str = dep_dict.get("type", "required").lower()
        if type_str == "required":
            dep_type = DepType.REQUIRED
        elif type_str == "optional":
            dep_type = DepType.OPTIONAL
        elif type_str == "incompatible":
            dep_type = DepType.CONFLICT
        elif type_str == "discouraged":
            dep_type = DepType.DISCOURAGED
        else:
            dep_type = DepType.REQUIRED

        version_range = dep_dict.get("versionRange", "*")
        side_raw = dep_dict.get("side", "BOTH")
        side = Environment.from_str(side_raw)

        dep_list.append(
            Dependency(
                mod_id=dep_id,
                version_range=version_range,
                dep_type=dep_type,
                side=side,
            )
        )

    # ==========================
    # VERSION RESOLUTION
    # ==========================

    @classmethod
    def _resolve_version(cls, version: str, filename: str, manifest_mf: str) -> str:
        """Resolve dynamic placeholder version strings like ${file.jarVersion}."""
        # Check MANIFEST.MF first
        if manifest_mf:
            for line in manifest_mf.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    if key in ("Implementation-Version", "Specification-Version") and val:
                        return val

        # Try extracting version pattern from jar filename, e.g. "my-mod-1.20.1-1.4.0.jar"
        if filename:
            # Match version numbers at the end of filename
            match = re.search(r"[-_v]([0-9]+(?:\.[0-9]+)+(?:[.-][a-zA-Z0-9.]+)?)\.jar$", filename)
            if match:
                return match.group(1)

        return "1.0.0"
