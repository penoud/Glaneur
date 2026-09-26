"""Comparaison stricte de versions SemVer."""

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
    """Version SemVer immuable, comparable et ordonnée totalement.

    Compare sur ``(major, minor, patch)`` puis, à égalité de triplet,
    par les identifiants de prerelease selon la règle SemVer 2.0 : une
    version sans prerelease est plus grande que la même avec
    prerelease, et les identifiants sont comparés numérique-vs-numérique
    puis lexicographiquement.
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
        """Analyse une chaîne SemVer (avec ``v`` optionnel et metadata build ignorée).

        Args:
            value: Chaîne à analyser (par exemple ``"v1.2.3"``,
                ``"1.2.3-rc.1"``, ``"1.2.3+build.5"``).

        Returns:
            La :class:`Version` correspondante. Le suffixe ``+build``
            est reconnu mais non conservé.

        Raises:
            ValueError: Si la chaîne ne correspond pas au format
                SemVer strict.
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
