"""Collecte Vélo'v : un instantané de l'état des stations (toutes les 15 min).

Usage :
    python -m pipeline.ingest.velov status # disponibilités (cron 15 min)
    python -m pipeline.ingest.velov information # référentiel des stations (cron quotidien)

Sans HF_TOKEN / HF_DATASET_REPO, les fichiers sont écrits dans ./data (mode dev).

Partitionnement (dates en UTC, la conversion en heure de Paris se fera dans dbt) :
    raw/velov/station_status/date=YYYY-MM-DD/status_YYYYMMDDTHHMMSSZ.parquet
    raw/velov/station_information/date=YYYY-MM-DD/station_information.parquet
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from typing import Any

import pandas as pd

from pipeline.config import VELOV_GBFS_URL, HubSettings, hub_settings
from pipeline.http import fetch_json
from pipeline.ingest.gbfs import (
    discover_feeds,
    information_quality_warnings,
    parse_station_information,
    parse_station_status,
    quality_warnings,
)
from pipeline.storage import write_parquet

log = logging.getLogger("velov")

STATUS_PREFIX = "raw/velov/station_status"
INFORMATION_PREFIX = "raw/velov/station_information"

# Emprise large de la métropole de Lyon : (lat_min, lat_max, lon_min, lon_max).
LYON_BBOX = (45.55, 45.95, 4.65, 5.15)

Fetcher = Callable[[str], Any]


def outside_service_area(information: pd.DataFrame) -> pd.DataFrame:
    """Stations dont la position connue est hors de la métropole.

    Exemple réel : une station « PLATINE PLAISIR » située dans les Yvelines, probablement
    technique. Elles sont gardées dans les données brutes et exclues en aval (dbt).
    """
    lat_min, lat_max, lon_min, lon_max = LYON_BBOX
    located = information.dropna(subset=["lat", "lon"])
    inside = located["lat"].between(lat_min, lat_max) & located["lon"].between(lon_min, lon_max)
    return located[~inside]


def status_path(collected_at: pd.Timestamp) -> str:
    return f"{STATUS_PREFIX}/date={collected_at:%Y-%m-%d}/status_{collected_at:%Y%m%dT%H%M%SZ}.parquet"


def information_path(collected_at: pd.Timestamp) -> str:
    return f"{INFORMATION_PREFIX}/date={collected_at:%Y-%m-%d}/station_information.parquet"


def collect(
    what: str,
    hub: HubSettings,
    fetch: Fetcher = fetch_json,
    gbfs_url: str = VELOV_GBFS_URL,
    now: pd.Timestamp | None = None,
) -> str:
    collected_at = (now or pd.Timestamp.now(tz="UTC")).floor("s")
    feeds = discover_feeds(fetch(gbfs_url))

    if what == "status":
        df = parse_station_status(fetch(feeds["station_status"]), collected_at)
        for warning in quality_warnings(df):
            log.warning("Qualité : %s", warning)
        log.info(
            "%s stations, %s vélos disponibles, %s stations hors service",
            len(df),
            int(df["num_bikes_available"].sum()),
            int((~df["is_renting"].fillna(False)).sum()),
        )
        path = status_path(collected_at)
    elif what == "information":
        df = parse_station_information(fetch(feeds["station_information"]), collected_at)
        for warning in information_quality_warnings(df):
            log.warning("Qualité : %s", warning)
        outside = outside_service_area(df)
        if not outside.empty:
            log.warning(
                "Qualité : %s stations hors de la métropole (exclues en aval) : %s",
                len(outside),
                ", ".join(f"{row.station_id} {row.name}" for row in outside.itertuples()),
            )
        log.info("%s stations dans le référentiel", len(df))
        path = information_path(collected_at)
    else:
        raise ValueError(f"Type de collecte inconnu : {what}")

    return write_parquet(df, path, hub, commit_message=f"velov {what} {collected_at:%Y-%m-%dT%H:%MZ}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("what", choices=["status", "information"])
    parser.add_argument("--local", action="store_true", help="forcer l'écriture locale (ignore HF_TOKEN)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    hub = HubSettings(None, None) if args.local else hub_settings()
    if not hub.enabled:
        log.info("Hugging Face non configuré : écriture locale dans ./data")
    collect(args.what, hub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
