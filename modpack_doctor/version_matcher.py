"""Version parsing and constraint matching for Minecraft mods.

Supports:
- SemVer and npm-style ranges (^, ~, >=, <=, >, <, =, !=)
- Maven artifact version ranges: [1.0, 2.0), [1.0], (1.0,), (,2.0]
- Minecraft snapshot and release versions (e.g., 1.20.1, 24w10a, 1.20.1-rc1)
- Wildcards: *, x, X, 1.20.*, 1.20.x
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple
from packaging.version import InvalidVersion, Version as PkgVersion


class ComparableVersion:
    """A version class supporting standard semver and Minecraft non-standard versions."""

    def __init__(self, raw: str) -> None:
        self.raw = str(raw).strip()
        self.cleaned = self._clean_raw(self.raw)
        self._pkg_version: Optional[PkgVersion] = None
        self._fallback_tuple: Tuple[Any, ...] = ()

        try:
            self._pkg_version = PkgVersion(self.cleaned)
        except InvalidVersion:
            self._fallback_tuple = self._parse_fallback(self.cleaned)

    @staticmethod
    def _clean_raw(v: str) -> str:
        v = v.strip()
        if v.startswith("v") or v.startswith("V"):
            v = v[1:]
        # Remove build metadata after '+' if needed for standard comparison,
        # but retain it if needed. PkgVersion supports +local
        return v

    @staticmethod
    def _parse_fallback(v: str) -> Tuple[Any, ...]:
        """Parse non-standard version into comparable tuple of ints and strings."""
        # Split into tokens by dots, hyphens, pluses
        parts = re.split(r"[-._+]", v)
        result: List[Any] = []
        for p in parts:
            if not p:
                continue
            if p.isdigit():
                result.append(int(p))
            else:
                # Split alphanumeric like 24w10a -> 24, 'w', 10, 'a'
                sub_parts = re.findall(r"\d+|\D+", p)
                for sp in sub_parts:
                    if sp.isdigit():
                        result.append(int(sp))
                    else:
                        result.append(sp.lower())
        return tuple(result)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ComparableVersion):
            try:
                other = ComparableVersion(str(other))
            except Exception:
                return False
        if self._pkg_version and other._pkg_version:
            return bool(self._pkg_version == other._pkg_version)
        if self._pkg_version or other._pkg_version:
            # One is standard packaging, one is fallback
            return self.raw == other.raw
        return bool(self._fallback_tuple == other._fallback_tuple)

    def __lt__(self, other: ComparableVersion) -> bool:
        if not isinstance(other, ComparableVersion):
            other = ComparableVersion(str(other))
        if self._pkg_version and other._pkg_version:
            return bool(self._pkg_version < other._pkg_version)
        if self._pkg_version and not other._pkg_version:
            # Convert pkg_version base to tuple
            self_tup = tuple(self._pkg_version.release)
            return self_tup < other._fallback_tuple
        if not self._pkg_version and other._pkg_version:
            other_tup = tuple(other._pkg_version.release)
            return self._fallback_tuple < other_tup
        return self._tuple_compare(self._fallback_tuple, other._fallback_tuple) < 0

    def __le__(self, other: ComparableVersion) -> bool:
        return self == other or self < other

    def __gt__(self, other: ComparableVersion) -> bool:
        return not (self <= other)

    def __ge__(self, other: ComparableVersion) -> bool:
        return not (self < other)

    @staticmethod
    def _tuple_compare(t1: Tuple[Any, ...], t2: Tuple[Any, ...]) -> int:
        """Compare two arbitrary fallback tuples safely."""
        for a, b in zip(t1, t2):
            if isinstance(a, int) and isinstance(b, int):
                if a != b:
                    return 1 if a > b else -1
            else:
                sa, sb = str(a), str(b)
                if sa != sb:
                    return 1 if sa > sb else -1
        if len(t1) != len(t2):
            return 1 if len(t1) > len(t2) else -1
        return 0

    def __repr__(self) -> str:
        return f"ComparableVersion({self.raw!r})"


class VersionMatcher:
    """Matches version strings against Maven, SemVer, or custom ranges."""

    MAVEN_RANGE_REGEX = re.compile(r"^([\[\(])([^,]*),?([^,]*)([\]\)])$")

    @classmethod
    def matches(cls, version_str: str, constraint_str: str) -> bool:
        """Check if version_str satisfies constraint_str."""
        v_str = (version_str or "").strip()
        c_str = (constraint_str or "").strip()

        # Wildcards match anything
        if not c_str or c_str in ("*", "x", "X", "any"):
            return True

        if not v_str:
            return False

        # Check for Maven range: e.g. [1.0, 2.0), [1.0], [1.0,)
        if cls.is_maven_range(c_str):
            return cls._matches_maven(v_str, c_str)

        # Handle multiple comma-separated or space-separated constraints: e.g. ">=1.20 <=1.20.4"
        parts = cls._split_constraints(c_str)
        if len(parts) > 1:
            return all(cls.matches(v_str, part) for part in parts)

        # Single constraint matching
        return cls._matches_single(v_str, c_str)

    @classmethod
    def is_maven_range(cls, constraint: str) -> bool:
        """Return True if string conforms to Maven range syntax."""
        c = constraint.strip()
        return (c.startswith("[") or c.startswith("(")) and (c.endswith("]") or c.endswith(")"))

    @classmethod
    def _split_constraints(cls, c_str: str) -> List[str]:
        """Split combined constraints (e.g. '>=1.19 <1.20' or '>=1.19, <1.20')."""
        # Replace commas with spaces if not inside brackets
        tokens = c_str.replace(",", " ").split()
        return [t.strip() for t in tokens if t.strip()]

    @classmethod
    def _matches_maven(cls, v_str: str, maven_range: str) -> bool:
        """Evaluate Maven range."""
        m = cls.MAVEN_RANGE_REGEX.match(maven_range)
        if not m:
            return True

        left_bracket, lower_str, upper_str, right_bracket = m.groups()
        lower_str = lower_str.strip()
        upper_str = upper_str.strip()

        # Exact version case: [1.2.3]
        if left_bracket == "[" and right_bracket == "]" and lower_str and not upper_str:
            return ComparableVersion(v_str) == ComparableVersion(lower_str)

        ver = ComparableVersion(v_str)

        # Check lower bound
        if lower_str:
            low_ver = ComparableVersion(lower_str)
            if left_bracket == "[" and not (ver >= low_ver):
                return False
            if left_bracket == "(" and not (ver > low_ver):
                return False

        # Check upper bound
        if upper_str:
            up_ver = ComparableVersion(upper_str)
            if right_bracket == "]" and not (ver <= up_ver):
                return False
            if right_bracket == ")" and not (ver < up_ver):
                return False

        return True

    @classmethod
    def _matches_single(cls, v_str: str, constraint: str) -> bool:
        """Evaluate single semver/wildcard constraint."""
        c = constraint.strip()

        # Wildcard suffix: e.g. "1.20.*" or "1.20.x"
        if c.endswith(".*") or c.endswith(".x") or c.endswith(".X"):
            prefix = c[:-2]
            return v_str == prefix or v_str.startswith(prefix + ".") or v_str.startswith(prefix + "-")

        # Caret range: ^1.2.3 (compatible with same major)
        if c.startswith("^"):
            base_str = c[1:].strip()
            base_ver = ComparableVersion(base_str)
            ver = ComparableVersion(v_str)
            if ver < base_ver:
                return False
            # Find next major bound
            parts = re.split(r"[-._+]", base_str)
            if parts and parts[0].isdigit():
                major = int(parts[0])
                if major == 0 and len(parts) > 1 and parts[1].isdigit():
                    minor = int(parts[1])
                    upper = ComparableVersion(f"0.{minor + 1}.0")
                else:
                    upper = ComparableVersion(f"{major + 1}.0.0")
                return ver < upper
            return True

        # Tilde range: ~1.2.3 (compatible with same minor)
        if c.startswith("~"):
            base_str = c[1:].strip()
            base_ver = ComparableVersion(base_str)
            ver = ComparableVersion(v_str)
            if ver < base_ver:
                return False
            parts = re.split(r"[-._+]", base_str)
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                major = int(parts[0])
                minor = int(parts[1])
                upper = ComparableVersion(f"{major}.{minor + 1}.0")
                return ver < upper
            return True

        # Comparison operators
        for op in (">=", "<=", "!=", ">", "<", "="):
            if c.startswith(op):
                target_str = c[len(op):].strip()
                ver = ComparableVersion(v_str)
                target = ComparableVersion(target_str)
                if op == ">=":
                    return ver >= target
                elif op == "<=":
                    return ver <= target
                elif op == ">":
                    return ver > target
                elif op == "<":
                    return ver < target
                elif op == "!=":
                    return ver != target
                else:  # op == "="
                    return ver == target

        # Soft requirement or plain version match:
        if v_str == c:
            return True

        # Try version equality
        return ComparableVersion(v_str) == ComparableVersion(c)
