"""Tests for the scheduler's due-time logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Glaneur.config import Config
from Glaneur.engine.result import RunResult
from Glaneur.scheduler import Scheduler
from Glaneur.scheduler_labels import next_run_text


def _cfg(tmp_path, **kw):
    """Config isolated in tmp_path, overridden by kw."""
    c = Config.load(tmp_path / "c.json")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestLastRun:
    def test_empty(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, last_run=""))
        assert p.last_run() is None

    def test_invalid(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, last_run="pas une date"))
        assert p.last_run() is None

    def test_valid(self, tmp_path):
        t = "2026-01-15T12:30:00"
        p = Scheduler(_cfg(tmp_path, last_run=t))
        assert p.last_run() == datetime.fromisoformat(t)


class TestNextRun:
    def test_manual_mode(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, interval_hours=0))
        assert p.next_run() is None

    def test_never_ran_triggers_immediate(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=""))
        avant = datetime.now()
        r = p.next_run()
        apres = datetime.now()
        assert avant <= r <= apres

    def test_normal_computation(self, tmp_path):
        t0 = datetime.now() - timedelta(hours=1)
        p = Scheduler(_cfg(tmp_path,
                               interval_hours=6,
                               last_run=t0.isoformat(timespec="seconds")))
        assert p.next_run() == p.last_run() + timedelta(hours=6)


class TestDeadlineReached:
    def test_manual_never(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, interval_hours=0))
        assert p.is_due() is False

    def test_deadline_past(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        assert p.is_due() is True

    def test_deadline_future(self, tmp_path):
        t0 = datetime.now().isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        assert p.is_due() is False


class TestMarkRun:
    def test_writes_timestamp_and_persists(self, tmp_path):
        cfg = _cfg(tmp_path, interval_hours=24, last_run="")
        p = Scheduler(cfg)
        p.mark_run()
        # re-read from disk: the timestamp has been persisted
        cfg2 = Config.load(tmp_path / "c.json")
        assert cfg2.last_run
        # parses cleanly to a datetime
        datetime.fromisoformat(cfg2.last_run)


class TestDisplayText:
    def test_manual_mode(self, tmp_path):
        p = Scheduler(_cfg(tmp_path, interval_hours=0))
        assert "désactivée" in next_run_text(p)

    def test_imminent(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        assert "imminente" in next_run_text(p)

    def test_remaining_in_minutes(self, tmp_path):
        # due time in ~30 min: derniere = now - 23h30
        t0 = (datetime.now() - timedelta(hours=23, minutes=30)).isoformat(
            timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        r = next_run_text(p)
        assert "min" in r
        # < 1h → no "h" field
        assert " h " not in r

    def test_remaining_in_hours(self, tmp_path):
        # due time in ~3h30: derniere = now - 20h30
        t0 = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        assert " h " in next_run_text(p)

    def test_remaining_in_days(self, tmp_path):
        # due time in 5 days: interval 7 days, derniere = 2 days ago
        t0 = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=168,
                               last_run=t0))
        assert " j " in next_run_text(p)


# --------------------------------------------------------------------------- #
# Deferred retry (lot 3): circuit-breaker/backoff persistence
# --------------------------------------------------------------------------- #

class TestDefer:
    def test_defer_without_hint_uses_backoff_1h(self, tmp_path):
        """Level 0 with no server hint schedules retry ~1h out and bumps level to 1."""
        cfg = _cfg(tmp_path, backoff_level=0)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retry_after)
        assert abs((parsed - (avant + timedelta(hours=1))).total_seconds()) < 60
        assert cfg.backoff_level == 1

    def test_defer_increments_level_1_to_2(self, tmp_path):
        """Level 1 with no hint schedules retry ~2h out and moves to level 2."""
        cfg = _cfg(tmp_path, backoff_level=1)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retry_after)
        assert abs((parsed - (avant + timedelta(hours=2))).total_seconds()) < 60
        assert cfg.backoff_level == 2

    def test_defer_caps_level_at_2(self, tmp_path):
        """Level 2 caps at 2 and applies the 4h backoff without going further."""
        cfg = _cfg(tmp_path, backoff_level=2)
        p = Scheduler(cfg)
        avant = datetime.now()
        p.defer(RunResult(deferred=True, retry_after=""))
        parsed = datetime.fromisoformat(cfg.retry_after)
        assert abs((parsed - (avant + timedelta(hours=4))).total_seconds()) < 60
        assert cfg.backoff_level == 2

    def test_defer_with_server_hint(self, tmp_path):
        """A server Retry-After sets retenter_apres verbatim and leaves the level intact."""
        cfg = _cfg(tmp_path, backoff_level=1)
        p = Scheduler(cfg)
        hint_aware = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
        p.defer(RunResult(deferred=True, retry_after=hint_aware.isoformat()))
        expected_local = hint_aware.astimezone().replace(tzinfo=None)
        parsed = datetime.fromisoformat(cfg.retry_after)
        assert parsed.tzinfo is None
        assert abs((parsed - expected_local).total_seconds()) < 2
        assert cfg.backoff_level == 1

    def test_defer_persists(self, tmp_path):
        """Fields written by defer survive a fresh charger() round-trip."""
        cfg = _cfg(tmp_path, backoff_level=0)
        p = Scheduler(cfg)
        p.defer(RunResult(deferred=True, retry_after=""))

        cfg2 = Config.load(tmp_path / "c.json")
        assert cfg2.retry_after == cfg.retry_after
        assert cfg2.backoff_level == cfg.backoff_level


class TestNextRunWithDefer:
    def test_next_respects_retry_after(self, tmp_path):
        """When the deferral date is later than the nominal deadline, prochaine returns it."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() + timedelta(hours=26)
        p = Scheduler(_cfg(
            tmp_path,
            interval_hours=24,
            last_run=derniere.isoformat(timespec="seconds"),
            retry_after=report.isoformat(timespec="seconds"),
        ))
        r = p.next_run()
        assert abs((r - report.replace(microsecond=0)).total_seconds()) < 2

    def test_next_ignores_past_retry_after(self, tmp_path):
        """A stale deferral must not drag the nominal deadline back into the past."""
        derniere = datetime.now() - timedelta(hours=1)
        report = datetime.now() - timedelta(hours=5)
        p = Scheduler(_cfg(
            tmp_path,
            interval_hours=24,
            last_run=derniere.isoformat(timespec="seconds"),
            retry_after=report.isoformat(timespec="seconds"),
        ))
        r = p.next_run()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal

    def test_next_ignores_invalid_retry_after(self, tmp_path):
        """A malformed retenter_apres is silently ignored, prochaine still returns nominal."""
        derniere = datetime.now() - timedelta(hours=1)
        p = Scheduler(_cfg(
            tmp_path,
            interval_hours=24,
            last_run=derniere.isoformat(timespec="seconds"),
            retry_after="not-a-datetime",
        ))
        r = p.next_run()
        nominal = datetime.fromisoformat(
            derniere.isoformat(timespec="seconds")) + timedelta(hours=24)
        assert r == nominal


