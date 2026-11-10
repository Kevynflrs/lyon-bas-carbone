"""Test d'intégration : vrai téléchargement du GTFS TCL sur data.grandlyon.com.

Exclu de `pytest -q`. À lancer avec : pytest -m integration
Nécessite GRANDLYON_USERNAME / GRANDLYON_PASSWORD (fichier .env en local, secrets en CI).
Un seul téléchargement pour tout le module : on reste très loin des seuils de la Licence Mobilités.
"""

import datetime as dt
import json
import os

import pytest

from pipeline.config import grandlyon_credentials
from pipeline.explore import gtfs as explore
from pipeline.ingest import gtfs

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    credentials = grandlyon_credentials()
    if not credentials.enabled:
        message = "GRANDLYON_USERNAME et GRANDLYON_PASSWORD ne sont pas définis"
        if os.getenv("CI"):
            pytest.fail(message)  # en CI, l'absence des secrets est une erreur de configuration
        pytest.skip(message)
    return gtfs.run(credentials, root=tmp_path_factory.mktemp("gtfs"))


@pytest.fixture(scope="module")
def manifest(folder):
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def test_live_gtfs_is_currently_valid(manifest):
    for warning in manifest["warnings"]:
        print("Alerte qualité :", warning)  # visibles avec pytest -s ou dans les logs de la CI
    validity = manifest["validity"]
    assert validity["end"] is not None, "Période de validité introuvable"
    today = dt.date.today()
    # Tolérance d'un jour sur le début : le fichier peut être publié la veille de sa validité.
    assert dt.date.fromisoformat(validity["start"]) <= today + dt.timedelta(days=1)
    assert today <= dt.date.fromisoformat(validity["end"])


def test_live_gtfs_has_the_tcl_network(manifest):
    counts = manifest["counts"]
    modes = counts["routes_by_mode"]
    assert modes.get("metro", 0) >= 4, f"Lignes de métro A, B, C, D attendues : {modes}"
    assert modes.get("tramway", 0) >= 5, f"Au moins 5 lignes de tramway attendues : {modes}"
    assert modes.get("funiculaire", 0) >= 1, modes
    assert modes.get("bus", 0) >= 50, modes
    assert counts["stops"] > 1000
    assert counts["trips"] > 1000


def test_live_gtfs_explorable_with_duckdb(folder):
    con = explore.connect(folder / "extracted")
    day = explore.reference_day(con, dt.date.today())
    peak = explore.headways(con, day)
    metro = peak[peak["mode"] == "metro"]
    assert not metro.empty, "Aucun départ de métro entre 7 h et 9 h un jour ouvré"

    # Le jour de référence doit voir circuler les quatre lignes de métro (cf. métro C fermé en 11/2026).
    assert {"A", "B", "C", "D"} <= set(metro["ligne"]), f"Lignes de métro le {day} : {sorted(metro['ligne'])}"
    
    # Un métro lyonnais passe bien plus souvent qu'une fois par quart d'heure en pointe.
    assert metro["intervalle_moyen_min"].median() < 15
    con.close()
