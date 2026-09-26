"""Format a byte count into a human-readable string."""

from __future__ import annotations


def format_octets(n: int) -> str:
    """Format a byte count into a human-readable string.

    Args:
        n: Number of bytes.

    Returns:
        A string such as ``"1024 o"``, ``"1.5 Mo"`` or ``"2.3 Go"``,
        rounded to one decimal place above the byte unit.
    """
    for unite in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unite == "Go":
            return f"{n:.0f} {unite}" if unite == "o" else f"{n:.1f} {unite}"
        n /= 1024
    return f"{n:.1f} Go"
