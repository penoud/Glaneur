"""Unit tests for :mod:`Glaneur.engine.events`.

Strict scope: the :class:`EngineEvent` dataclass and the ``render_en``
helper. No engine, no Qt, no I/O.
"""

from __future__ import annotations

import pytest

from Glaneur.engine.events import EngineEvent, render_en


class TestEngineEvent:
    def test_frozen(self):
        """``EngineEvent`` is a frozen dataclass — mutation raises.

        Frozen dataclasses raise ``FrozenInstanceError`` (a subclass of
        ``AttributeError``); asserting on ``AttributeError`` keeps the
        test resilient to the exact class name.
        """
        e = EngineEvent("nothing-matches")
        with pytest.raises(AttributeError):
            e.code = "other"  # type: ignore[misc]

    def test_default_params_is_empty(self):
        """A code without params gets an empty mapping, not ``None``."""
        e = EngineEvent("all-up-to-date")
        assert dict(e.params) == {}


class TestRenderEn:
    def test_known_code_renders_with_params(self):
        """A registered code renders using its English template."""
        text = render_en(EngineEvent("already-known", {"count": 15}))
        assert "15" in text
        assert text  # non-empty guarantee

    def test_unknown_code_falls_back_to_code_and_params(self):
        """An unknown code keeps information rather than raising.

        This guards the invariant: a missing template must never silently
        drop the event; the caller still receives something to show.
        """
        text = render_en(EngineEvent("brand-new-code", {"k": "v"}))
        assert "brand-new-code" in text
        assert "k" in text
        assert "v" in text

    def test_missing_placeholder_falls_back_to_code_and_params(self):
        """A ``KeyError`` inside ``str.format`` falls back too.

        ``known-and-todo`` needs ``known`` and ``todo``; omitting
        ``todo`` must not raise — the fallback path renders the raw
        code plus params instead.
        """
        text = render_en(EngineEvent("known-and-todo", {"known": 3}))
        assert "known-and-todo" in text
        assert "3" in text
