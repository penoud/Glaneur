"""Tests for the scheduler's due-time logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Glaneur.config import Config
from Glaneur.engine.result import RunResult
from Glaneur.scheduler import Scheduler
from Glaneur.scheduler_labels import next_run_text


def _cfg(tmp_path, **kw):
    """Config isolated in tmp_path, overridden by kw."""
    c = Config.charger(tmp_path / "c.json")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestDerniere:
    def test_vide(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, derniere_execution=""))
        assert p.last_run() is None

    def test_invalide(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, derniere_execution="pas une date"))
        assert p.last_run() is None

    def test_valide(self, tmp_path):
        t = "2026-01-15T12:30:00"
        p = Scheduler(_cfg(tmp_path, derniere_execution=t))
        assert p.last_run() == datetime.fromisoformat(t)


class TestProchaine:
    def test_mode_manuel(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, intervalle_heures=0))
        assert p.next_run() is None

    def test_jamais_execute_declanche_immediat(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=""))
        avant = datetime.now()
        r = p.next_run()
        apres = datetime.now()
        assert avant <= r <= apres

    def test_calcul_normal(self, tmp_path):
        t0 = datetime.now() - timedelta(hours=1)
        p = Scheduler(_cfg(tmp_path,
                               intervalle_heures=6,
                               derniere_execution=t0.isoformat(timespec="seconds")))
        assert p.next_run() == p.last_run() + timedelta(hours=6)


class TestEcheanceAtteinte:
    def test_manuel_jamais(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, intervalle_heures=0))
        assert p.is_due() is False

    def test_echeance_passee(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert p.is_due() is True

    def test_echeance_future(self, tmp_path):
        t0 = datetime.now().isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert p.is_due() is False


class TestMarquerExecution:
    def test_ecrit_horodatage_et_persiste(self, tmp_path):
        cfg = _cfg(tmp_path, intervalle_heures=24, derniere_execution="")
        p = Scheduler(cfg)
        p.mark_run()
        # re-read from disk: the timestamp has been persisted
        cfg2 = Config.charger(tmp_path / "c.json")
        assert cfg2.derniere_execution
        # parses cleanly to a datetime
        datetime.fromisoformat(cfg2.derniere_execution)


class TestTextePresentable:
    def test_mode_manuel(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, intervalle_heures=0))
        assert "désactivée" in next_run_text(p)

    def test_imminente(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert "imminente" in next_run_text(p)

    def test_reste_en_minutes(self, tmp_path):
        # due time in ~30 min: derniere = now - 23h30
        t0 = (datetime.now() - timedelta(hours=23, minutes=30)).isoformat(
            timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        r = next_run_text(p)
        assert "min" in r
        # < 1h → no "h" field
        assert " h " not in r

    def test_reste_en_heures(self, tmp_path):
        # due time in ~3h30: derniere = now - 20h30
        t0 = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert " h " in next_run_text(p)

    def test_reste_en_jours(self, tmp_path):
        # due time in 5 days: interval 7 days, derniere = 2 days ago
        t0 = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, intervalle_heures=168,
                               derniere_execution=t0))
        assert " j " in next_run_text(p)


# --------------------------------------------------------------------------- #
# Deferred retry (lot 3): circuit-breaker/backoff persistence
# --------------------------------------------------------------------------- #

class TestDifferer:
    def test_differer_sans_hint_utilise_backoff_1h(self, tmp_path):
        """Level 0 with no server hint schedules retry ~1h out and bumps level to 1."""
        cfg = _cfg(tmp_path, backoff_niveau=0)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=1))).total_seconds()) < 60
        assert cfg.backoff_niveau == 1

    def test_differer_incremente_le_niveau_1_a_2(self, tmp_path):
        """Level 1 with no hint schedules retry ~2h out and moves to level 2."""
        cfg = _cfg(tmp_path, backoff_niveau=1)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=2))).total_seconds()) < 60
        assert cfg.backoff_niveau == 2

    def test_differer_plafonne_le_niveau_a_2(self, tmp_path):
        """Level 2 caps at 2 and applies the 4h backoff without going further."""
        cfg = _cfg(tmp_path, backoff_niveau=2)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert abs((parsed - (avant + timedelta(hours=4))).total_seconds()) < 60
        assert cfg.backoff_niveau == 2

    def test_differer_avec_hint_serveur(self, tmp_path):
        """A server Retry-After sets retenter_apres verbatim and leaves the level intact."""
        cfg = _cfg(tmp_path, backoff_niveau=1)
        p = Scheduler(cfg)
        hint_aware = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        p.defer(RunResult(deferred=True, retry_after=hint_aware.isoformat()))
        expected_local = hint_aware.astimezone().replace(tzinfo=None)
        parsed = datetime.fromisoformat(cfg.retenter_apres)
        assert parsed.tzinfo is None
        assert abs((parsed - expected_local).total_seconds()) < 2
        assert cfg.backoff_niveau == 1

    def test_differer_persiste(self, tmp_path):
        """Fields written by defer survive a fresh charger() round-trip."""
        cfg = _cfg(tmp_path, backoff_niveau=0)
        p = Scheduler(cfg)
        p.defer(RunResult(deferred=True, retry_after=""))

        cfg2 = Config.charger(tmp_path / "c.json")
        assert cfg2.retenter_apres == cfg.retenter_apres
        assert cfg2.backoff_niveau == cfg.backoff_niveau


class TestProchaineAvecReport:
    def test_prochaine_respecte_retenter_apres(self, tmp_path):
        """When the deferral date is later than the nominal deadline, prochaine returns it."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() + timedelta(hours=26)
        p = Scheduler(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres=report.isoformat(timespec="seconds"),
        ))
        r = p.next_run()
        assert abs((r - report.replace(microsecond=0)).total_seconds()) < 2

    def test_prochaine_ignore_retenter_apres_depasse(self, tmp_path):
        """A stale deferral must not drag the nominal deadline back into the past."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() - timedelta(hours=5)
        p = Scheduler(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres=report.isoformat(timespec="seconds"),
        ))
        r = p.next_run()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal

    def test_prochaine_retenter_apres_invalide_ignore(self, tmp_path):
        """A malformed retenter_apres is silently ignored, prochaine still returns nominal."""
        derniere = datetime.now() - timedelta(hours=1)
        p = Scheduler(_cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere.isoformat(timespec="seconds"),
            retenter_apres="not-a-datetime",
        ))
        r = p.next_run()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal


class TestMarquerExecutionReinitialise:
    def test_reset_apres_marquer_execution(self, tmp_path):
        """mark_run clears any pending deferral (retenter_apres + backoff)."""
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(tmp_path,
                   intervalle_heures=24,
                   retenter_apres=report,
                   backoff_niveau=2)
        p = Scheduler(cfg)
        p.mark_run()
        assert cfg.retenter_apres == ""
        assert cfg.backoff_niveau == 0


class TestTextePresentableAvecReport:
    def test_libelle_report_actif(self, tmp_path):
        """A defer that pushes past the nominal time → label mentions "report"."""
        # Recent last run: nominal time ≈ now + 24 h; we set a defer that
        # goes past that nominal time so it is actually the decisive one.
        report = (datetime.now() + timedelta(hours=26)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=datetime.now().isoformat(timespec="seconds"),
            retenter_apres=report,
        )
        p = Scheduler(cfg)
        assert "report" in next_run_text(p).lower()

    def test_libelle_report_avant_nominale_ignore(self, tmp_path):
        """Defer earlier than the nominal time → no misleading "report" label.

        Concrete case: the server replied with a short `Retry-After` (1 h)
        but the automatic update is 24 h away anyway. The defer is not the
        decisive factor: the nominal time wins, so the label must stay
        nominal.
        """
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=datetime.now().isoformat(timespec="seconds"),
            retenter_apres=report,
        )
        p = Scheduler(cfg)
        assert "report" not in next_run_text(p).lower()

    def test_libelle_report_passe_ignore(self, tmp_path):
        """`retenter_apres` in the past → nominal label (no "report" mention)."""
        past = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        derniere = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        cfg = _cfg(
            tmp_path,
            intervalle_heures=24,
            derniere_execution=derniere,
            retenter_apres=past,
        )
        p = Scheduler(cfg)
        assert "report" not in next_run_text(p).lower()
