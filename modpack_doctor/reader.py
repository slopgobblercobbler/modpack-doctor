"""Non-extracting streaming JAR and modpack directory reader."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from modpack_doctor.manifest_parser import ManifestParser
from modpack_doctor.mixin_analyzer import MixinAnalyzer
from modpack_doctor.models import (
    DiagnosticIssue,
    IssueCode,
    IssueSeverity,
    LoaderType,
    MixinInfo,
    ModInfo,
)


class JarReader:
    """Inspects JAR files directly from ZIP streams without extracting full archives to disk."""

    @classmethod
    def read_jar_file(cls, jar_path: Path) -> Tuple[List[ModInfo], List[DiagnosticIssue]]:
        """Read a JAR file and extract mod metadata and mixin configs in-memory."""
        issues: List[DiagnosticIssue] = []
        path_str = str(jar_path)
        file_name = jar_path.name

        if not jar_path.exists():
            issues.append(
                DiagnosticIssue(
                    code=IssueCode.CORRUPT_JAR,
                    severity=IssueSeverity.CRITICAL,
                    message=f"JAR file does not exist: {path_str}",
                    file_path=path_str,
                    recommendation="Verify the mod file path.",
                )
            )
            return [], issues

        try:
            file_size = jar_path.stat().st_size
        except OSError:
            file_size = 0

        try:
            with open(jar_path, "rb") as f:
                content_bytes = f.read()
            return cls.read_jar_bytes(content_bytes, file_name, path_str, file_size)
        except Exception as e:
            issues.append(
                DiagnosticIssue(
                    code=IssueCode.CORRUPT_JAR,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Failed to read JAR ({e}): {file_name}",
                    file_path=path_str,
                    recommendation="Check file permissions and integrity.",
                )
            )
            return [], issues

    @classmethod
    def read_jar_bytes(
        cls,
        data: bytes,
        file_name: str,
        file_path: str = "",
        file_size: int = 0,
    ) -> Tuple[List[ModInfo], List[DiagnosticIssue]]:
        """Read JAR from byte stream without extracting to disk."""
        issues: List[DiagnosticIssue] = []
        mods: List[ModInfo] = []

        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                namelist = zf.namelist()
                normalized_names = {name.lower(): name for name in namelist}

                # Read MANIFEST.MF if present
                manifest_mf = ""
                for mf_candidate in ("meta-inf/manifest.mf", "meta-inf/manifest.mf/"):
                    if mf_candidate in normalized_names:
                        manifest_mf = zf.read(normalized_names[mf_candidate]).decode("utf-8", errors="replace")
                        break

                # Search manifests in priority order
                # 1. fabric.mod.json
                # 2. quilt.mod.json
                # 3. META-INF/neoforge.mods.toml
                # 4. META-INF/mods.toml
                manifest_key = None
                if "fabric.mod.json" in normalized_names:
                    manifest_key = normalized_names["fabric.mod.json"]
                elif "quilt.mod.json" in normalized_names:
                    manifest_key = normalized_names["quilt.mod.json"]
                elif "meta-inf/neoforge.mods.toml" in normalized_names:
                    manifest_key = normalized_names["meta-inf/neoforge.mods.toml"]
                elif "meta-inf/mods.toml" in normalized_names:
                    manifest_key = normalized_names["meta-inf/mods.toml"]

                if not manifest_key:
                    issues.append(
                        DiagnosticIssue(
                            code=IssueCode.INVALID_MANIFEST,
                            severity=IssueSeverity.WARNING,
                            message=f"No recognized mod manifest (fabric.mod.json, mods.toml, neoforge.mods.toml) in {file_name}",
                            file_path=file_path,
                            recommendation="Check if this is a plain library or non-mod archive.",
                        )
                    )
                    return [], issues

                # Parse the manifest
                manifest_content = zf.read(manifest_key).decode("utf-8", errors="replace")
                try:
                    parsed_mods = ManifestParser.parse_manifest_content(
                        content=manifest_content,
                        manifest_filename=manifest_key,
                        jar_filename=file_name,
                        jar_path=file_path,
                        manifest_mf=manifest_mf,
                        file_size=file_size,
                    )
                except Exception as e:
                    issues.append(
                        DiagnosticIssue(
                            code=IssueCode.INVALID_MANIFEST,
                            severity=IssueSeverity.CRITICAL,
                            message=f"Failed to parse {manifest_key} in {file_name}: {e}",
                            file_path=file_path,
                            recommendation="Fix syntax or formatting error in manifest file.",
                        )
                    )
                    return [], issues

                # Extract and parse mixins
                cls._extract_mixins(zf, parsed_mods, manifest_mf)

                # Check for nested JARs (Fabric / JiJ)
                for mod in parsed_mods:
                    if mod.nested_jars:
                        for nested_path in mod.nested_jars:
                            nested_key = nested_path.replace("\\", "/")
                            if nested_key in namelist:
                                nested_bytes = zf.read(nested_key)
                                nested_mods, nested_issues = cls.read_jar_bytes(
                                    nested_bytes,
                                    file_name=Path(nested_path).name,
                                    file_path=f"{file_path}!/{nested_path}",
                                    file_size=len(nested_bytes),
                                )
                                mods.extend(nested_mods)
                                issues.extend(nested_issues)

                mods.extend(parsed_mods)
                return mods, issues

        except zipfile.BadZipFile as e:
            issues.append(
                DiagnosticIssue(
                    code=IssueCode.CORRUPT_JAR,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Corrupt or invalid ZIP archive ({e}): {file_name}",
                    file_path=file_path,
                    recommendation="Re-download or remove the corrupted JAR file.",
                )
            )
            return [], issues

    @classmethod
    def _extract_mixins(
        cls,
        zf: zipfile.ZipFile,
        mods: List[ModInfo],
        manifest_mf: str,
    ) -> None:
        """Read and parse mixin JSON files directly from ZIP stream."""
        namelist = zf.namelist()
        normalized_names = {name.lower(): name for name in namelist}

        # Check for mixin configs in MANIFEST.MF (Forge style)
        manifest_mixin_configs: List[str] = []
        if manifest_mf:
            for line in manifest_mf.splitlines():
                if line.lower().startswith("mixinconfigs:"):
                    parts = line.split(":", 1)[1].split(",")
                    manifest_mixin_configs.extend(p.strip() for p in parts if p.strip())

        for mod in mods:
            # Add manifest MF mixins if mod is Forge/NeoForge
            if mod.loader in (LoaderType.FORGE, LoaderType.NEOFORGE):
                for mf_cfg in manifest_mixin_configs:
                    if not any(m.config_file == mf_cfg for m in mod.mixin_configs):
                        mod.mixin_configs.append(MixinInfo(config_file=mf_cfg))

            # Now read actual contents of each declared mixin config
            detailed_mixins: List[MixinInfo] = []
            for mixin_entry in mod.mixin_configs:
                cfg_name = mixin_entry.config_file.replace("\\", "/")
                target_key = None
                if cfg_name in namelist:
                    target_key = cfg_name
                elif cfg_name.lower() in normalized_names:
                    target_key = normalized_names[cfg_name.lower()]

                if target_key:
                    content = zf.read(target_key).decode("utf-8", errors="replace")
                    parsed = MixinAnalyzer.parse_mixin_json(content, cfg_name)
                    detailed_mixins.append(parsed)
                else:
                    detailed_mixins.append(mixin_entry)

            mod.mixin_configs = detailed_mixins


class ModpackScanner:
    """Scans directories containing Minecraft mod JARs."""

    @classmethod
    def scan_directory(
        cls,
        dir_path: Path,
        recursive: bool = False,
    ) -> Tuple[List[ModInfo], List[DiagnosticIssue]]:
        """Scan a directory for .jar files and parse all discovered mods."""
        all_mods: List[ModInfo] = []
        all_issues: List[DiagnosticIssue] = []

        if not dir_path.exists():
            all_issues.append(
                DiagnosticIssue(
                    code=IssueCode.CORRUPT_JAR,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Directory does not exist: {dir_path}",
                    file_path=str(dir_path),
                    recommendation="Ensure the mod directory path is valid.",
                )
            )
            return all_mods, all_issues

        if dir_path.is_file():
            # If a single file was passed, inspect it
            return JarReader.read_jar_file(dir_path)

        jar_files: List[Path] = []
        if recursive:
            jar_files = sorted(dir_path.rglob("*.jar"))
        else:
            jar_files = sorted(dir_path.glob("*.jar"))

        for jar in jar_files:
            mods, issues = JarReader.read_jar_file(jar)
            all_mods.extend(mods)
            all_issues.extend(issues)

        return all_mods, all_issues
