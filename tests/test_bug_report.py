"""Tests du helper de rapport de bug (URL GitHub préremplie)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from WpImageDownloader.bug_report import build_issue_url, collect_context


# --------------------------------------------------------------------------- #
# build_issue_url
# --------------------------------------------------------------------------- #

class TestBuildIssueUrl:
    def test_construit_url_de_base(self):
        url = build_issue_url("penoud", "WpImageDownloader", "titre", "corps")
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == "/penoud/WpImageDownloader/issues/new"
        q = parse_qs(parsed.query)
        assert q["title"] == ["titre"]
        assert q["body"] == ["corps"]

    def test_encode_caracteres_speciaux(self):
        url = build_issue_url("o", "r", "É&é ?", "```\nlog\n```")
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        # décodé, on retrouve les valeurs originales
        assert q["title"] == ["É&é ?"]
        assert q["body"] == ["```\nlog\n```"]
        # encodé, pas de & ni ? bruts dans les valeurs
        assert "%26" in parsed.query   # & encodé
        assert "%3F" in parsed.query   # ? encodé

    def test_body_tronque_si_trop_long(self):
        body = "x" * 20000
        url = build_issue_url("o", "r", "t", body, max_body=1000)
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        assert len(q["body"][0]) <= 1000
        assert "tronqué automatiquement" in q["body"][0]

    def test_body_court_pas_tronque(self):
        url = build_issue_url("o", "r", "t", "petit corps")
        q = parse_qs(urlparse(url).query)
        assert q["body"] == ["petit corps"]


# --------------------------------------------------------------------------- #
# collect_context
# --------------------------------------------------------------------------- #

class TestCollectContext:
    def test_inclut_version_platforme_python(self):
        ctx = collect_context("1.2.3")
        assert "**Version** : 1.2.3" in ctx
        assert "**Plateforme**" in ctx
        assert "**Python**" in ctx

    def test_sans_log_omet_section_log(self):
        ctx = collect_context("1.2.3", chemin_log=None)
        assert "log" not in ctx.lower() or "Dernières lignes" not in ctx
        assert "Dernières lignes de log" not in ctx

    def test_avec_log_inclut_les_dernieres_lignes(self, tmp_path):
        chemin = tmp_path / "app.log"
        chemin.write_text("\n".join(f"ligne{i}" for i in range(100)) + "\n")
        ctx = collect_context("1.2.3", chemin_log=chemin, nb_lignes=5)
        assert "ligne99" in ctx
        assert "ligne95" in ctx
        assert "ligne94" not in ctx   # sous la fenêtre de 5

    def test_log_inaccessible_omet_section(self, tmp_path):
        # fichier absent -> section omise sans lever
        ctx = collect_context("1.2.3", chemin_log=tmp_path / "absent.log")
        assert "Dernières lignes de log" not in ctx
