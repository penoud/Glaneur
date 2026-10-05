"""pytest-qt tests for ``DialoguePreferences``' tabbed layout.

Covers the E1 (lot 5.0) refactor: the dialog is now a
``QTabWidget`` with four tabs (``General`` and ``Site`` visible;
``Filters`` and ``Images`` created hidden until E5/E6 populate them).

The important test here is
:class:`TestConfigJsonIsUnchangedAfterEmptyOk` — it pins the
byte-for-byte invariant that a "OK without edits" cycle rewrites the
config file with the same content the user opened. That is the
guardrail the roadmap asked for before the migration lands.

Requires `pytest-qt` and a Qt display: on headless CI, set
``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

import json
import sys

import pytest

# `app` is a top-level module (not under `Glaneur/`), so we import it
# directly. Importing it needs a QApplication instance; pytest-qt
# provides one through the `qapp` fixture.
import app as app_module
from Glaneur.config import Config

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def seeded_config(tmp_path):
    """Config with every field set to a non-default value.

    Loaded through ``Config.load(chemin) → save()`` first so the on-disk
    file is in Config.save's canonical form (``indent=2``,
    ``ensure_ascii=False``) — the byte-for-byte round-trip is then
    meaningful.
    """
    chemin = tmp_path / "c.json"
    # Prime the file with the seed values, then canonicalise via save().
    chemin.write_text(json.dumps({
        "site": "https://example.test",
        "target_dir": str(tmp_path / "photos"),
        "interval_hours": 12,
        "min_width": 1200,
        "sort_mode": "date",
        "source_type": "djangoplicity",
        "image_format": "Small",
        "verify_integrity": True,
        "slideshow_dir": False,
        "close_to_tray": False,
        "notifications": False,
        "check_updates_on_start": False,
        "request_delay": 1.0,
        "last_run": "",
        "retry_after": "",
        "backoff_level": 0,
        "run_at_startup": False,
        "language": "fr",
    }), encoding="utf-8")
    cfg = Config.load(chemin)
    cfg.save()   # canonicalise to save()'s exact byte format
    return cfg


# --------------------------------------------------------------------------- #
# Layout: five tabs — General, Site, Profiles visible; Filters, Images hidden
# --------------------------------------------------------------------------- #

class TestTabbedLayout:
    def test_five_tabs_created(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        assert dlg.onglets.count() == 5

    def test_first_three_tabs_are_visible(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        # General is index 0, Site is index 1, Profiles is index 2.
        assert dlg.onglets.isTabVisible(0)
        assert dlg.onglets.isTabVisible(1)
        assert dlg.onglets.isTabVisible(2)

    def test_filters_and_images_are_hidden(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        assert not dlg.onglets.isTabVisible(dlg._idx_filters)
        assert not dlg.onglets.isTabVisible(dlg._idx_images)


# --------------------------------------------------------------------------- #
# Widget attribute contract: every attribute callers rely on still exists
# --------------------------------------------------------------------------- #

class TestWidgetAttributes:
    """Every widget the outer code (`Fenetre._ouvrir_preferences`,
    `DialoguePreferences.appliquer`, tests) reads by attribute name
    must survive the tab refactor."""

    _EXPECTED_ATTRS = (
        "combo_type", "champ_site", "combo_format", "label_format",
        "champ_dossier",
        "combo_intervalle", "combo_classement", "spin_largeur",
        "case_verifier", "case_diaporama", "case_barre",
        "case_demarrage", "case_maj_demarrage", "combo_langue",
    )

    def test_every_widget_present(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        missing = [a for a in self._EXPECTED_ATTRS if not hasattr(dlg, a)]
        assert not missing, f"missing widgets: {missing!r}"

    def test_seed_values_propagate(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        assert dlg.champ_site.text() == "https://example.test"
        assert dlg.champ_dossier.text() == seeded_config.target_dir
        assert dlg.spin_largeur.value() == 1200
        assert dlg.case_verifier.isChecked() is True
        assert dlg.combo_langue.currentData() == "fr"


# --------------------------------------------------------------------------- #
# The pin: config.json unchanged byte for byte after OK without edits
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="autostart/slideshow side-effects hit real registry")
class TestConfigJsonIsUnchangedAfterEmptyOk:
    """Invariant from ``docs/design/roadmap.md`` §5.0: opening the
    Preferences dialog and clicking OK without any edit must rewrite
    the config file with the exact same content the user saw.

    On non-Windows platforms ``system.autostart`` and
    ``system.set_slideshow_dir`` are no-ops, so ``appliquer()``
    exercises the pure config-write path.
    """

    def test_bytes_unchanged(self, qtbot, seeded_config, tmp_path):
        chemin = seeded_config._path
        before = chemin.read_bytes()
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        # OK without edits: `appliquer()` reads the widgets (all seeded
        # from the same config), validates, saves. No error message.
        probleme = dlg.appliquer()
        assert probleme is None
        after = chemin.read_bytes()
        assert after == before


# --------------------------------------------------------------------------- #
# Profiles tab: add / remove pending mutations, applied on OK
# --------------------------------------------------------------------------- #

class TestProfilesTab:
    """The 'Profiles' tab queues add/remove pending changes; they only
    hit ``cfg._extra_profiles`` on :meth:`DialoguePreferences.appliquer`
    (i.e. the user clicks OK). Cancel discards them.
    """

    def test_initial_list_matches_cfg_extras(self, qtbot, seeded_config):
        seeded_config.add_profile("eso", site="https://eso.example")
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        assert dlg.liste_profils.count() == 1
        # Exact-match assertion on the display label — the ``in`` form
        # tripped CodeQL's py/incomplete-url-substring-sanitization
        # rule (false positive: this is a UI label check, not URL
        # validation), and a full equality is a stronger test anyway.
        assert dlg.liste_profils.item(0).text() == "eso — https://eso.example"

    def test_add_queues_a_pending_profile(self, qtbot, seeded_config):
        """A pending add shows in the list but does NOT touch
        ``cfg._extra_profiles`` yet — the caller may still cancel."""
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        # Skip the QInputDialog by calling the queueing logic directly.
        from Glaneur.config import Profile
        dlg._pending_add_profiles.append(Profile(
            id="pending-id", name="new-profile",
            source_type="wordpress", site="https://n.example",
            target_dir="/tmp/n"))
        dlg._rafraichir_liste_profils()
        assert dlg.liste_profils.count() == 1
        assert dlg.liste_profils.item(0).text().startswith("new-profile")
        # Config unchanged so far.
        assert seeded_config._extra_profiles == []

    def test_cancel_discards_pending_adds(self, qtbot, seeded_config):
        """Not calling appliquer() (i.e. dialog cancelled) leaves the
        seeded config untouched."""
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        from Glaneur.config import Profile
        dlg._pending_add_profiles.append(Profile(
            id="pending-id", name="drop-me",
            source_type="wordpress", site="", target_dir=""))
        # No appliquer() call — the outer window would have rejected.
        assert seeded_config._extra_profiles == []

    @pytest.mark.skipif(sys.platform == "win32",
                        reason="autostart/slideshow hit real registry")
    def test_appliquer_commits_pending_adds(self, qtbot, seeded_config):
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        from Glaneur.config import Profile
        dlg._pending_add_profiles.append(Profile(
            id="new-id", name="new-profile",
            source_type="djangoplicity", site="https://n.example",
            target_dir="/tmp/n"))
        probleme = dlg.appliquer()
        assert probleme is None
        assert len(seeded_config._extra_profiles) == 1
        assert seeded_config._extra_profiles[0].id == "new-id"
        # Persisted to disk too.
        from Glaneur.config import Config
        reloaded = Config.load(seeded_config._path)
        assert len(reloaded._extra_profiles) == 1
        assert reloaded._extra_profiles[0].name == "new-profile"
        # Pending list drained after commit.
        assert dlg._pending_add_profiles == []

    @pytest.mark.skipif(sys.platform == "win32",
                        reason="autostart/slideshow hit real registry")
    def test_appliquer_commits_pending_removes(self, qtbot, seeded_config):
        added = seeded_config.add_profile("condemned", site="https://c.example")
        seeded_config.save()
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        # Simulate user selecting the row and clicking Remove.
        dlg._pending_remove_ids.add(added.id)
        probleme = dlg.appliquer()
        assert probleme is None
        assert seeded_config._extra_profiles == []
        # Pending set drained after commit.
        assert dlg._pending_remove_ids == set()

    def test_pending_remove_of_pending_add_is_a_noop(self, qtbot, seeded_config):
        """Removing a row that was just added (still pending) drops it
        from _pending_add_profiles rather than queuing a remove for a
        non-existent id."""
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        from Glaneur.config import Profile
        pending = Profile(id="pending-id", name="quickly",
                          source_type="wordpress", site="", target_dir="")
        dlg._pending_add_profiles.append(pending)
        dlg._rafraichir_liste_profils()
        dlg.liste_profils.setCurrentRow(0)
        dlg._supprimer_profil()
        assert dlg._pending_add_profiles == []
        assert dlg._pending_remove_ids == set()
        assert dlg.liste_profils.count() == 0

    def test_remove_without_selection_is_a_noop(self, qtbot, seeded_config):
        seeded_config.add_profile("eso", site="https://eso.example")
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        # Nothing selected — clicking Remove does nothing.
        dlg._supprimer_profil()
        assert dlg._pending_remove_ids == set()
        assert dlg.liste_profils.count() == 1


# --------------------------------------------------------------------------- #
# Per-profile edit dialog (lot 5.1 E3 part B step 9)
# --------------------------------------------------------------------------- #

class TestDialogueProfilEdition:
    """DialogueProfilEdition returns a fresh Profile — the source
    profile passed in the constructor is never mutated."""

    def _profil(self, **overrides):
        from Glaneur.config import Profile
        base = {
            "id": "abc123",
            "name": "eso",
            "source_type": "djangoplicity",
            "site": "https://eso.example",
            "target_dir": "/tmp/eso",
            "image_format": "Small",
            "sort_mode": "date",
            "last_run": "2026-09-30T10:00:00",
            "min_width": 1500,   # override preserved through the dialog
        }
        base.update(overrides)
        return Profile(**base)

    def test_seed_values_appear_in_widgets(self, qtbot):
        dlg = app_module.DialogueProfilEdition(None, self._profil())
        qtbot.addWidget(dlg)
        assert dlg.champ_nom.text() == "eso"
        assert dlg.champ_site.text() == "https://eso.example"
        assert dlg.champ_dossier.text() == "/tmp/eso"

    def test_profile_reflects_edited_widgets(self, qtbot):
        dlg = app_module.DialogueProfilEdition(None, self._profil())
        qtbot.addWidget(dlg)
        dlg.champ_nom.setText("eso-hd")
        dlg.champ_site.setText("https://eso.example/hd")
        dlg.champ_dossier.setText("/tmp/eso-hd")
        edited = dlg.profile()
        assert edited.name == "eso-hd"
        assert edited.site == "https://eso.example/hd"
        assert edited.target_dir == "/tmp/eso-hd"

    def test_immutable_fields_preserved(self, qtbot):
        """id, per-profile scheduler state and the min_width override
        stay on the returned Profile — the dialog only edits the six
        user-facing fields."""
        dlg = app_module.DialogueProfilEdition(None, self._profil())
        qtbot.addWidget(dlg)
        dlg.champ_nom.setText("renamed")
        edited = dlg.profile()
        assert edited.id == "abc123"
        assert edited.last_run == "2026-09-30T10:00:00"
        assert edited.min_width == 1500

    def test_source_profile_is_not_mutated(self, qtbot):
        original = self._profil()
        dlg = app_module.DialogueProfilEdition(None, original)
        qtbot.addWidget(dlg)
        dlg.champ_nom.setText("mutated")
        dlg.profile()
        assert original.name == "eso"   # unchanged

    def test_empty_name_falls_back_to_original(self, qtbot):
        dlg = app_module.DialogueProfilEdition(None, self._profil())
        qtbot.addWidget(dlg)
        dlg.champ_nom.setText("   ")
        edited = dlg.profile()
        # Empty / whitespace-only names would break the CLI --profile
        # picker; the dialog silently keeps the previous name.
        assert edited.name == "eso"

    def test_format_hidden_for_wordpress(self, qtbot):
        dlg = app_module.DialogueProfilEdition(
            None, self._profil(source_type="wordpress"))
        qtbot.addWidget(dlg)
        assert not dlg.combo_format.isVisible()

    def test_format_shown_for_djangoplicity(self, qtbot):
        # Show the dialog so visibility flags reflect the real widget tree.
        dlg = app_module.DialogueProfilEdition(
            None, self._profil(source_type="djangoplicity"))
        qtbot.addWidget(dlg)
        dlg.show()
        assert dlg.combo_format.isVisible()
        dlg.hide()


class TestProfilesTabEditing:
    """Editing plumbing on the Profiles tab: pending queue, apply on
    OK, discard on Cancel, in-place mutation for a pending add."""

    def test_edit_pending_add_mutates_in_place(self, qtbot, seeded_config):
        from Glaneur.config import Profile
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        pending = Profile(id="pid", name="original",
                          source_type="wordpress",
                          site="https://x.example",
                          target_dir="/tmp/x",
                          image_format="Large",
                          sort_mode="gallery")
        dlg._pending_add_profiles.append(pending)
        dlg._rafraichir_liste_profils()
        dlg.liste_profils.setCurrentRow(0)
        # Skip the modal edit dialog and apply an edited replacement
        # through the same code path _editer_profil takes.
        edited = Profile(**{**pending.__dict__, "name": "renamed"})
        i = dlg._pending_add_profiles.index(pending)
        dlg._pending_add_profiles[i] = edited
        dlg._rafraichir_liste_profils()
        assert dlg._pending_add_profiles[0].name == "renamed"
        # Existing profile edits queue separately — no bleed.
        assert dlg._pending_edits == {}

    def test_edit_existing_profile_queues_in_pending_edits(
            self, qtbot, seeded_config):
        from Glaneur.config import Profile
        added = seeded_config.add_profile("eso", site="https://eso.example")
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        edited = Profile(**{**added.__dict__, "name": "eso-hd"})
        dlg._pending_edits[added.id] = edited
        dlg._rafraichir_liste_profils()
        assert dlg.liste_profils.item(0).text().startswith("eso-hd")
        # Config unchanged so far.
        assert seeded_config._extra_profiles[0].name == "eso"

    @pytest.mark.skipif(sys.platform == "win32",
                        reason="autostart/slideshow hit real registry")
    def test_appliquer_commits_pending_edits(self, qtbot, seeded_config):
        from Glaneur.config import Profile
        added = seeded_config.add_profile("eso", site="https://eso.example")
        seeded_config.save()
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        dlg._pending_edits[added.id] = Profile(
            **{**added.__dict__, "name": "eso-hd", "min_width": 2000})
        probleme = dlg.appliquer()
        assert probleme is None
        assert seeded_config._extra_profiles[0].name == "eso-hd"
        assert seeded_config._extra_profiles[0].min_width == 2000
        assert dlg._pending_edits == {}

    def test_edit_then_remove_drops_the_edit(self, qtbot, seeded_config):
        """If a queued edit's target profile is then removed in the
        same session, the edit becomes moot — apply order in
        appliquer() must remove BEFORE editing so the phantom edit
        cannot re-insert anything."""
        from Glaneur.config import Profile
        added = seeded_config.add_profile("eso", site="https://eso.example")
        seeded_config.save()
        dlg = app_module.DialoguePreferences(None, seeded_config)
        qtbot.addWidget(dlg)
        dlg._pending_edits[added.id] = Profile(
            **{**added.__dict__, "name": "ignored"})
        dlg._pending_remove_ids.add(added.id)
        dlg.appliquer()
        assert seeded_config._extra_profiles == []