class TestMarkRunResets:
    def test_reset_after_mark_run(self, tmp_path):
        """mark_run clears any pending deferral (retenter_apres + backoff)."""
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(tmp_path,
                   interval_hours=24,
                   retry_after=report,
                   backoff_level=2)
        p = Scheduler(cfg)
        p.mark_run()
        assert cfg.retry_after == ""
        assert cfg.backoff_level == 0


class TestDisplayTextWithDefer:
    def test_defer_label_active(self, tmp_path):
        """A defer that pushes past the nominal time → label mentions "report"."""
        # Recent last run: nominal time ≈ now + 24 h; we set a defer that
        # goes past that nominal time so it is actually the decisive one.
        report = (datetime.now() + timedelta(hours=26)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            interval_hours=24,
            last_run=datetime.now().isoformat(timespec="seconds"),
            retry_after=report,
        )
        p = Scheduler(cfg)
        assert "report" in next_run_text(p).lower()

    def test_defer_label_before_nominal_ignored(self, tmp_path):
        """Defer earlier than the nominal time → no misleading "report" label.

        Concrete case: the server replied with a short `Retry-After` (1 h)
        but the automatic update is 24 h away anyway. The defer is not the
        decisive factor: the nominal time wins, so the label must stay
        nominal.
        """
        report = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        cfg = _cfg(
            tmp_path,
            interval_hours=24,
            last_run=datetime.now().isoformat(timespec="seconds"),
            retry_after=report,
        )
        p = Scheduler(cfg)
        assert "report" not in next_run_text(p).lower()

    def test_defer_label_past_ignored(self, tmp_path):
        """`retenter_apres` in the past → nominal label (no "report" mention)."""
        past = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        derniere = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        cfg = _cfg(
            tmp_path,
            interval_hours=24,
            last_run=derniere,
            retry_after=past,
        )
        p = Scheduler(cfg)
        assert "report" not in next_run_text(p).lower()
