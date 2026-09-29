"""Tests for `Glaneur.updater.version.Version`.

The existing `tests/test_updater.py` verified the happy-path
comparison and the invalid-format branch. This file drills into the
finer SemVer 2.0 rules that were previously uncovered: the
prerelease-vs-stable ordering, the numeric-vs-lex identifier
comparison, and the `NotImplemented` return on foreign types.
"""

from __future__ import annotations

import pytest

from Glaneur.updater.version import Version


# --------------------------------------------------------------------------- #
# parse: extras
# --------------------------------------------------------------------------- #


class TestParse:
    def test_ignores_build_metadata(self):
        # `+build.X` is recognised but discarded.
        v = Version.parse("1.2.3+build.5")
        assert v == Version.parse("1.2.3")

    def test_prerelease_keeps_identifiers(self):
        v = Version.parse("1.2.3-rc.1")
        assert v.prerelease == ("rc", "1")

    def test_surrounding_whitespace_is_tolerated(self):
        assert Version.parse("  1.2.3  ") == Version.parse("1.2.3")

    def test_v_prefix_is_optional(self):
        assert Version.parse("v1.2.3") == Version.parse("1.2.3")

    @pytest.mark.parametrize("bad", [
        "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3",
        "1.2.3-", "abc", "",
    ])
    def test_rejects_invalid_formats(self, bad):
        with pytest.raises(ValueError):
            Version.parse(bad)


# --------------------------------------------------------------------------- #
# __eq__ / __lt__ against foreign types
# --------------------------------------------------------------------------- #


class TestComparisonWithForeignType:
    def test_equality_with_non_version_is_false(self):
        v = Version.parse("1.2.3")
        # __eq__ returns NotImplemented; Python's fallback yields False.
        assert (v == "1.2.3") is False
        assert (v == 42) is False
        assert (v == None) is False   # noqa: E711 — explicit `== None`

    def test_order_with_non_version_raises_typeerror(self):
        # `__lt__` returns NotImplemented; `@total_ordering` derives the
        # other comparisons from it, and Python raises TypeError when no
        # reflected op is defined either.
        v = Version.parse("1.2.3")
        with pytest.raises(TypeError):
            _ = v < "1.2.4"
        with pytest.raises(TypeError):
            _ = v > 0


# --------------------------------------------------------------------------- #
# Prerelease vs stable ordering (SemVer 2.0 §11)
# --------------------------------------------------------------------------- #


class TestPrereleaseVsStable:
    def test_stable_greater_than_same_version_with_prerelease(self):
        assert Version.parse("1.2.3") > Version.parse("1.2.3-rc.1")

    def test_prerelease_less_than_same_version_stable(self):
        assert Version.parse("1.2.3-alpha") < Version.parse("1.2.3")

    def test_two_stables_equal(self):
        assert Version.parse("1.2.3") == Version.parse("v1.2.3")
        # Neither strictly less than the other.
        v = Version.parse("1.2.3")
        assert not (v < v)


# --------------------------------------------------------------------------- #
# Prerelease identifier ordering
# --------------------------------------------------------------------------- #


class TestPrereleaseOrder:
    def test_numeric_less_than_larger_numeric(self):
        assert Version.parse("1.0.0-1") < Version.parse("1.0.0-2")
        assert Version.parse("1.0.0-alpha.1") < Version.parse("1.0.0-alpha.2")

    def test_lex_alpha_less_than_beta(self):
        assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-beta")
        assert Version.parse("1.0.0-beta") < Version.parse("1.0.0-rc")

    def test_numeric_less_than_alphanumeric(self):
        # SemVer 2.0 §11.4.3: numeric identifiers rank lower than
        # alphanumeric ones.
        assert Version.parse("1.0.0-1") < Version.parse("1.0.0-alpha")

    def test_shorter_prerelease_less_when_common_prefix(self):
        # `1.0.0-alpha` < `1.0.0-alpha.1` because the second has more
        # identifiers with the same prefix.
        assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-alpha.1")

    def test_equal_with_same_prerelease(self):
        a = Version.parse("1.0.0-rc.1")
        b = Version.parse("1.0.0-rc.1")
        assert a == b
        assert not (a < b)


# --------------------------------------------------------------------------- #
# __str__
# --------------------------------------------------------------------------- #


class TestStr:
    def test_str_stable(self):
        assert str(Version.parse("1.2.3")) == "1.2.3"

    def test_str_prerelease(self):
        assert str(Version.parse("1.2.3-rc.1")) == "1.2.3-rc.1"

    def test_str_ignores_build(self):
        assert str(Version.parse("1.2.3+build.5")) == "1.2.3"
