"""Tests de la logique d'échéance (planificateur)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Glaneur.config import Config
from Glaneur.engine.result import Resultat
from Glaneur.scheduler import Planificateur


def _cfg(tmp_path, **kw):
    """Config isolated in tmp_path, overridden by kw."""
    c = Config.charger(tmp_path / "c.json")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestDerniere:
    def test_vide(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, derniere_execution=""))
        assert p.derniere() is None

    def test_invalide(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, derniere_execution="pas une date"))
        assert p.derniere() is None

    def test_valide(self, tmp_path):
        t = "2026-01-15T12:30:00"
        p = Planificateur(_cfg(tmp_path, derniere_execution=t))
        assert p.derniere() == datetime.fromisoformat(t)


class TestProchaine:
    def test_mode_manuel(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, intervalle_heures=0))
        assert p.prochaine() is None

    def test_jamais_execute_declanche_immediat(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=""))
        avant = datetime.now()
        r = p.prochaine()
        apres = datetime.now()
        assert avant <= r <= apres

    def test_calcul_normal(self, tmp_path):
        t0 = datetime.now() - timedelta(hours=1)
        p = Planificateur(_cfg(tmp_path,
                               intervalle_heures=6,
                               derniere_execution=t0.isoformat(timespec="seconds")))
        assert p.prochaine() == p.derniere() + timedelta(hours=6)


class TestEcheanceAtteinte:
    def test_manuel_jamais(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, intervalle_heures=0))
        assert p.echeance_atteinte() is False

    def test_echeance_passee(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert p.echeance_atteinte() is True

    def test_echeance_future(self, tmp_path):
        t0 = datetime.now().isoformat(timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert p.echeance_atteinte() is False


class TestMarquerExecution:
    def test_ecrit_horodatage_et_persiste(self, tmp_path):
        cfg = _cfg(tmp_path, intervalle_heures=24, derniere_execution="")
        p = Planificateur(cfg)
        p.marquer_execution()
        # re-read from disk: the timestamp has been persisted
        cfg2 = Config.charger(tmp_path / "c.json")
        assert cfg2.derniere_execution
        # parses cleanly to a datetime
        datetime.fromisoformat(cfg2.derniere_execution)


class TestTextePresentable:
    def test_mode_manuel(self, tmp_path):
        p = Planificateur(_cfg(tmp_path, intervalle_heures=0))
        assert "désactivée" in p.texte_prochaine()

    def test_imminente(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert "imminente" in p.texte_prochaine()

    def test_reste_en_minutes(self, tmp_path):
        # due time in ~30 min: derniere = now - 23h30
        t0 = (datetime.now() - timedelta(hours=23, minutes=30)).isoformat(
            timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        r = p.texte_prochaine()
        assert "min" in r
        # < 1h → no "h" field
        assert " h " not in r

    def test_reste_en_heures(self, tmp_path):
        # due time in ~3h30: derniere = now - 20h30
        t0 = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert " h " in p.texte_prochaine()

    def test_reste_en_jours(self, tmp_path):
        # due time in 5 days: interval 7 days, derniere = 2 days ago
        t0 = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=168,
                               derniere_execution=t0))
        assert " j " in p.texte_prochaine()


# --------------------------------------------------------------------------- #
# Deferred retry (lot 3): circuit-breaker/backoff persistence
# --------------------------------------------------------------------------- #

class TestDifferer:
    def test_differer_sans_hint_utilise_backoff_1h(self, tmp_path):
        """Level 0 with no server hint schedules retry ~1h out and bumps level to 1."""
        cfg = _cfg(tmp_path, backoff_niveau=0)
        p = Planificateur(cfg)
        avant = datetime.now()
        p.differer(Resultat(reporte=True, retenter_apres=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=1))).total_seconds()) < 60
        assert cfg.backoff_niveau == 1

    def test_differer_incremente_le_niveau_1_a_2(self, tmp_path):
        """Level 1 with no hint schedules retry ~2h out and moves to level 2."""
        cfg = _cfg(tmp_path, backoff_niveau=1)
        p = Planificateur(cfg)
        avant = datetime.now()
        p.differer(Resultat(reporte=True, retenter_apres=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=2))).total_seconds()) < 60
        assert cfg.backoff_niveau == 2

    def test_differer_plafonne_le_niveau_a_2(self, tmp_path):
        """Level 2 caps at 2 and applies the 4h backoff without going further."""
        cfg = _cfg(tmp_path, backoff_niveau=2)
        p = Planificateur(cfg)
        avant = datetime.now()
        p.differer(Resultat(reporte=True, retenter_apres=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=4))).total_seconds()) < 60
        assert cfg.backoff_niveau == 2

    def test_differer_avec_hint_serveur(self, tmp_path):
        """A server Retry-After sets retenter_apres verbatim and leaves the level intact."""
        cfg = _cfg(tmp_path, backoff_niveau=1)
        p = Planificateur(cfg)
        hint_aware = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        p.differer(Resultat(reporte=True, retenter_apres=hint_aware.isoformat()))
        expected_local = hint_aware.astimezone().replace(tzinfo=None)
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert parsed.tzinfo is None
        assert abs((parsed - expected_local).total_seconds()) < 2
        assert cfg.backoff_niveau == 1

    def test_differer_persiste(self, tmp_path):
        """Fields written by differer survive a fresh charger() round-trip."""
        cfg = _cfg(tmp_path, backoff_niveau=0)
        p = Planificateur(cfg)
        p.differer(Resultat(reporte=True, retenter_apres=""))

        cfg2 = Config.charger(tmp_path / "c.json")
        assert cfg2.retenter_apres == cfg.retenter_apres
        assert cfg2.backoff_niveau == cfg.backoff_niveau


class TestProchaineAvecReport:
    def test_prochaine_respecte_retenter_apres(self, tmp_path):
        """When the deferral date is later than the nominal deadline, prochaine returns it."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() + timedelta(hours=26)
        p = Planificateur(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres=report.isoformat(timespec="seconds"),
        ))
        r = p.prochaine()
        assert abs((r - report.replace(microsecond=0)).total_seconds()) < 2

    def test_prochaine_ignore_retenter_apres_depasse(self, tmp_path):
        """A stale deferral must not drag the nominal deadline back into the past."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() - timedelta(hours=5)
        p = Planificateur(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres=report.isoformat(timespec="seconds"),
        ))
        r = p.prochaine()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal

    def test_prochaine_retenter_apres_invalide_ignore(self, tmp_path):
        """A malformed retenter_apres is silently ignored, prochaine still returns nominal."""
        derniere = datetime.now() - timedelta(hours=1)
        p = Planificateur(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres="not-a-datetime",
        ))
        r = p.prochaine()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal


class TestMarquerExecutionReinitialise:
    def test_reset_apres_marquer_execution(self, tmp_path):
        """marquer_execution clears any pending deferral (retenter_apres + backoff)."""
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(tmp_path,
                   intervalle_heures=24,
                   retenter_apres=report,
                   backoff_niveau=2)
        p = Planificateur(cfg)
        p.marquer_execution()
        assert cfg.retenter_apres == ""
        assert cfg.backoff_niveau == 0


class TestTextePresentableAvecReport:
    def test_libelle_report_actif(self, tmp_path):
        """Report qui repousse la nominale → libellé mentionne « report »."""
        # Dernière exécution récente : nominale ≈ maintenant + 24 h ; on pose
        # un report qui dépasse cette nominale pour qu'il soit vraiment
        # décisionnaire.
        report = (datetime.now() + timedelta(hours=26)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=datetime.now().isoformat(timespec="seconds"),
            retenter_apres=report,
        )
        p = Planificateur(cfg)
        assert "report" in p.texte_prochaine().lower()

    def test_libelle_report_avant_nominale_ignore(self, tmp_path):
        """Report antérieur à la nominale → pas de libellé « report » trompeur.

        Cas concret : le serveur a répondu par un `Retry-After` court (1 h)
        mais la mise à jour automatique n'est de toute façon que dans 24 h.
        Le report n'est pas le facteur décisif : c'est la nominale qui
        gagne, donc le libellé doit rester nominal.
        """
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=datetime.now().isoformat(timespec="seconds"),
            retenter_apres=report,
        )
        p = Planificateur(cfg)
        assert "report" not in p.texte_prochaine().lower()

    def test_libelle_report_passe_ignore(self, tmp_path):
        """`retenter_apres` dépassé → libellé nominal (pas de « report »)."""
        past = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        derniere = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere,
            retenter_apres=past,
        )
        p = Planificateur(cfg)
        assert "report" not in p.texte_prochaine().lower()
