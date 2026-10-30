import json

import pandas as pd
import pytest
from conftest import GBFS_V2, GBFS_V3, INFORMATION_V3, NOW, STATUS_V2, STATUS_V3

from pipeline.config import HubSettings
from pipeline.ingest import velov
from pipeline.ingest.compact import merge_parts
from pipeline.ingest.gbfs import (
    GBFSError,
    discover_feeds,
    parse_station_information,
    parse_station_status,
    quality_warnings,
)


@pytest.mark.parametrize(("doc", "version"), [(GBFS_V2, "v2"), (GBFS_V3, "v3")])
def test_discover_feeds(doc, version):
    feeds = discover_feeds(doc)
    assert feeds["station_status"].endswith(f"/{version}/station_status.json")
    assert "station_information" in feeds


def test_discover_feeds_empty():
    with pytest.raises(GBFSError):
        discover_feeds({"data": {}})


def test_parse_status_v2():
    df = parse_station_status(STATUS_V2, NOW).set_index("station_id")
    assert len(df) == 3
    assert df.loc["2010", "num_bikes_available"] == 7
    assert df.loc["2010", "last_reported"] == pd.Timestamp("2026-10-29T12:59:10Z")
    assert df.loc["2010", "is_renting"] == True  # noqa: E712 (booléen pandas)
    assert df.loc["3082", "is_renting"] == False  # noqa: E712
    assert str(df["num_bikes_available"].dtype) == "Int16"


def test_parse_status_v3_converts_timezones_and_keeps_vehicle_types():
    df = parse_station_status(STATUS_V3, NOW).set_index("station_id")
    # 13:59:10+01:00 doit devenir 12:59:10 UTC
    assert df.loc["2010", "last_reported"] == pd.Timestamp("2026-10-29T12:59:10Z")
    assert df.loc["2010", "num_bikes_available"] == 7
    assert json.loads(df.loc["2010", "vehicle_types_available"])[1]["count"] == 2
    assert pd.isna(df.loc["7024", "vehicle_types_available"])


def test_parse_information_v3_picks_french_name():
    df = parse_station_information(INFORMATION_V3, NOW).set_index("station_id")
    assert df.loc["7024", "name"] == "Exemple Station B"
    assert df.loc["2010", "capacity"] == 20


def test_empty_status_raises():
    with pytest.raises(GBFSError):
        parse_station_status({"data": {"stations": []}}, NOW)


def test_quality_warnings():
    df = parse_station_status(STATUS_V2, NOW)
    assert quality_warnings(df) == []
    duplicated = pd.concat([df, df.iloc[[0]]])
    assert any("double" in w for w in quality_warnings(duplicated))


def test_status_path_is_partitioned_by_utc_date():
    assert velov.status_path(NOW) == (
        "raw/velov/station_status/date=2026-10-29/status_20261029T130042Z.parquet"
    )


def test_collect_end_to_end_local(tmp_path, monkeypatch):
    """Collecte complète avec un faux client HTTP et une écriture locale."""
    from pipeline import storage

    responses = {
        "https://gbfs.test/gbfs.json": GBFS_V3,
        "https://example.test/v3/station_status.json": STATUS_V3,
    }
    monkeypatch.setattr(
        velov,
        "write_parquet",
        lambda df, path, hub, commit_message: storage.write_parquet(df, path, hub, commit_message, tmp_path),
    )
    destination = velov.collect(
        "status",
        HubSettings(None, None),
        fetch=responses.__getitem__,
        gbfs_url="https://gbfs.test/gbfs.json",
        now=NOW,
    )
    written = pd.read_parquet(destination)
    assert len(written) == 2
    assert written["collected_at"].iloc[0] == NOW


def test_merge_parts_deduplicates():
    a = parse_station_status(STATUS_V2, NOW)
    b = parse_station_status(STATUS_V2, NOW + pd.Timedelta(minutes=15))
    merged = merge_parts([a, b, a])  # `a` lu deux fois (fichier compacté + retardataire)
    assert len(merged) == 6
    assert merged["collected_at"].is_monotonic_increasing