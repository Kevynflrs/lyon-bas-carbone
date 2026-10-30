"""Instantané Vélo'v pour le site web : un JSON public d'environ 60 Ko, relu par le front React.

Usage :
    python -m pipeline.export.snapshot            # vers le dataset Hugging Face
    python -m pipeline.export.snapshot --local    # vers ./data/public/velov_latest.json

Le dataset de production doit être public pour que le navigateur puisse lire ce fichier.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from typing import Any

import pandas as pd

from pipeline.config import VELOV_GBFS_URL, HubSettings, hub_settings
from pipeline.http import fetch_json
from pipeline.ingest.gbfs import discover_feeds, parse_station_information, parse_station_status
from pipeline.ingest.velov import outside_service_area
from pipeline.storage import write_bytes

log = logging.getLogger("snapshot")

SNAPSHOT_PATH = "public/velov_latest.json"
SOURCE = "Métropole de Lyon / JCDecaux, Licence Ouverte 2.0"


def _int(value: Any) -> int | None:
    return None if pd.isna(value) else int(value)


def build_snapshot(status: pd.DataFrame, information: pd.DataFrame, generated_at: pd.Timestamp) -> dict:
    """Joint statut et référentiel ; écarte les stations sans position ou hors de la métropole."""
    usable = information.drop(index=outside_service_area(information).index).dropna(subset=["lat", "lon"])
    merged = usable.merge(status, on="station_id", how="inner", suffixes=("", "_status"))

    stations = [
        {
            "id": row.station_id,
            "name": row.name,
            "lat": round(row.lat, 5),
            "lon": round(row.lon, 5),
            "capacity": _int(row.capacity),
            "bikes": _int(row.num_bikes_available),
            "docks": _int(row.num_docks_available),
            "renting": bool(row.is_renting) if not pd.isna(row.is_renting) else False,
            "last_reported": None if pd.isna(row.last_reported) else row.last_reported.isoformat(),
        }
        for row in merged.itertuples()
    ]
    renting = [s for s in stations if s["renting"]]
    return {
        "generated_at": generated_at.isoformat(),
        "source": SOURCE,
        "totals": {
            "stations": len(stations),
            "bikes": sum(s["bikes"] or 0 for s in renting),
            "docks": sum(s["docks"] or 0 for s in renting),
            "empty": sum(1 for s in renting if s["bikes"] == 0),
            "full": sum(1 for s in renting if s["docks"] == 0),
            "out_of_service": len(stations) - len(renting),
        },
        "stations": stations,
    }


def export(hub: HubSettings, fetch: Callable[[str], Any] = fetch_json, gbfs_url: str = VELOV_GBFS_URL) -> str:
    now = pd.Timestamp.now(tz="UTC").floor("s")
    feeds = discover_feeds(fetch(gbfs_url))
    snapshot = build_snapshot(
        parse_station_status(fetch(feeds["station_status"]), now),
        parse_station_information(fetch(feeds["station_information"]), now),
        now,
    )
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    destination = write_bytes(payload, SNAPSHOT_PATH, hub, commit_message=f"snapshot {now:%Y-%m-%dT%H:%MZ}")
    totals = snapshot["totals"]
    log.info(
        "%s stations, %s vélos (%s Ko) -> %s",
        totals["stations"],
        totals["bikes"],
        len(payload) // 1024,
        destination,
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--local", action="store_true", help="écrire dans ./data (ignore HF_TOKEN)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    export(HubSettings(None, None) if args.local else hub_settings())
    return 0


if __name__ == "__main__":
    sys.exit(main())
