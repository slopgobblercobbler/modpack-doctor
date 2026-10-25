"""Pytest fixtures and test helpers for creating realistic mock mod JARs."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest


def make_fabric_jar_bytes(
    mod_id: str,
    name: str = "Test Mod",
    version: str = "1.0.0",
    environment: str = "*",
    depends: Optional[Dict[str, Any]] = None,
    recommends: Optional[Dict[str, Any]] = None,
    suggests: Optional[Dict[str, Any]] = None,
    conflicts: Optional[Dict[str, Any]] = None,
    breaks: Optional[Dict[str, Any]] = None,
    provides: Optional[List[str]] = None,
    mixins: Optional[List[Any]] = None,
    entrypoints: Optional[Dict[str, Any]] = None,
    jars: Optional[List[Dict[str, str]]] = None,
    authors: Optional[List[Any]] = None,
    description: str = "Test description",
    nested_jar_files: Optional[Dict[str, bytes]] = None,
    mixin_files: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bytes:
    """Create in-memory bytes of a Fabric mod JAR."""
    manifest = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": name,
        "version": version,
        "environment": environment,
        "description": description,
    }
    if depends:
        manifest["depends"] = depends
    if recommends:
        manifest["recommends"] = recommends
    if suggests:
        manifest["suggests"] = suggests
    if conflicts:
        manifest["conflicts"] = conflicts
    if breaks:
        manifest["breaks"] = breaks
    if provides:
        manifest["provides"] = provides
    if mixins:
        manifest["mixins"] = mixins
    if entrypoints:
        manifest["entrypoints"] = entrypoints
    if jars:
        manifest["jars"] = jars
    if authors:
        manifest["authors"] = authors

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("fabric.mod.json", json.dumps(manifest, indent=2))

        if mixin_files:
            for filename, mixin_dict in mixin_files.items():
                zf.writestr(filename, json.dumps(mixin_dict, indent=2))

        if nested_jar_files:
            for nested_path, jar_bytes in nested_jar_files.items():
                zf.writestr(nested_path, jar_bytes)

    return buf.getvalue()


def make_forge_jar_bytes(
    mod_id: str,
    name: str = "Test Forge Mod",
    version: str = "1.0.0",
    display_test: str = "MATCH_VERSION",
    dependencies: Optional[List[Dict[str, Any]]] = None,
    authors: str = "Author Name",
    description: str = "Forge description",
    manifest_mf: Optional[str] = None,
    mixin_configs: Optional[List[str]] = None,
    mixin_files: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bytes:
    """Create in-memory bytes of a Forge mods.toml JAR."""
    toml_lines = [
        'modLoader="javafml"',
        'loaderVersion="[40,)"',
        'license="MIT"',
        '[[mods]]',
        f'modId="{mod_id}"',
        f'version="{version}"',
        f'displayName="{name}"',
        f'displayTest="{display_test}"',
        f'description="{description}"',
        f'authors="{authors}"',
    ]

    if dependencies:
        for dep in dependencies:
            toml_lines.append(f'[[dependencies.{mod_id}]]')
            toml_lines.append(f'modId="{dep.get("modId", "")}"')
            toml_lines.append(f'mandatory={str(dep.get("mandatory", True)).lower()}')
            toml_lines.append(f'versionRange="{dep.get("versionRange", "*")}"')
            toml_lines.append(f'ordering="{dep.get("ordering", "NONE")}"')
            toml_lines.append(f'side="{dep.get("side", "BOTH")}"')

    toml_content = "\n".join(toml_lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/mods.toml", toml_content)

        mf_lines = ["Manifest-Version: 1.0"]
        if manifest_mf:
            mf_lines.append(manifest_mf)
        if mixin_configs:
            mf_lines.append(f"MixinConfigs: {','.join(mixin_configs)}")
        zf.writestr("META-INF/MANIFEST.MF", "\n".join(mf_lines) + "\n")

        if mixin_files:
            for filename, mixin_dict in mixin_files.items():
                zf.writestr(filename, json.dumps(mixin_dict, indent=2))

    return buf.getvalue()


def make_neoforge_jar_bytes(
    mod_id: str,
    name: str = "Test NeoForge Mod",
    version: str = "1.0.0",
    client_only: bool = False,
    dependencies: Optional[List[Dict[str, Any]]] = None,
    authors: str = "Author Name",
    description: str = "NeoForge description",
) -> bytes:
    """Create in-memory bytes of a NeoForge neoforge.mods.toml JAR."""
    toml_lines = [
        'modLoader="javafml"',
        'loaderVersion="[1,)"',
        'license="MIT"',
        '[[mods]]',
        f'modId="{mod_id}"',
        f'version="{version}"',
        f'displayName="{name}"',
        f'clientOnly={str(client_only).lower()}',
        f'description="{description}"',
        f'authors="{authors}"',
    ]

    if dependencies:
        for dep in dependencies:
            toml_lines.append(f'[[dependencies.{mod_id}]]')
            toml_lines.append(f'modId="{dep.get("modId", "")}"')
            toml_lines.append(f'type="{dep.get("type", "required")}"')
            toml_lines.append(f'versionRange="{dep.get("versionRange", "*")}"')
            toml_lines.append(f'side="{dep.get("side", "BOTH")}"')

    toml_content = "\n".join(toml_lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/neoforge.mods.toml", toml_content)

    return buf.getvalue()


def make_quilt_jar_bytes(
    mod_id: str,
    name: str = "Test Quilt Mod",
    version: str = "1.0.0",
    depends: Optional[List[Any]] = None,
    breaks: Optional[List[Any]] = None,
    mixin: Optional[Any] = None,
) -> bytes:
    """Create in-memory bytes of a Quilt quilt.mod.json JAR."""
    data: Dict[str, Any] = {
        "schema_version": 1,
        "quilt_loader": {
            "id": mod_id,
            "version": version,
            "metadata": {
                "name": name,
                "description": "Quilt description",
            },
        },
    }
    if depends:
        data["quilt_loader"]["depends"] = depends
    if breaks:
        data["quilt_loader"]["breaks"] = breaks
    if mixin:
        data["quilt_loader"]["mixin"] = mixin

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("quilt.mod.json", json.dumps(data, indent=2))

    return buf.getvalue()
