"""Strict SemVer version comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@total_ordering
@dataclass(frozen=True)
class Version:
    """Immutable, totally-ordered SemVer version.

    Compares on ``(major, minor, patch)``; on triplet ties, by the
    prerelease identifiers following SemVer 2.0: a version without a
    prerelease is greater than the same one with a prerelease, and
    identifiers are compared numeric-vs-numeric then lexicographically.
    """

    #: Major number.
    major: int
    #: Minor number.
    minor: int
    #: Patch number.
    patch: int
    #: Prerelease identifiers (``()`` for a stable version).
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "Version":
        """Parse a SemVer string (optional ``v`` prefix, build metadata ignored).

        Args:
            value: String to parse (for example ``"v1.2.3"``,
                ``"1.2.3-rc.1"``, ``"1.2.3+build.5"``).

        Returns:
            The matching :class:`Version`. The ``+build`` suffix is
            recognised but not kept.

        Raises:
            ValueError: If the string does not follow strict SemVer.
        """
        match = _PATTERN.fullmatch(value.strip())
        if not match:
            raise ValueError(f"Version SemVer invalide : {value!r}")
        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)

    def _compare_key(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._compare_key() == other._compare_key() and self.prerelease == other.prerelease

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self._compare_key() != other._compare_key():
            return self._compare_key() < other._compare_key()
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and not other.prerelease:
            return True
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)

    def __str__(self) -> str:
        suffix = f"-{'.'.join(self.prerelease)}" if self.prerelease else ""
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"
