"""Tests d'intégration : vrais appels réseau (flux Vélo'v et dataset Hugging Face de staging).

Exclus de `pytest -q`. À lancer avec : pytest -m integration
"""

import os
import uuid

import pandas as pd
import pytest

from pipeline.config import VELOV_GBFS_URL, hub_settings
from pipeline.http import fetch_json
from pipeline.ingest.gbfs import discover_feeds, parse_station_information, parse_station_status
from pipeline.storage import write_parquet

pytestmark = pytest.mark.integration

MIN_STATIONS = 100  # Vélo'v compte plusieurs centaines de stations
LAT_RANGE = (45.55, 45.95)  # emprise large de la métropole de Lyon
LON_RANGE = (4.65, 5.15)


@pytest.fixture(scope="module")
def live():
    """Un seul appel réseau par flux pour tout le module."""
    now = pd.Timestamp.now(tz="UTC")
    feeds = discover_feeds(fetch_json(VELOV_GBFS_URL))
    return {
        "now": now,
        "status": parse_station_status(fetch_json(feeds["station_status"]), now),
        "information": parse_station_information(fetch_json(feeds["station_information"]), now),
    }


def test_live_status_has_enough_valid_stations(live):
    status = live["status"]
    assert len(status) >= MIN_STATIONS
    assert status["station_id"].is_unique
    assert (status["num_bikes_available"].dropna() >= 0).all()
    assert (status["num_docks_available"].dropna() >= 0).all()


def test_live_feed_is_fresh(live):
    freshest = live["status"]["last_reported"].max()
    assert live["now"] - freshest < pd.Timedelta(hours=1), f"Flux figé ? Dernier relevé : {freshest}"


def test_live_stations_are_in_lyon_and_match_status(live):
    info, status = live["information"], live["status"]
    assert info["lat"].between(*LAT_RANGE).all()
    assert info["lon"].between(*LON_RANGE).all()
    known = status["station_id"].isin(info["station_id"]).mean()
    assert known > 0.9, f"Seulement {known:.0%} des stations du statut sont dans le référentiel"


def test_hugging_face_write_read_delete():
    """Écrit un petit fichier dans le dataset de staging, le relit, puis le supprime."""
    if os.getenv("ALLOW_HUB_WRITE_TESTS") != "1":
        pytest.skip("Écriture Hugging Face désactivée (ALLOW_HUB_WRITE_TESTS != 1)")
    hub = hub_settings()
    if not hub.enabled:
        pytest.fail("HF_TOKEN et HF_DATASET_REPO doivent être définis pour ce test")

    from huggingface_hub import HfApi, hf_hub_download

    expected = pd.DataFrame({"station_id": ["a", "b"], "num_bikes_available": [1, 2]})
    path = f"ci/integration/{uuid.uuid4().hex}.parquet"
    write_parquet(expected, path, hub, commit_message="ci: test d'intégration")
    try:
        local_copy = hf_hub_download(hub.repo_id, path, repo_type="dataset", token=hub.token)
        pd.testing.assert_frame_equal(pd.read_parquet(local_copy), expected)
    finally:
        HfApi(token=hub.token).delete_file(
            path, hub.repo_id, repo_type="dataset", commit_message="ci: nettoyage du test d'intégration"
        )
