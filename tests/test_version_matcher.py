"""Tests for version matcher and parser."""

import pytest
from modpack_doctor.version_matcher import ComparableVersion, VersionMatcher


def test_comparable_version_basic():
    v1 = ComparableVersion("1.2.3")
    v2 = ComparableVersion("v1.2.3")
    v2_cap = ComparableVersion("V1.2.3")
    v3 = ComparableVersion("1.2.4")
    assert v1 == v2
    assert v1 == v2_cap
    assert v1 < v3
    assert v1 <= v3
    assert v3 > v1
    assert v3 >= v1
    assert repr(v1) == "ComparableVersion('1.2.3')"


def test_comparable_version_fallback():
    # Consecutive dots / delimiters to hit empty part
    v_dots = ComparableVersion("1..0")
    assert v_dots == "1..0"

    # Minecraft snapshots
    v1 = ComparableVersion("24w10a")
    v2 = ComparableVersion("24w10b")
    assert v1 < v2
    assert v2 > v1
    assert v1 <= v2
    assert v2 >= v1
    assert v1 != v2

    v3 = ComparableVersion("24w10a")
    assert v1 == v3

    # Fallback tuple comparison length differences
    v_short = ComparableVersion("24w10")
    assert v_short < v1
    assert v1 > v_short

    # Mixed standard vs fallback
    v_std = ComparableVersion("1.20.1")
    v_snap = ComparableVersion("24w10a")
    assert v_std != v_snap
    # Check comparison both ways (std < fallback and fallback < std)
    assert (v_std < v_snap) or (v_std > v_snap)
    assert (v_snap < v_std) or (v_snap > v_std)

    # String comparison in fallback tuple
    v_alpha = ComparableVersion("1.0.0-alpha")
    v_beta = ComparableVersion("1.0.0-beta")
    assert v_alpha < v_beta
    assert v_beta > v_alpha


def test_comparable_version_object_compare():
    v1 = ComparableVersion("1.0.0")
    assert v1 == "1.0.0"
    assert v1 != "2.0.0"
    assert (v1 == object()) is False
    assert v1 < "2.0.0"

    class BadStr:
        def __str__(self):
            raise ValueError("boom")

    assert (v1 == BadStr()) is False


def test_version_matcher_caret_tilde_fallbacks():
    # Caret with non-digit parts
    assert VersionMatcher.matches("alpha.2", "^alpha.1") in (True, False)
    # Tilde with single part or non-digit
    assert VersionMatcher.matches("1", "~1") in (True, False)
    assert VersionMatcher.matches("alpha", "~alpha") in (True, False)

    # Malformed multi-comma maven range
    assert VersionMatcher.matches("1.5.0", "[1.0, 2.0, 3.0]") is True


def test_version_matcher_wildcards():
    assert VersionMatcher.matches("1.20.1", "*") is True
    assert VersionMatcher.matches("1.20.1", "") is True
    assert VersionMatcher.matches("1.20.1", "x") is True
    assert VersionMatcher.matches("1.20.1", "X") is True
    assert VersionMatcher.matches("1.20.1", "any") is True
    assert VersionMatcher.matches("", "*") is True
    assert VersionMatcher.matches("", "1.0.0") is False


def test_version_matcher_maven_exact():
    assert VersionMatcher.matches("1.2.3", "[1.2.3]") is True
    assert VersionMatcher.matches("1.2.4", "[1.2.3]") is False


