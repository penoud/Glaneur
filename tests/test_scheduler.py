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
        assert "disabled" in next_run_text(p)

    def test_imminent(self, tmp_path):
        t0 = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
        p = Scheduler(_cfg(tmp_path, interval_hours=24,
                               last_run=t0))
        assert "imminent" in next_run_text(p)

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
        assert " d " in next_run_text(p)


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
        assert "deferred" in next_run_text(p).lower()

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
        assert "deferred" not in next_run_text(p).lower()

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
        assert "deferred" not in next_run_text(p).lower()


# --------------------------------------------------------------------------- #
# Lot 5.2 — per-profile grid (pure computation)
# --------------------------------------------------------------------------- #

from datetime import time as dt_time

from Glaneur.config import Profile
from Glaneur.scheduler import Scheduler as _Scheduler


class TestGridSlot:
    """`Scheduler._grid_slot` is a pure static computation of the
    grid formula ``anchor_dt + k x I/n + m x I``. Every test seeds
    the anchor, k, n, I and threshold explicitly so failures point
    directly at the math, not at any implicit clock or config."""

    _ANCHOR = datetime(2026, 9, 30, 10, 0, 0)  # 10:00 today  # noqa: DTZ001
    _I = 24  # hours

    def test_threshold_before_base_returns_base(self):
        # k=0 base = anchor; threshold < base → m=0 → slot = base.
        threshold = self._ANCHOR - timedelta(hours=4)
        slot = _Scheduler._grid_slot(self._ANCHOR, 0, 1, self._I, threshold)
        assert slot == self._ANCHOR

    def test_threshold_equal_to_base_returns_base(self):
        slot = _Scheduler._grid_slot(self._ANCHOR, 0, 1, self._I, self._ANCHOR)
        assert slot == self._ANCHOR

    def test_threshold_between_slots_returns_next(self):
        # Threshold 2 h after base → m=1 → slot = base + 24 h.
        threshold = self._ANCHOR + timedelta(hours=2)
        slot = _Scheduler._grid_slot(self._ANCHOR, 0, 1, self._I, threshold)
        assert slot == self._ANCHOR + timedelta(hours=24)

    def test_threshold_exactly_at_a_slot_returns_that_slot(self):
        threshold = self._ANCHOR + timedelta(hours=24)
        slot = _Scheduler._grid_slot(self._ANCHOR, 0, 1, self._I, threshold)
        assert slot == threshold

    def test_two_profile_grid_is_staggered_by_I_over_2(self):
        # k=1, n=2 → base offset = 24 / 2 = 12 h.
        slot_k0 = _Scheduler._grid_slot(
            self._ANCHOR, 0, 2, self._I, self._ANCHOR)
        slot_k1 = _Scheduler._grid_slot(
            self._ANCHOR, 1, 2, self._I, self._ANCHOR)
        assert slot_k1 - slot_k0 == timedelta(hours=12)

    def test_three_profile_grid_is_staggered_by_I_over_3(self):
        # k=1 → +8h; k=2 → +16h.
        slots = [_Scheduler._grid_slot(
                    self._ANCHOR, k, 3, self._I, self._ANCHOR)
                 for k in range(3)]
        assert slots[1] - slots[0] == timedelta(hours=8)
        assert slots[2] - slots[0] == timedelta(hours=16)

    def test_anchor_midnight_vs_noon_grids_are_parallel(self):
        """Changing the anchor's time-of-day shifts every slot by the
        same half-interval magnitude — the grids stay parallel, each
        slot a half-day away from the other anchor's slot (the sign
        depends on which anchor sits above the threshold)."""
        anchor_a = datetime(2026, 9, 30, 0, 0, 0)   # midnight  # noqa: DTZ001
        anchor_b = datetime(2026, 9, 30, 12, 0, 0)  # noon  # noqa: DTZ001
        threshold = datetime(2026, 10, 1, 6, 0, 0)  # noqa: DTZ001
        slot_a = _Scheduler._grid_slot(anchor_a, 0, 1, self._I, threshold)
        slot_b = _Scheduler._grid_slot(anchor_b, 0, 1, self._I, threshold)
        assert abs(slot_b - slot_a) == timedelta(hours=12)

    def test_n_of_zero_is_treated_as_one(self):
        # Defensive: n=0 must not divide-by-zero the offset math.
        slot = _Scheduler._grid_slot(
            self._ANCHOR, 0, 0, self._I, self._ANCHOR)
        assert slot == self._ANCHOR


class TestParseAnchor:
    def test_valid_hh_mm(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="14:30")
        assert Scheduler(c)._parse_anchor() == dt_time(14, 30)

    def test_empty_falls_back_to_midnight(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="")
        assert Scheduler(c)._parse_anchor() == dt_time(0, 0)

    def test_malformed_falls_back_to_midnight(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="nope")
        assert Scheduler(c)._parse_anchor() == dt_time(0, 0)


