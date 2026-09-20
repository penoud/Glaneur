"""Tests de la logique d'échéance (planificateur)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from servette.config import Config
from servette.scheduler import Planificateur


def _cfg(tmp_path, **kw):
    """Config isolée dans tmp_path, surchargée par kw."""
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
        # relire depuis disque : l'horodatage a été persisté
        cfg2 = Config.charger(tmp_path / "c.json")
        assert cfg2.derniere_execution
        # bien parsable en datetime
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
        # échéance dans ~30 min : derniere = maintenant - 23h30
        t0 = (datetime.now() - timedelta(hours=23, minutes=30)).isoformat(
            timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        r = p.texte_prochaine()
        assert "min" in r
        # < 1h → pas de champ "h"
        assert " h " not in r

    def test_reste_en_heures(self, tmp_path):
        # échéance dans ~3h30 : derniere = maintenant - 20h30
        t0 = (datetime.now() - timedelta(hours=20, minutes=30)).isoformat(
            timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=24,
                               derniere_execution=t0))
        assert " h " in p.texte_prochaine()

    def test_reste_en_jours(self, tmp_path):
        # échéance dans 5 j : intervalle 7 j, derniere = il y a 2 j
        t0 = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        p = Planificateur(_cfg(tmp_path, intervalle_heures=168,
                               derniere_execution=t0))
        assert " j " in p.texte_prochaine()
