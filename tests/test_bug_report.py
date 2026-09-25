"""Tests du helper de rapport de bug (URL GitHub préremplie)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from Glaneur.bug_report import (
    MAX_URL_LENGTH,
    _compact_line,
    build_issue_url,
    collect_context,
    is_url_too_long,
)


# --------------------------------------------------------------------------- #
# build_issue_url
# --------------------------------------------------------------------------- #

class TestBuildIssueUrl:
    def test_construit_url_de_base(self):
        url = build_issue_url("penoud", "Glaneur", "titre", "corps")
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == "/penoud/Glaneur/issues/new"
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

    def test_ne_tronque_jamais_le_body(self):
        # La troncature silencieuse a été retirée : le caller doit avertir
        # l'utilisateur via is_url_too_long() plutôt que perdre du contenu.
        body = "x" * 20000
        url = build_issue_url("o", "r", "t", body)
        q = parse_qs(urlparse(url).query)
        assert q["body"] == [body]


# --------------------------------------------------------------------------- #
# is_url_too_long
# --------------------------------------------------------------------------- #

class TestIsUrlTooLong:
    def test_url_courte_ok(self):
        url = build_issue_url("o", "r", "t", "petit corps")
        assert is_url_too_long(url) is False

    def test_url_longue_detectee(self):
        # 20 000 chars bruts + accents/backslashes gonflent l'URL encodée
        # bien au-delà de MAX_URL_LENGTH.
        body = ("Chemin C:\\Users\\Denis\\AppData é à ù\n" * 500)
        url = build_issue_url("o", "r", "t", body)
        assert len(url) > MAX_URL_LENGTH
        assert is_url_too_long(url) is True

    def test_seuil_personnalisable(self):
        url = build_issue_url("o", "r", "t", "x" * 200)
        assert is_url_too_long(url, max_length=100) is True
        assert is_url_too_long(url, max_length=10_000) is False


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

    def test_log_est_compacte(self, tmp_path):
        # Le log réel du user (préfixe logger + chemins Windows + timestamps
        # à ms) doit être compacté avant d'être inclus dans le body. Deux
        # dates différentes pour désactiver la sortie de date en en-tête et
        # tester la compaction ligne par ligne.
        chemin = tmp_path / "app.log"
        chemin.write_text(
            "2026-09-21 15:03:04,949 INFO Glaneur.app.update: "
            r"installer=C:\Users\Denis\AppData\Local\Temp\x.exe"
            "\n"
            "2026-09-22 16:00:00,000 INFO Glaneur.foo: bar\n"
        )
        ctx = collect_context("1.2.3", chemin_log=chemin, nb_lignes=2)
        assert "Glaneur." not in ctx
        assert "C:\\Users\\Denis" not in ctx
        assert "%TEMP%" in ctx
        assert ",949" not in ctx      # ms droppées
        assert "2026-" not in ctx     # année droppée en tête de ligne
        assert "09-21 15:03:04" in ctx

    def test_log_meme_jour_note_la_date_dans_len_tete(self, tmp_path):
        # Toutes les lignes le même jour -> date sortie en tête, HH:MM:SS
        # seulement dans les lignes.
        chemin = tmp_path / "app.log"
        chemin.write_text(
            "2026-09-21 15:03:04,949 INFO Glaneur.foo: a\n"
            "2026-09-21 15:03:05,000 INFO Glaneur.foo: b\n"
        )
        ctx = collect_context("1.2.3", chemin_log=chemin, nb_lignes=10)
        assert "date : 2026-09-21" in ctx
        assert "09-21 15:03:04" not in ctx   # date retirée aussi des lignes
        assert "15:03:04 INFO foo: a" in ctx


# --------------------------------------------------------------------------- #
# _compact_line
# --------------------------------------------------------------------------- #

class TestCompactLine:
    def test_strip_prefixe_logger_uniquement_apres_le_niveau(self):
        # Le préfixe est enlevé après INFO/WARN/… mais PAS quand il apparaît
        # dans un message (ex: dépôt GitHub, chemin, etc.).
        line = (
            "2026-09-21 15:03:04,949 INFO Glaneur.updater.foo: "
            "repo=penoud/Glaneur.git"
        )
        out = _compact_line(line)
        assert "INFO updater.foo:" in out
        assert "penoud/Glaneur.git" in out  # non touché

    def test_strip_millisecondes(self):
        out = _compact_line("2026-09-21 15:03:04,949 INFO foo: bar")
        assert ",949" not in out
        assert "15:03:04" in out

    def test_strip_annee(self):
        out = _compact_line("2026-09-21 15:03:04,949 INFO foo: bar")
        assert not out.startswith("2026-")
        assert out.startswith("09-21 15:03:04")

    def test_chemins_windows_remplaces_par_placeholders(self):
        line = (
            "INFO x: "
            r"a=C:\Users\Denis\AppData\Local\Temp\z "
            r"b=C:\Users\Denis\AppData\Local\Programs\y "
            r"c=C:\Users\Denis\AppData\Roaming\w "
            r"d=C:\Users\Denis\Documents"
        )
        out = _compact_line(line)
        assert "%TEMP%\\z" in out
        assert "%LOCALAPPDATA%\\Programs\\y" in out
        assert "%APPDATA%\\w" in out
        assert "%USERPROFILE%\\Documents" in out
        assert "Denis" not in out   # bonus vie privée
