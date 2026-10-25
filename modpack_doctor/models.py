"""Data models for modpack-doctor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoaderType(str, Enum):
    """Supported Minecraft mod loaders."""
    FABRIC = "fabric"
    FORGE = "forge"
    NEOFORGE = "neoforge"
    QUILT = "quilt"
    UNKNOWN = "unknown"


class Environment(str, Enum):
    """Execution environment side."""
    CLIENT = "client"
    SERVER = "server"
    UNIVERSAL = "both"

    @classmethod
    def from_str(cls, val: Optional[str]) -> Environment:
        """Parse environment side from string."""
        if not val:
            return cls.UNIVERSAL
        normalized = val.strip().lower()
        if normalized in ("client", "client_only", "clientonly"):
            return cls.CLIENT
        if normalized in ("server", "server_only", "serveronly", "dedicated_server"):
            return cls.SERVER
        return cls.UNIVERSAL


class DepType(str, Enum):
    """Dependency relationship type."""
    REQUIRED = "required"
    OPTIONAL = "optional"
    RECOMMENDED = "recommended"
    SUGGESTED = "suggested"
    CONFLICT = "conflict"
    BREAKS = "breaks"
    DISCOURAGED = "discouraged"


class IssueSeverity(str, Enum):
    """Severity level of diagnostic issues."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class IssueCode(str, Enum):
    """Standardized issue diagnostic codes."""
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    DUPLICATE_MOD = "DUPLICATE_MOD"
    CLIENT_MOD_ON_SERVER = "CLIENT_MOD_ON_SERVER"
    SERVER_MOD_ON_CLIENT = "SERVER_MOD_ON_CLIENT"
    MIXIN_COLLISION = "MIXIN_COLLISION"
    CORRUPT_JAR = "CORRUPT_JAR"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"


@dataclass
class Dependency:
    """Mod dependency specification."""
    mod_id: str
    version_range: str = "*"
    dep_type: DepType = DepType.REQUIRED
    side: Environment = Environment.UNIVERSAL
    ordering: str = "NONE"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mod_id": self.mod_id,
            "version_range": self.version_range,
            "dep_type": self.dep_type.value,
            "side": self.side.value,
            "ordering": self.ordering,
        }


@dataclass
class MixinInfo:
    """Mixin configuration metadata extracted from JAR."""
    config_file: str
    package: str = ""
    mixins: List[str] = field(default_factory=list)
    client_mixins: List[str] = field(default_factory=list)
    server_mixins: List[str] = field(default_factory=list)
    compatibility_level: Optional[str] = None

    def all_mixins(self) -> List[str]:
        """Return all mixin class names combined."""
        return self.mixins + self.client_mixins + self.server_mixins

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "config_file": self.config_file,
            "package": self.package,
            "mixins": list(self.mixins),
            "client_mixins": list(self.client_mixins),
            "server_mixins": list(self.server_mixins),
            "compatibility_level": self.compatibility_level,
        }


@dataclass
class ModInfo:
    """Complete metadata for a scanned Minecraft mod."""
    id: str
    name: str
    version: str
    loader: LoaderType
    file_path: str
    file_name: str
    file_size: int = 0
    environment: Environment = Environment.UNIVERSAL
    dependencies: List[Dependency] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    mixin_configs: List[MixinInfo] = field(default_factory=list)
    entrypoints: Dict[str, List[str]] = field(default_factory=dict)
    description: str = ""
    authors: List[str] = field(default_factory=list)
    nested_jars: List[str] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "loader": self.loader.value,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "environment": self.environment.value,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "provides": list(self.provides),
            "mixin_configs": [m.to_dict() for m in self.mixin_configs],
            "entrypoints": self.entrypoints,
            "description": self.description,
            "authors": list(self.authors),
            "nested_jars": list(self.nested_jars),
        }


@dataclass
class DiagnosticIssue:
    """An issue diagnosed during modpack inspection."""
    code: IssueCode
    severity: IssueSeverity
    message: str
    mod_id: Optional[str] = None
    related_mod_id: Optional[str] = None
    file_path: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "mod_id": self.mod_id,
            "related_mod_id": self.related_mod_id,
            "file_path": self.file_path,
            "recommendation": self.recommendation,
        }


@dataclass
class DiagnosisReport:
    """Complete diagnostic report for a modpack or set of mods."""
    scanned_path: str
    target_env: str = "both"
    minecraft_version: Optional[str] = None
    mods: List[ModInfo] = field(default_factory=list)
    issues: List[DiagnosticIssue] = field(default_factory=list)
    scan_duration_ms: float = 0.0

    @property
    def critical_count(self) -> int:
        """Count of critical issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Count of warning issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of info issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.INFO)

    def has_errors(self) -> bool:
        """Return True if any critical issues were found."""
        return self.critical_count > 0

    def has_warnings(self) -> bool:
        """Return True if any warning issues were found."""
        return self.warning_count > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert whole report to JSON-serializable dict."""
        loader_counts: Dict[str, int] = {}
        for mod in self.mods:
            loader_counts[mod.loader.value] = loader_counts.get(mod.loader.value, 0) + 1

        return {
            "scanned_path": self.scanned_path,
            "target_env": self.target_env,
            "minecraft_version": self.minecraft_version,
            "summary": {
                "total_mods": len(self.mods),
                "loaders": loader_counts,
                "critical_issues": self.critical_count,
                "warning_issues": self.warning_count,
                "info_issues": self.info_count,
                "scan_duration_ms": round(self.scan_duration_ms, 2),
                "healthy": not self.has_errors(),
            },
            "mods": [m.to_dict() for m in self.mods],
            "issues": [i.to_dict() for i in self.issues],
        }