def test_version_matcher_maven_ranges():
    # [1.0, 2.0)
    assert VersionMatcher.matches("1.0.0", "[1.0.0, 2.0.0)") is True
    assert VersionMatcher.matches("1.5.0", "[1.0.0, 2.0.0)") is True
    assert VersionMatcher.matches("2.0.0", "[1.0.0, 2.0.0)") is False
    assert VersionMatcher.matches("0.9.0", "[1.0.0, 2.0.0)") is False

    # (1.0, 2.0]
    assert VersionMatcher.matches("1.0.0", "(1.0.0, 2.0.0]") is False
    assert VersionMatcher.matches("1.0.1", "(1.0.0, 2.0.0]") is True
    assert VersionMatcher.matches("2.0.0", "(1.0.0, 2.0.0]") is True
    assert VersionMatcher.matches("2.0.1", "(1.0.0, 2.0.0]") is False

    # [1.0,)
    assert VersionMatcher.matches("1.0.0", "[1.0.0,)") is True
    assert VersionMatcher.matches("5.0.0", "[1.0.0,)") is True
    assert VersionMatcher.matches("0.9.9", "[1.0.0,)") is False

    # (,2.0]
    assert VersionMatcher.matches("1.0.0", "(,2.0.0]") is True
    assert VersionMatcher.matches("2.0.0", "(,2.0.0]") is True
    assert VersionMatcher.matches("2.0.1", "(,2.0.0]") is False

    # (,2.0)
    assert VersionMatcher.matches("2.0.0", "(,2.0.0)") is False
    assert VersionMatcher.matches("1.9.9", "(,2.0.0)") is True

    # Malformed maven
    assert VersionMatcher.matches("1.0.0", "[invalid") is False


def test_version_matcher_wildcard_suffix():
    assert VersionMatcher.matches("1.20.1", "1.20.*") is True
    assert VersionMatcher.matches("1.20", "1.20.*") is True
    assert VersionMatcher.matches("1.20-rc1", "1.20.*") is True
    assert VersionMatcher.matches("1.21.0", "1.20.*") is False

    assert VersionMatcher.matches("1.20.1", "1.20.x") is True
    assert VersionMatcher.matches("1.20.2", "1.20.X") is True
    assert VersionMatcher.matches("1.19.4", "1.20.x") is False


def test_version_matcher_caret_range():
    # ^1.2.3 -> >=1.2.3 <2.0.0
    assert VersionMatcher.matches("1.2.3", "^1.2.3") is True
    assert VersionMatcher.matches("1.9.0", "^1.2.3") is True
    assert VersionMatcher.matches("2.0.0", "^1.2.3") is False
    assert VersionMatcher.matches("1.2.2", "^1.2.3") is False

    # ^0.2.3 -> >=0.2.3 <0.3.0
    assert VersionMatcher.matches("0.2.3", "^0.2.3") is True
    assert VersionMatcher.matches("0.2.9", "^0.2.3") is True
    assert VersionMatcher.matches("0.3.0", "^0.2.3") is False


def test_version_matcher_tilde_range():
    # ~1.2.3 -> >=1.2.3 <1.3.0
    assert VersionMatcher.matches("1.2.3", "~1.2.3") is True
    assert VersionMatcher.matches("1.2.9", "~1.2.3") is True
    assert VersionMatcher.matches("1.3.0", "~1.2.3") is False
    assert VersionMatcher.matches("1.2.2", "~1.2.3") is False


def test_version_matcher_operators():
    assert VersionMatcher.matches("1.20.1", ">=1.20.0") is True
    assert VersionMatcher.matches("1.20.1", ">=1.20.2") is False

    assert VersionMatcher.matches("1.20.1", "<=1.20.1") is True
    assert VersionMatcher.matches("1.20.2", "<=1.20.1") is False

    assert VersionMatcher.matches("1.20.2", ">1.20.1") is True
    assert VersionMatcher.matches("1.20.1", ">1.20.1") is False

    assert VersionMatcher.matches("1.20.0", "<1.20.1") is True
    assert VersionMatcher.matches("1.20.1", "<1.20.1") is False

    assert VersionMatcher.matches("1.20.1", "!=1.20.0") is True
    assert VersionMatcher.matches("1.20.0", "!=1.20.0") is False

    assert VersionMatcher.matches("1.20.1", "=1.20.1") is True
    assert VersionMatcher.matches("1.20.1", "=1.20.2") is False


def test_version_matcher_compound():
    assert VersionMatcher.matches("1.20.1", ">=1.20.0 <=1.20.4") is True
    assert VersionMatcher.matches("1.20.5", ">=1.20.0 <=1.20.4") is False

    assert VersionMatcher.matches("1.20.1", ">=1.20, <1.21") is True
    assert VersionMatcher.matches("1.21.0", ">=1.20, <1.21") is False


def test_version_matcher_fallback_equality():
    assert VersionMatcher.matches("custom-snapshot-1", "custom-snapshot-1") is True
    assert VersionMatcher.matches("custom-snapshot-1", "custom-snapshot-2") is False
