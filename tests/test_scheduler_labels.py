"""Tests for ``Glaneur.scheduler_labels``.

Sits on the UI side of boundary 1: the scheduler itself stays Qt-free,
but the label formatter needs ``QCoreApplication.translate``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from Glaneur.scheduler_labels import next_run_text


class TestNextRunText:
    """Cover every branch of ``next_run_text``."""

    def test_manual_mode(self):
        """interval_hours == 0 → disabled message."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 0
        assert next_run_text(scheduler) == "Automatic update disabled"

    def test_next_run_returns_none(self):
        """When ``next_run()`` is ``None`` the scheduler is effectively
        in manual mode."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = None
        assert next_run_text(scheduler) == "Automatic update disabled"

    def test_imminent(self):
        """Past deadline → imminent message."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = datetime.now() - timedelta(minutes=5)
        scheduler.defer_active.return_value = False
        label = next_run_text(scheduler)
        assert "imminent" in label

    def test_future_many_days(self):
        """More than 24 h → "Xd Xh" format."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = datetime.now() + timedelta(days=3, hours=5, minutes=10)
        scheduler.defer_active.return_value = False
        label = next_run_text(scheduler)
        assert " d " in label
        assert " h" in label
        assert "Next update in" in label

    def test_future_hours_only(self):
        """1–23 h → "Xh MMmin" format."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = datetime.now() + timedelta(hours=2, minutes=30)
        scheduler.defer_active.return_value = False
        label = next_run_text(scheduler)
        assert " h " in label
        assert "min" in label

    def test_future_minutes_only(self):
        """Under 1 h → "Xmin" format."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = datetime.now() + timedelta(minutes=15)
        scheduler.defer_active.return_value = False
        label = next_run_text(scheduler)
        assert "min" in label
        assert " h" not in label

    def test_defer_active(self):
        """Active defer → "Resume deferred, in …" prefix."""
        scheduler = MagicMock()
        scheduler.config.interval_hours = 6
        scheduler.next_run.return_value = datetime.now() + timedelta(hours=2)
        scheduler.defer_active.return_value = True
        label = next_run_text(scheduler)
        assert "Resume deferred" in label
        assert "Next update" not in label
