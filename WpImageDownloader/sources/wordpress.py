"""Adaptateur WordPress : `/wp-json/wp/v2/`.

Extrait à l'identique de l'ancien `engine.py` : mêmes règles de pagination
(`X-WP-TotalPages`, 400 = fin), même résolution de galeries, même regex
`/uploads/AAAA/MM/` pour le classement par date.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterator
from urllib.parse import urlparse

from .base import Element, Source

PER_PAGE = 100


def _nettoyer(titre: str, defaut: str = "divers") -> str:
    """Copie locale de `engine.nettoyer` pour éviter le cycle d'import."""
    texte = html.unescape(titre or "").strip()
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip()
    texte = re.sub(r"[\s_]+", "-", texte).lower()
    texte = texte.strip(".-")
    return texte[:80] or defaut


class WordPress(Source):
    type = "wordpress"
    classements = frozenset({"galerie", "date", "plat"})

    def __init__(self, base, transport, reglages, journal=None, progression=None):
        super().__init__(base, transport, reglages, journal, progression)
        self.api = f"{self.base}/wp-json/wp/v2"

    # -- HTTP ------------------------------------------------------------- #

    def _api(self, chemin: str, params: dict | None = None):
        url = f"{self.api}/{chemin.lstrip('/')}"
        return self.transport.get_json(url, params=params, fin_si=frozenset({400}))

    # -- Inventaire ------------------------------------------------------- #

    def inventaire(
        self, depuis: str | None, jusqua: str | None,
    ) -> Iterator[Element]:
        params = {
            "per_page": PER_PAGE,
            "media_type": "image",
            "orderby": "date",
            "order": "asc",
            "_fields": "id,date,source_url,mime_type,title,alt_text,post,media_details",
        }
        if depuis:
            params["after"] = depuis if "T" in depuis else f"{depuis}T00:00:00"
        if jusqua:
            params["before"] = f"{jusqua}T23:59:59"

        vus: set[int] = set()
        rendus: list[Element] = []
        page, pages_totales, vides = 1, None, 0

        while True:
            lot, headers = self._api("media", {**params, "page": page})
            if pages_totales is None:
                total = headers.get("X-WP-Total", "?")
                pages_totales = int(headers.get("X-WP-TotalPages") or 0)
                self._journal(
                    f"Catalogue : {total} image(s) sur {pages_totales or '?'} page(s)")
            if lot is None:
                break

            nouvelles = [m for m in lot if m["id"] not in vus]
            vus.update(m["id"] for m in nouvelles)
            for m in nouvelles:
                rendus.append(self._to_element(m))
            self._progression(page, pages_totales or page,
                              f"Inventaire… {len(rendus)} image(s)")

            vides = vides + 1 if not lot else 0
            if vides >= 2:
                break
            if pages_totales and page >= pages_totales:
                break
            if not pages_totales and not lot:
                break
            page += 1
            self.transport.pause()

        return iter(rendus)

    def _to_element(self, m: dict) -> Element:
        url = m.get("source_url") or ""
        details = m.get("media_details") or {}
        chemin = urlparse(url).path
        mois: str | None = None
        match = re.search(r"/uploads/(\d{4})/(\d{2})/", chemin)
        if match:
            mois = f"{match.group(1)}-{match.group(2)}"
        return Element(
            ident=str(m["id"]),
            url=url,
            nom_fichier=chemin.rsplit("/", 1)[-1] if chemin else "",
            date=m.get("date"),
            mois=mois,
            largeur=details.get("width"),
            taille=details.get("filesize"),
            groupe=str(m["post"]) if m.get("post") else None,
        )

    # -- Regroupement (galerie) ------------------------------------------- #

    def _bases_rest(self) -> list[str]:
        try:
            types, _ = self._api("types")
        except RuntimeError:
            return ["posts", "pages"]
        bases = [
            info.get("rest_base")
            for slug, info in (types or {}).items()
            if info.get("rest_base") and slug not in ("attachment", "wp_block", "nav_menu_item")
        ]
        bases.sort(key=lambda b: (0 if "galer" in b else 1, b))
        return bases or ["posts"]

    def resoudre_groupes(
        self, cles: set[str], connus: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """{clé → titre}. Les entrées `connus` sont conservées telles quelles ;
        seules les clés manquantes déclenchent des appels API."""
        titres: dict[str, str] = dict(connus or {})
        restants = {c for c in cles if c and c not in titres}
        if not restants:
            return titres

        # côté WP les IDs sont des entiers ; on convertit pour les paramètres
        # et on garde des clés string dans le résultat.
        for base in self._bases_rest():
            if not restants:
                break
            ids_int = sorted(int(c) for c in restants if str(c).isdigit())
            for i in range(0, len(ids_int), PER_PAGE):
                tranche = ids_int[i: i + PER_PAGE]
                try:
                    items, _ = self._api(base, {
                        "include": ",".join(map(str, tranche)),
                        "per_page": PER_PAGE,
                        "_fields": "id,title,slug",
                    })
                except RuntimeError:
                    continue
                for item in items or []:
                    cle = str(item["id"])
                    titres[cle] = item.get("slug") or _nettoyer(
                        item.get("title", {}).get("rendered", ""))
                    restants.discard(cle)
                self.transport.pause()

        if restants:
            self._journal(
                f"{len(restants)} galerie(s) non identifiée(s), classées par date.")
        return titres