def _profile(**kw) -> Profile:
    base = {"id": "abc", "name": "p"}
    base.update(kw)
    return Profile(**base)


class TestNextRunFor:
    """`Scheduler.next_run_for` combines the grid with the profile's
    scheduler state (`last_run`, `retry_after`) and the config's
    interval and anchor."""

    def test_manual_mode_returns_none(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=0, schedule_anchor="10:00")
        assert Scheduler(c).next_run_for(_profile(), 0, 1) is None

    def test_fresh_profile_is_due_immediately(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="10:00")
        p = _profile(last_run="")
        avant = datetime.now()  # noqa: DTZ005
        prochaine = Scheduler(c).next_run_for(p, 0, 1)
        assert prochaine is not None
        # A fresh profile fires at the first grid slot ≥ now.
        assert prochaine >= avant - timedelta(seconds=1)

    def test_retry_after_pushes_past_nominal(self, tmp_path):
        """A retry_after set well past the nominal slot wins."""
        derniere = (datetime.now() - timedelta(hours=25)  # noqa: DTZ005
                    ).isoformat(timespec="seconds")
        report = (datetime.now() + timedelta(hours=100)  # noqa: DTZ005
                  ).isoformat(timespec="seconds")
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="10:00")
        p = _profile(last_run=derniere, retry_after=report)
        prochaine = Scheduler(c).next_run_for(p, 0, 1)
        assert prochaine == datetime.fromisoformat(report)

    def test_retry_after_older_than_slot_is_ignored(self, tmp_path):
        """A ``retry_after`` older than the nominal grid slot does not
        push the run — the deferral has already expired, so the
        scheduler simply returns the grid slot. Note the slot itself
        can still be in the past (the profile is "overdue"); the
        important invariant is that we did NOT pick the stale
        retry_after."""
        derniere = (datetime.now() - timedelta(hours=25)  # noqa: DTZ005
                    ).isoformat(timespec="seconds")
        report_ancien = (datetime.now() - timedelta(hours=100)  # noqa: DTZ005
                         ).isoformat(timespec="seconds")
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="10:00")
        p = _profile(last_run=derniere, retry_after=report_ancien)
        prochaine = Scheduler(c).next_run_for(p, 0, 1)
        assert prochaine is not None
        # The stale retry_after would have put us 100 h in the past;
        # the chosen slot is nowhere near that.
        assert prochaine > datetime.fromisoformat(report_ancien) + timedelta(hours=50)

    def test_i_over_two_rule_holds(self, tmp_path):
        """A run made "on time" (last_run just now) lands on the next
        slot exactly one interval later, not on the current one."""
        derniere = datetime.now()  # noqa: DTZ005
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="10:00")
        p = _profile(last_run=derniere.isoformat(timespec="seconds"))
        prochaine = Scheduler(c).next_run_for(p, 0, 1)
        assert prochaine is not None
        # ≥ threshold means ≥ last_run + I/2 = now + 12 h.
        assert prochaine >= derniere + timedelta(hours=12)

    def test_two_profiles_are_offset_by_half_the_interval(self, tmp_path):
        """Two identical profiles with the same last_run land exactly
        I/2 apart on the grid — one is at anchor + k x I/2, the other
        at anchor + (k+1) x I/2. The sign of ``d1 - d0`` depends on
        which base ends up on which side of the threshold, so this
        test asserts the magnitude only."""
        derniere = (datetime.now() - timedelta(hours=25)  # noqa: DTZ005
                    ).isoformat(timespec="seconds")
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="10:00")
        p0 = _profile(last_run=derniere)
        p1 = _profile(last_run=derniere)
        s = Scheduler(c)
        d0 = s.next_run_for(p0, 0, 2)
        d1 = s.next_run_for(p1, 1, 2)
        assert d0 is not None and d1 is not None
        assert abs(d1 - d0) == timedelta(hours=12)


class TestIsDueForAndNextDueIndex:
    def test_is_due_for_fresh_profile(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="00:00")
        assert Scheduler(c).is_due_for(_profile(last_run=""), 0, 1) is True

    def test_is_due_for_manual_mode(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=0, schedule_anchor="00:00")
        assert Scheduler(c).is_due_for(_profile(last_run=""), 0, 1) is False

    def test_next_due_index_picks_first_due_profile(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="00:00")
        # p0 ran recently (not due), p1 is fresh (due immediately).
        recent = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
        p0 = _profile(id="p0", last_run=recent)
        p1 = _profile(id="p1", last_run="")
        assert Scheduler(c).next_due_index([p0, p1]) == 1

    def test_next_due_index_returns_none_when_nothing_is_due(self, tmp_path):
        c = _cfg(tmp_path, interval_hours=24, schedule_anchor="00:00")
        recent = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
        p0 = _profile(id="p0", last_run=recent)
        p1 = _profile(id="p1", last_run=recent)
        assert Scheduler(c).next_due_index([p0, p1]) is None
