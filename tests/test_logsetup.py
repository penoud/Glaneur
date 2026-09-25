"""Tests du helper de configuration logging."""

from __future__ import annotations

import logging

from Glaneur.logsetup import configure_logging


def _detacher_handlers_wpid():
    """Retire les handlers WPID entre tests pour repartir propre."""
    racine = logging.getLogger()
    for handler in list(racine.handlers):
        if getattr(handler, "_wpid_tag", None):
            racine.removeHandler(handler)
            handler.close()


class TestConfigureLogging:
    def test_cree_le_dossier_et_le_fichier(self, tmp_path):
        _detacher_handlers_wpid()
        chemin = configure_logging(tmp_path)
        assert chemin == tmp_path / "logs" / "app.log"
        assert chemin.parent.is_dir()

        logging.getLogger("t").info("bonjour")
        for h in logging.getLogger().handlers:
            h.flush()
        assert chemin.exists()
        assert "bonjour" in chemin.read_text(encoding="utf-8")

    def test_idempotent_ne_duplique_pas_le_handler(self, tmp_path):
        _detacher_handlers_wpid()
        configure_logging(tmp_path)
        configure_logging(tmp_path)
        configure_logging(tmp_path)
        wpid = [h for h in logging.getLogger().handlers
                if getattr(h, "_wpid_tag", None)]
        assert len(wpid) == 1

    def test_debug_active_niveau_debug(self, tmp_path):
        _detacher_handlers_wpid()
        configure_logging(tmp_path, debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_env_wpid_debug_active_niveau_debug(self, tmp_path, monkeypatch):
        _detacher_handlers_wpid()
        monkeypatch.setenv("WPID_DEBUG", "1")
        configure_logging(tmp_path)
        assert logging.getLogger().level == logging.DEBUG
