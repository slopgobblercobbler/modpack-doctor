"""Mixin configuration inspector and collision candidate detector."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from modpack_doctor.models import (
    DiagnosticIssue,
    IssueCode,
    IssueSeverity,
    MixinInfo,
    ModInfo,
)

# Critical Minecraft classes where mixin injection conflicts commonly crash games
HIGH_RISK_CLASSES = {
    "net.minecraft.client.MinecraftClient",
    "net.minecraft.client.Minecraft",
    "net.minecraft.client.gui.screen.TitleScreen",
    "net.minecraft.client.renderer.GameRenderer",
    "net.minecraft.server.network.ServerPlayNetworkHandler",
    "net.minecraft.server.network.ServerGamePacketListenerImpl",
    "net.minecraft.world.entity.player.Player",
    "net.minecraft.entity.player.PlayerEntity",
    "net.minecraft.world.level.Level",
    "net.minecraft.world.World",
}


class MixinAnalyzer:
    """Analyzes Mixin configurations across mods and flags collision risks."""

    @classmethod
    def parse_mixin_json(cls, json_str: str, config_filename: str) -> MixinInfo:
        """Parse mixin JSON string into MixinInfo."""
        try:
            data = json.loads(json_str)
        except Exception:
            return MixinInfo(config_file=config_filename)

        package = data.get("package", "")
        mixins = [str(m) for m in data.get("mixins", []) if m]
        client_mixins = [str(m) for m in data.get("client", []) if m]
        server_mixins = [str(m) for m in data.get("server", []) if m]
        compat = data.get("compatibilityLevel")

        return MixinInfo(
            config_file=config_filename,
            package=package,
            mixins=mixins,
            client_mixins=client_mixins,
            server_mixins=server_mixins,
            compatibility_level=compat,
        )

    @classmethod
    def detect_collisions(cls, mods: List[ModInfo]) -> List[DiagnosticIssue]:
        """Detect mixin collisions across mods."""
        issues: List[DiagnosticIssue] = []

        # 1. Check for generic mixin config filenames (e.g. "mixins.json")
        # In Fabric and Forge, identical mixin config names overwrite or collide in classloader!
        config_to_mods: Dict[str, List[ModInfo]] = defaultdict(list)
        for mod in mods:
            for mixin_cfg in mod.mixin_configs:
                cfg_name = mixin_cfg.config_file.split("/")[-1].split("\\")[-1]
                config_to_mods[cfg_name].append(mod)

        for cfg_name, mod_list in config_to_mods.items():
            if len(mod_list) > 1:
                # If generic name like "mixins.json" or collision of custom name
                severity = IssueSeverity.CRITICAL if cfg_name in ("mixins.json", "mixin.json") else IssueSeverity.WARNING
                mod_ids = ", ".join(m.id for m in mod_list)
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.MIXIN_COLLISION,
                        severity=severity,
                        message=f"Duplicate Mixin config filename '{cfg_name}' shared by multiple mods: {mod_ids}.",
                        mod_id=mod_list[0].id,
                        related_mod_id=mod_list[1].id,
                        file_path=mod_list[0].file_path,
                        recommendation=f"Rename mixin config in one of the mods to avoid classloader collision (e.g., '<modid>.mixins.json').",
                    )
                )

        # 2. Check for fully-qualified mixin class overlaps
        fq_class_to_mods: Dict[str, List[Tuple[ModInfo, str]]] = defaultdict(list)
        for mod in mods:
            for mixin_cfg in mod.mixin_configs:
                pkg = mixin_cfg.package.strip()
                for cls_name in mixin_cfg.all_mixins():
                    full_name = f"{pkg}.{cls_name}" if pkg else cls_name
                    fq_class_to_mods[full_name].append((mod, mixin_cfg.config_file))

        for full_cls, occurrences in fq_class_to_mods.items():
            # Check if different mods define the identical mixin class name
            unique_mods = {mod.id: mod for mod, _ in occurrences}
            if len(unique_mods) > 1:
                mod_list = list(unique_mods.values())
                issues.append(
                    DiagnosticIssue(
                        code=IssueCode.MIXIN_COLLISION,
                        severity=IssueSeverity.CRITICAL,
                        message=f"Identical Mixin class name '{full_cls}' defined by multiple mods: {', '.join(unique_mods.keys())}.",
                        mod_id=mod_list[0].id,
                        related_mod_id=mod_list[1].id,
                        file_path=mod_list[0].file_path,
                        recommendation="Two mods have identical mixin class paths, causing JVM class collision.",
                    )
                )

        return issues
