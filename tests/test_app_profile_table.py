"""pytest-qt tests for the profile list (lot 5.0 E2).

Covers:

- :func:`app._profile_row` — how a :class:`Config` maps to a row.
- :class:`app.ProfileTableModel` — read-only Qt model contract.
- :meth:`app.Fenetre._status_from_result` — pure helper mapping a
  :class:`Glaneur.engine.RunResult` to the ``Status`` column string.

Requires `pytest-qt` and a Qt display: on headless CI, set
``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt

import app as app_module
from Glaneur.config import Config
from Glaneur.engine import RunResult

# --------------------------------------------------------------------------- #
# Row builder
# --------------------------------------------------------------------------- #

class TestProfileRowFromConfig:
    def test_populates_every_field(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(
            '{"site": "https://example.test",'
            f' "target_dir": "{tmp_path / "photos"}",'
            ' "source_type": "wordpress",'
            ' "last_run": "2026-09-29T15:30:00"}',
            encoding="utf-8",
        )
        cfg = Config.load(chemin)
        row = app_module._profile_row(cfg, status="Idle")

        assert row.name == "example.test"          # host from site URL
        assert row.source_type == "WordPress (API REST)"
        assert row.site == "https://example.test"
        assert row.folder == str(tmp_path / "photos")
        # last_run: T stripped, seconds dropped
        assert row.last_run == "2026-09-29 15:30"
        assert row.status == "Idle"

    def test_unknown_source_type_falls_back_to_raw(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.source_type = "flickr"   # not in SOURCE_TYPES
        row = app_module._profile_row(cfg)
        assert row.source_type == "flickr"

    def test_empty_fields_become_em_dash(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.site = ""
        cfg.target_dir = ""
        cfg.last_run = ""
        row = app_module._profile_row(cfg)
        # The default profile has name="default", which wins over an em
        # dash when site is empty — a named-but-incomplete profile is
        # clearer than a fully anonymous one.
        assert row.name == "default"
        assert row.site == "—"
        assert row.folder == "—"
        assert row.last_run == "—"
        assert row.status == "—"     # empty status also becomes em dash


# --------------------------------------------------------------------------- #
# Qt model contract
# --------------------------------------------------------------------------- #

class TestModelContract:
    def test_starts_empty(self, qtbot):
        m = app_module.ProfileTableModel()
        assert m.rowCount() == 0
        assert m.columnCount() == 6

    def test_set_single_row_publishes_it(self, qtbot):
        m = app_module.ProfileTableModel()
        row = app_module.ProfileRow(
            name="ex", source_type="WordPress (API REST)",
            site="https://example.test", folder="/tmp/p",
            last_run="2026-09-29 15:30", status="Idle",
        )
        m.set_single_row(row)
        assert m.rowCount() == 1
        # DisplayRole returns each field, in column order.
        assert m.data(m.index(0, 0), Qt.DisplayRole) == "ex"
        assert m.data(m.index(0, 1), Qt.DisplayRole) == "WordPress (API REST)"
        assert m.data(m.index(0, 2), Qt.DisplayRole) == "https://example.test"
        assert m.data(m.index(0, 3), Qt.DisplayRole) == "/tmp/p"
        assert m.data(m.index(0, 4), Qt.DisplayRole) == "2026-09-29 15:30"
        assert m.data(m.index(0, 5), Qt.DisplayRole) == "Idle"

    def test_other_roles_return_none(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_single_row(app_module.ProfileRow("a", "b", "c", "d", "e", "f"))
        for role in (Qt.EditRole, Qt.ToolTipRole, Qt.UserRole):
            assert m.data(m.index(0, 0), role) is None

    def test_invalid_index_returns_none(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_single_row(app_module.ProfileRow("a", "b", "c", "d", "e", "f"))
        assert m.data(QModelIndex(), Qt.DisplayRole) is None
        assert m.data(m.index(9, 0), Qt.DisplayRole) is None

    def test_headers_match_design(self, qtbot):
        m = app_module.ProfileTableModel()
        expected = ("Name", "Type", "Site", "Folder", "Last run", "Status")
        for col, libelle in enumerate(expected):
            assert m.headerData(col, Qt.Horizontal, Qt.DisplayRole) == libelle
        # Vertical headers and non-Display roles return None.
        assert m.headerData(0, Qt.Vertical, Qt.DisplayRole) is None
        assert m.headerData(0, Qt.Horizontal, Qt.EditRole) is None

    def test_set_status_only_touches_the_last_column(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_single_row(app_module.ProfileRow(
            "a", "b", "c", "d", "e", "Idle"))
        received: list[tuple[int, int, int, int]] = []
        m.dataChanged.connect(
            lambda tl, br, _roles: received.append(
                (tl.row(), tl.column(), br.row(), br.column())))
        m.set_status("Running…")
        assert received == [(0, 5, 0, 5)]
        assert m.data(m.index(0, 5), Qt.DisplayRole) == "Running…"

    def test_set_status_on_empty_model_is_noop(self, qtbot):
        m = app_module.ProfileTableModel()
        # No row yet — no crash, no signal, no row appears.
        received: list = []
        m.dataChanged.connect(lambda *a: received.append(a))
        m.set_status("Whatever")
        assert m.rowCount() == 0
        assert received == []


class TestMultiRow:
    """Multi-profile display: the table now shows every entry
    :meth:`Glaneur.config.Config.profiles` returns, not just the
    default one."""

    def _row(self, name: str, status: str = "—") -> app_module.ProfileRow:
        return app_module.ProfileRow(
            name=name, source_type="WordPress (API REST)",
            site="https://x", folder="/tmp",
            last_run="—", status=status)

    def test_set_rows_replaces_the_full_list(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A"), self._row("B"), self._row("C")])
        assert m.rowCount() == 3
        assert m.data(m.index(0, 0), Qt.DisplayRole) == "A"
        assert m.data(m.index(1, 0), Qt.DisplayRole) == "B"
        assert m.data(m.index(2, 0), Qt.DisplayRole) == "C"

    def test_set_rows_in_place_keeps_selection(self, qtbot):
        """Same row count -> in-place update -> no modelReset."""
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A"), self._row("B")])
        received: list = []
        m.modelReset.connect(lambda: received.append("reset"))
        m.set_rows([self._row("A2"), self._row("B2")])
        assert received == []
        assert m.data(m.index(0, 0), Qt.DisplayRole) == "A2"

    def test_set_rows_row_count_change_triggers_reset(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A")])
        received: list = []
        m.modelReset.connect(lambda: received.append("reset"))
        m.set_rows([self._row("A"), self._row("B")])
        assert received == ["reset"]

    def test_set_status_targets_row_zero_by_default(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A", "Idle"), self._row("B", "Idle")])
        m.set_status("Running…")
        assert m.data(m.index(0, 5), Qt.DisplayRole) == "Running…"
        assert m.data(m.index(1, 5), Qt.DisplayRole) == "Idle"

    def test_set_status_can_target_any_row(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A", "Idle"), self._row("B", "Idle")])
        m.set_status("Running…", row=1)
        assert m.data(m.index(0, 5), Qt.DisplayRole) == "Idle"
        assert m.data(m.index(1, 5), Qt.DisplayRole) == "Running…"

    def test_set_status_out_of_range_row_is_noop(self, qtbot):
        m = app_module.ProfileTableModel()
        m.set_rows([self._row("A", "Idle")])
        # No crash on a row index that does not exist.
        m.set_status("X", row=9)
        assert m.data(m.index(0, 5), Qt.DisplayRole) == "Idle"


class TestProfileRowFrom:
    """`_profile_row_from(profile, status)` — the multi-profile-friendly
    builder that takes a Profile instance directly."""

    def _profile(self, **overrides):
        from Glaneur.config import Profile
        base = {
            "id": "abc",
            "name": "eso",
            "source_type": "djangoplicity",
            "site": "https://eso.example",
            "target_dir": "/tmp/eso",
            "image_format": "Small",
            "sort_mode": "date",
            "last_run": "2026-09-30T10:00:00",
        }
        base.update(overrides)
        return Profile(**base)

    def test_populates_every_column(self):
        row = app_module._profile_row_from(self._profile(), status="Idle")
        assert row.name == "eso.example"
        assert row.source_type == "Djangoplicity (ESO, ESA/Hubble…)"
        assert row.site == "https://eso.example"
        assert row.folder == "/tmp/eso"
        assert row.last_run == "2026-09-30 10:00"
        assert row.status == "Idle"

    def test_name_falls_back_to_display_name_when_site_empty(self):
        row = app_module._profile_row_from(
            self._profile(site="", name="my-profile"))
        assert row.name == "my-profile"

    def test_status_default_is_em_dash(self):
        row = app_module._profile_row_from(self._profile())
        assert row.status == "—"


class TestSelectedProfileRow:
    """`Fenetre._selected_profile_row` maps the QTableView selection
    to a row index, falling back to 0 (default profile) when the
    selection is missing or invalid."""

    def _fenetre_stub(self, row_count: int, selected: int | None = None):
        """Build a tiny stand-in for Fenetre with just what
        _selected_profile_row reads: the model row count and the
        current selection. Avoids constructing the full main window
        (which spins timers, tray icon, etc.)."""
        from unittest.mock import MagicMock
        model = MagicMock()
        model.rowCount.return_value = row_count
        table = MagicMock()
        selection = MagicMock()
        if selected is None:
            selection.selectedRows.return_value = []
        else:
            idx = MagicMock()
            idx.row.return_value = selected
            selection.selectedRows.return_value = [idx]
        table.selectionModel.return_value = selection
        stub = MagicMock()
        stub.profils_model = model
        stub.table_profils = table
        return stub

    def test_no_selection_returns_zero(self):
        stub = self._fenetre_stub(row_count=3, selected=None)
        assert app_module.Fenetre._selected_profile_row(stub) == 0

    def test_selected_row_is_returned(self):
        stub = self._fenetre_stub(row_count=3, selected=2)
        assert app_module.Fenetre._selected_profile_row(stub) == 2

    def test_out_of_range_selection_falls_back_to_zero(self):
        stub = self._fenetre_stub(row_count=2, selected=5)
        assert app_module.Fenetre._selected_profile_row(stub) == 0

    def test_empty_model_returns_zero(self):
        stub = self._fenetre_stub(row_count=0, selected=None)
        assert app_module.Fenetre._selected_profile_row(stub) == 0


# --------------------------------------------------------------------------- #
# Status pipeline: RunResult → status column
# --------------------------------------------------------------------------- #

class TestStatusPipeline:
    def test_done_shows_download_count(self, qapp):
        res = RunResult(downloaded=42, message="ok")
        assert app_module.Fenetre._status_from_result(res) == "Done — 42 downloaded"

    def test_deferred_with_retry_after(self, qapp):
        res = RunResult(deferred=True, retry_after="2026-09-30T14:00:00",
                        message="deferred")
        assert app_module.Fenetre._status_from_result(res) == (
            "Deferred until 2026-09-30 14:00")

    def test_deferred_without_retry_after(self, qapp):
        res = RunResult(deferred=True, retry_after="", message="deferred")
        assert app_module.Fenetre._status_from_result(res) == "Deferred"

    def test_interrupted(self, qapp):
        res = RunResult(interrupted=True, message="stopped")
        assert app_module.Fenetre._status_from_result(res) == "Interrupted"

    def test_failed_when_only_failures(self, qapp):
        res = RunResult(failures=3, downloaded=0, message="ko")
        assert app_module.Fenetre._status_from_result(res) == "Failed"

    def test_failures_but_partial_success_is_still_done(self, qapp):
        res = RunResult(failures=3, downloaded=1, message="mixed")
        assert app_module.Fenetre._status_from_result(res) == "Done — 1 downloaded"
