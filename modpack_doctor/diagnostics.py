"""Diagnostic analysis engine for Minecraft modpacks."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from modpack_doctor.graph import ModDependencyGraph
from modpack_doctor.mixin_analyzer import MixinAnalyzer
from modpack_doctor.models import (
    Dependency,
    DepType,
    DiagnosisReport,
    DiagnosticIssue,
    Environment,
    IssueCode,
    IssueSeverity,
    LoaderType,
    ModInfo,
)
from modpack_doctor.reader import ModpackScanner
from modpack_doctor.version_matcher import VersionMatcher

# Virtual mod/platform IDs that represent runtime environments rather than mod JARs
VIRTUAL_PLATFORM_MODS = {
    "minecraft": "Minecraft game client/server",
    "java": "Java Virtual Machine",
    "fabricloader": "Fabric Loader",
    "fabric": "Fabric API / Loader",
    "forge": "Minecraft Forge",
    "neoforge": "NeoForge Loader",
    "quilt_loader": "Quilt Loader",
}


class DiagnosticEngine:
    """Core diagnostic engine inspecting mods, dependencies, collisions, and side mismatches."""

    def __init__(
        self,
        target_env: str = "both",
        minecraft_version: Optional[str] = None,
        loader_version: Optional[str] = None,
        java_version: Optional[str] = None,
    ) -> None:
        self.target_env = target_env.lower().strip() if target_env else "both"
        self.minecraft_version = minecraft_version.strip() if minecraft_version else None
        self.loader_version = loader_version.strip() if loader_version else None
        self.java_version = java_version.strip() if java_version else None

    def diagnose_directory(
        self,
        dir_path: Path,
        recursive: bool = False,
    ) -> DiagnosisReport:
        """Scan directory and run comprehensive diagnostic analysis."""
        start_time = time.perf_counter()

        mods, read_issues = ModpackScanner.scan_directory(dir_path, recursive=recursive)

        # Run diagnostic checks
        analysis_issues = self.diagnose_mods(mods)
        all_issues = read_issues + analysis_issues

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return DiagnosisReport(
            scanned_path=str(dir_path),
            target_env=self.target_env,
            minecraft_version=self.minecraft_version,
            mods=mods,
            issues=all_issues,
            scan_duration_ms=duration_ms,
        )

    def diagnose_mods(self, mods: List[ModInfo]) -> List[DiagnosticIssue]:
        """Perform all diagnostic checks on a list of scanned mods."""
        issues: List[DiagnosticIssue] = []

        if not mods:
            return issues

        graph = ModDependencyGraph.from_mods(mods)

        # 1. Duplicate mods detection
        issues.extend(self._check_duplicates(mods))

        # 2. Dependency resolution and version compatibility
        issues.extend(self._check_dependencies(mods, graph))

        # 3. Client vs Server environment mismatches
        issues.extend(self._check_environment_mismatches(mods))

        # 4. Mixin collisions
        issues.extend(MixinAnalyzer.detect_collisions(mods))

        # 5. Circular dependencies
        issues.extend(self._check_cycles(graph))

        return issues

    def _check_duplicates(self, mods: List[ModInfo]) -> List[DiagnosticIssue]:
        """Detect duplicate mod IDs or multiple JARs providing identical mod."""
        issues: List[DiagnosticIssue] = []
        id_to_mods: Dict[str, List[ModInfo]] = defaultdict(list)

        for mod in mods:
            id_to_mods[mod.id].append(mod)

        for mod_id, mod_list in id_to_mods.items():
            if len(mod_list) > 1:
                files = ", ".join(f"{m.file_name} ({m.version})" for m in mod_list)
                unique_versions = {m.version for m in mod_list}
                severity = IssueSeverity.CRITICAL if len(unique_versions) > 1 else IssueSeverity.WARNING
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.DUPLICATE_MOD,
                        severity=severity,
                        message=f"Duplicate mod ID '{mod_id}' discovered in multiple JARs: {files}",
                        mod_id=mod_id,
                        file_path=mod_list[0].file_path,
                        recommendation="Remove conflicting or duplicate JAR files, leaving only one version.",
                    )
                )

        return issues

    def _check_dependencies(
        self,
        mods: List[ModInfo],
        graph: ModDependencyGraph,
    ) -> List[DiagnosticIssue]:
        """Check all required, conflicting, and breaking dependencies."""
        issues: List[DiagnosticIssue] = []

        for mod in mods:
            for dep in mod.dependencies:
                dep_id = dep.mod_id.lower()

                # Handle virtual platforms: minecraft, java, loader
                if dep_id in VIRTUAL_PLATFORM_MODS:
                    self._check_virtual_dependency(mod, dep, issues)
                    continue

                # Check conflict / breaks
                if dep.dep_type in (DepType.CONFLICT, DepType.BREAKS):
                    target_mod = graph.get_mod(dep.mod_id)
                    if target_mod:
                        # If version constraint matches or is wildcard
                        if not dep.version_range or dep.version_range == "*" or VersionMatcher.matches(target_mod.version, dep.version_range):
                            issues.append(
                                DiagnosticIssue(
                                    code=IssueCode.CONFLICT_DETECTED,
                                    severity=IssueSeverity.CRITICAL,
                                    message=f"Mod '{mod.id}' explicitly breaks/conflicts with '{target_mod.id}' ({target_mod.version}).",
                                    mod_id=mod.id,
                                    related_mod_id=target_mod.id,
                                    file_path=mod.file_path,
                                    recommendation=f"Remove either '{mod.id}' or '{target_mod.id}' to prevent crash.",
                                )
                            )
                    continue

                # Check required dependencies
                if dep.dep_type == DepType.REQUIRED:
                    target_mod = graph.get_mod(dep.mod_id)

                    # Missing dependency
                    if not target_mod:
                        # If side constraint doesn't apply to our target environment, skip
                        if self._should_skip_side(dep.side):
                            continue

                        issues.append(
                            DiagnosticIssue(
                                code=IssueCode.MISSING_DEPENDENCY,
                                severity=IssueSeverity.CRITICAL,
                                message=f"Mod '{mod.id}' requires missing dependency '{dep.mod_id}' (constraint: {dep.version_range}).",
                                mod_id=mod.id,
                                related_mod_id=dep.mod_id,
                                file_path=mod.file_path,
                                recommendation=f"Install '{dep.mod_id}' version satisfying '{dep.version_range}'.",
                            )
                        )
                        continue

                    # Incompatible version
                    if dep.version_range and dep.version_range != "*":
                        if not VersionMatcher.matches(target_mod.version, dep.version_range):
                            issues.append(
                                DiagnosticIssue(
                                    code=IssueCode.INCOMPATIBLE_VERSION,
                                    severity=IssueSeverity.CRITICAL,
                                    message=(
                                        f"Mod '{mod.id}' requires '{dep.mod_id}' matching '{dep.version_range}', "
                                        f"but found version '{target_mod.version}'."
                                    ),
                                    mod_id=mod.id,
                                    related_mod_id=target_mod.id,
                                    file_path=mod.file_path,
                                    recommendation=f"Update or downgrade '{target_mod.id}' to satisfy '{dep.version_range}'.",
                                )
                            )

                # Optional recommendations / suggestions
                elif dep.dep_type in (DepType.RECOMMENDED, DepType.SUGGESTED):
                    target_mod = graph.get_mod(dep.mod_id)
                    if not target_mod and not self._should_skip_side(dep.side):
                        issues.append(
                            DiagnosticIssue(
                                code=IssueCode.MISSING_DEPENDENCY,
                                severity=IssueSeverity.INFO,
                                message=f"Mod '{mod.id}' recommends optional mod '{dep.mod_id}'.",
                                mod_id=mod.id,
                                related_mod_id=dep.mod_id,
                                file_path=mod.file_path,
                                recommendation=f"Consider installing '{dep.mod_id}' for full feature support.",
                            )
                        )

        return issues

    def _check_virtual_dependency(
        self,
        mod: ModInfo,
        dep: Dependency,
        issues: List[DiagnosticIssue],
    ) -> None:
        """Validate dependencies against runtime platforms (minecraft, java, loader)."""
        dep_id = dep.mod_id.lower()

        # Check Minecraft version constraint
        if dep_id == "minecraft" and self.minecraft_version:
            if not VersionMatcher.matches(self.minecraft_version, dep.version_range):
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.INCOMPATIBLE_VERSION,
                        severity=IssueSeverity.CRITICAL,
                        message=(
                            f"Mod '{mod.id}' requires Minecraft '{dep.version_range}', "
                            f"but target Minecraft version is '{self.minecraft_version}'."
                        ),
                        mod_id=mod.id,
                        related_mod_id="minecraft",
                        file_path=mod.file_path,
                        recommendation=f"Obtain a version of '{mod.id}' compatible with Minecraft {self.minecraft_version}.",
                    )
                )

        # Check Java version constraint
        elif dep_id == "java" and self.java_version:
            if not VersionMatcher.matches(self.java_version, dep.version_range):
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.INCOMPATIBLE_VERSION,
                        severity=IssueSeverity.CRITICAL,
                        message=(
                            f"Mod '{mod.id}' requires Java '{dep.version_range}', "
                            f"but runtime Java version is '{self.java_version}'."
                        ),
                        mod_id=mod.id,
                        related_mod_id="java",
                        file_path=mod.file_path,
                        recommendation=f"Run Minecraft with Java {dep.version_range}.",
                    )
                )

        # Check Loader version constraint
        elif dep_id in ("fabricloader", "fabric", "forge", "neoforge") and self.loader_version:
            if not VersionMatcher.matches(self.loader_version, dep.version_range):
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.INCOMPATIBLE_VERSION,
                        severity=IssueSeverity.CRITICAL,
                        message=(
                            f"Mod '{mod.id}' requires {dep_id} '{dep.version_range}', "
                            f"but configured loader version is '{self.loader_version}'."
                        ),
                        mod_id=mod.id,
                        related_mod_id=dep_id,
                        file_path=mod.file_path,
                        recommendation=f"Update mod loader to satisfy {dep.version_range}.",
                    )
                )

    def _check_environment_mismatches(self, mods: List[ModInfo]) -> List[DiagnosticIssue]:
        """Detect client-only mods in server packs or server-only mods in client packs."""
        issues: List[DiagnosticIssue] = []

        if self.target_env == "both":
            return issues

        for mod in mods:
            if self.target_env == "server":
                # Check if mod is client-only
                is_client_only = (mod.environment == Environment.CLIENT)
                # If only client entrypoints and no main or server entrypoints
                if not is_client_only and mod.entrypoints:
                    has_client = "client" in mod.entrypoints
                    has_main = "main" in mod.entrypoints
                    has_server = "server" in mod.entrypoints
                    if has_client and not has_main and not has_server:
                        is_client_only = True

                if is_client_only:
                    issues.append(
                        DiagnosticIssue(
                            code=IssueCode.CLIENT_MOD_ON_SERVER,
                            severity=IssueSeverity.WARNING,
                            message=f"Client-only mod '{mod.id}' found in server-targeted modpack.",
                            mod_id=mod.id,
                            file_path=mod.file_path,
                            recommendation="Remove client-only mod from server mods folder to avoid crash.",
                        )
                    )

            elif self.target_env == "client":
                if mod.environment == Environment.SERVER:
                    issues.append(
                        DiagnosticIssue(
                            code=IssueCode.SERVER_MOD_ON_CLIENT,
                            severity=IssueSeverity.WARNING,
                            message=f"Server-only mod '{mod.id}' found in client-targeted modpack.",
                            mod_id=mod.id,
                            file_path=mod.file_path,
                            recommendation="Ensure this mod is not needed on client.",
                        )
                    )

        return issues

    def _check_cycles(self, graph: ModDependencyGraph) -> List[DiagnosticIssue]:
        """Check for dependency cycles."""
        issues: List[DiagnosticIssue] = []
        cycles = graph.detect_cycles()
        for cycle in cycles:
            chain = " -> ".join(cycle)
            issues.append(
                DiagnosticIssue(
                    code=IssueCode.CIRCULAR_DEPENDENCY,
                    severity=IssueSeverity.WARNING,
                    message=f"Circular dependency detected: {chain}",
                    mod_id=cycle[0],
                    recommendation="Review mod dependencies to break recursive dependency cycle.",
                )
            )
        return issues

    def _should_skip_side(self, side: Environment) -> bool:
        """Determine if a dependency should be skipped based on target environment."""
        if self.target_env == "server" and side == Environment.CLIENT:
            return True
        if self.target_env == "client" and side == Environment.SERVER:
            return True
        return False


# =====================================================================
# MODPACK DIFF ENGINE
# =====================================================================

def diff_modpacks(mods_a: List[ModInfo], mods_b: List[ModInfo]) -> List[Dict[str, Any]]:
    """Compare two mod lists and return diff entries."""
    map_a = {m.id: m for m in mods_a}
    map_b = {m.id: m for m in mods_b}
    all_ids = sorted(set(map_a.keys()) | set(map_b.keys()))

    diffs: List[Dict[str, Any]] = []
    for mod_id in all_ids:
        in_a = map_a.get(mod_id)
        in_b = map_b.get(mod_id)

        if in_a and not in_b:
            diffs.append({
                "mod_id": mod_id,
                "status": "removed",
                "old_version": in_a.version,
                "new_version": None,
                "old_file": in_a.file_name,
                "new_file": None,
            })
        elif not in_a and in_b:
            diffs.append({
                "mod_id": mod_id,
                "status": "added",
                "old_version": None,
                "new_version": in_b.version,
                "old_file": None,
                "new_file": in_b.file_name,
            })
        elif in_a and in_b:
            if in_a.version != in_b.version:
                diffs.append({
                    "mod_id": mod_id,
                    "status": "changed",
                    "old_version": in_a.version,
                    "new_version": in_b.version,
                    "old_file": in_a.file_name,
                    "new_file": in_b.file_name,
                })
            else:
                diffs.append({
                    "mod_id": mod_id,
                    "status": "unchanged",
                    "old_version": in_a.version,
                    "new_version": in_b.version,
                    "old_file": in_a.file_name,
                    "new_file": in_b.file_name,
                })

    return diffs
