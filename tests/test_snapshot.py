import json

import pandas as pd
from conftest import INFORMATION_V3, NOW, STATUS_V3

from pipeline.config import HubSettings
from pipeline.export import snapshot
from pipeline.ingest.gbfs import parse_station_information, parse_station_status


def test_build_snapshot_joins_and_counts():
    result = snapshot.build_snapshot(
        parse_station_status(STATUS_V3, NOW), parse_station_information(INFORMATION_V3, NOW), NOW
    )
    by_id = {s["id"]: s for s in result["stations"]}
    assert by_id["2010"] == {
        "id": "2010",
        "name": "Exemple Station A",
        "lat": 45.7578,
        "lon": 4.832,
        "capacity": 20,
        "bikes": 7,
        "docks": 13,
        "renting": True,
        "last_reported": "2026-10-29T12:59:10+00:00",
    }
    assert result["totals"] == {
        "stations": 2,
        "bikes": 7,
        "docks": 33,
        "empty": 1,  # la station 7024 n'a aucun vélo
        "full": 0,
        "out_of_service": 0,
    }
    json.dumps(result)  # le résultat doit être sérialisable tel quel


def test_build_snapshot_skips_unlocated_and_out_of_area_stations():
    info = json.loads(json.dumps(INFORMATION_V3))
    info["data"]["stations"][0].update(lat=0.0, lon=0.0)  # position inconnue
    info["data"]["stations"][1].update(lat=48.799974, lon=1.946202)  # station technique en Île-de-France
    result = snapshot.build_snapshot(
        parse_station_status(STATUS_V3, NOW), parse_station_information(info, NOW), NOW
    )
    assert result["stations"] == []
    assert result["totals"]["stations"] == 0


def test_export_writes_json_locally(tmp_path, monkeypatch):
    from pipeline import storage

    gbfs = {
        "version": "3.0",
        "data": {
            "feeds": [
                {"name": "station_status", "url": "u://status"},
                {"name": "station_information", "url": "u://info"},
            ]
        },
    }
    responses = {"u://gbfs": gbfs, "u://status": STATUS_V3, "u://info": INFORMATION_V3}
    monkeypatch.setattr(
        snapshot,
        "write_bytes",
        lambda payload, path, hub, commit_message: storage.write_bytes(
            payload, path, hub, commit_message, tmp_path
        ),
    )
    destination = snapshot.export(HubSettings(None, None), fetch=responses.__getitem__, gbfs_url="u://gbfs")
    assert destination.endswith("velov_latest.json")
    written = json.loads((tmp_path / snapshot.SNAPSHOT_PATH).read_text(encoding="utf-8"))
    assert written["totals"]["stations"] == 2
    assert pd.Timestamp(written["generated_at"]).tzinfo is not None
