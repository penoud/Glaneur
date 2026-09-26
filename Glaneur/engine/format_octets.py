"""Formatage d'un nombre d'octets en unité lisible."""

from __future__ import annotations


def format_octets(n: int) -> str:
    """Formate un nombre d'octets en unité lisible.

    Args:
        n: Nombre d'octets.

    Returns:
        Une chaîne du type ``"1024 o"``, ``"1.5 Mo"`` ou ``"2.3 Go"``,
        arrondie à un chiffre après la virgule au-delà de l'octet.
    """
    for unite in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unite == "Go":
            return f"{n:.0f} {unite}" if unite == "o" else f"{n:.1f} {unite}"
        n /= 1024
    return f"{n:.1f} Go"
