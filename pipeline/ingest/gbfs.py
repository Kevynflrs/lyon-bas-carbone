"""Parsing GBFS indépendant de la version (2.x et 3.0).

Le flux Vélo'v est publié en GBFS 2.3 et 3.0. Les différences qui nous concernent :
- découverte des flux : `data.<langue>.feeds` (2.x) vs `data.feeds` (3.0) ;
- vélos disponibles : `num_bikes_available` (2.x) vs `num_vehicles_available` (3.0) ;
- horodatage : secondes POSIX (2.x) vs texte ISO 8601 (3.0) ;
- nom de station : texte (2.x) vs liste de traductions (3.0).

Ces fonctions sont pures (aucun appel réseau) pour être testables facilement.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

STATUS_COLUMNS = [
    "collected_at",
    "last_reported",
    "station_id",
    "num_bikes_available",
    "num_docks_available",
    "is_installed",
    "is_renting",
    "is_returning",
    "vehicle_types_available",
    "gbfs_version",
]

INFORMATION_COLUMNS = [
    "collected_at",
    "station_id",
    "name",
    "lat",
    "lon",
    "capacity",
    "address",
    "gbfs_version",
]


class GBFSError(ValueError):
    """Flux GBFS absent, vide ou mal formé."""


def feed_version(doc: dict[str, Any]) -> str:
    return str(doc.get("version", "unknown"))


def discover_feeds(gbfs_doc: dict[str, Any], preferred_lang: str = "fr") -> dict[str, str]:
    """Renvoie {nom_du_flux: url} à partir du document gbfs.json."""
    data = gbfs_doc.get("data") or {}
    feeds = data.get("feeds")  # GBFS 3.0
    if feeds is None:  # GBFS 2.x : un bloc par langue
        if not data:
            raise GBFSError("gbfs.json ne contient aucun flux")
        lang_block = data.get(preferred_lang) or next(iter(data.values()))
        feeds = lang_block.get("feeds", [])
    urls = {f["name"]: f["url"] for f in feeds if "name" in f and "url" in f}
    if not urls:
        raise GBFSError("gbfs.json ne contient aucun flux exploitable")
    return urls


def _to_utc(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return pd.Timestamp(int(value), unit="s", tz="UTC")
    return pd.Timestamp(datetime.fromisoformat(str(value).replace("Z", "+00:00"))).tz_convert("UTC")


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _localized_text(value: Any, preferred_lang: str = "fr") -> str | None:
    """GBFS 3.0 : liste [{text, language}] ; GBFS 2.x : simple texte."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        for item in value:
            if item.get("language", "").startswith(preferred_lang):
                return item.get("text")
        return value[0].get("text")
    return str(value)


def _stations(doc: dict[str, Any], feed_name: str) -> list[dict[str, Any]]:
    stations = (doc.get("data") or {}).get("stations")
    if not stations:
        raise GBFSError(f"{feed_name} : aucune station dans le flux")
    return stations


def parse_station_status(doc: dict[str, Any], collected_at: pd.Timestamp) -> pd.DataFrame:
    version = feed_version(doc)
    rows = []
    for s in _stations(doc, "station_status"):
        bikes = s.get("num_vehicles_available", s.get("num_bikes_available"))
        vehicle_types = s.get("vehicle_types_available")
        rows.append(
            {
                "collected_at": collected_at,
                "last_reported": _to_utc(s.get("last_reported")),
                "station_id": str(s["station_id"]),
                "num_bikes_available": bikes,
                "num_docks_available": s.get("num_docks_available"),
                "is_installed": _to_bool(s.get("is_installed")),
                "is_renting": _to_bool(s.get("is_renting")),
                "is_returning": _to_bool(s.get("is_returning")),
                # Conservé brut (JSON) : utile plus tard pour séparer vélos mécaniques / électriques.
                "vehicle_types_available": json.dumps(vehicle_types) if vehicle_types else None,
                "gbfs_version": version,
            }
        )
    df = pd.DataFrame(rows, columns=STATUS_COLUMNS)
    return df.astype(
        {
            "station_id": "string",
            "num_bikes_available": "Int16",
            "num_docks_available": "Int16",
            "is_installed": "boolean",
            "is_renting": "boolean",
            "is_returning": "boolean",
            "vehicle_types_available": "string",
            "gbfs_version": "string",
        }
    )


def parse_station_information(doc: dict[str, Any], collected_at: pd.Timestamp) -> pd.DataFrame:
    version = feed_version(doc)
    rows = [
        {
            "collected_at": collected_at,
            "station_id": str(s["station_id"]),
            "name": _localized_text(s.get("name")),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "capacity": s.get("capacity"),
            "address": _localized_text(s.get("address")),
            "gbfs_version": version,
        }
        for s in _stations(doc, "station_information")
    ]
    df = pd.DataFrame(rows, columns=INFORMATION_COLUMNS)
    return df.astype(
        {
            "station_id": "string",
            "name": "string",
            "lat": "float64",
            "lon": "float64",
            "capacity": "Int16",
            "address": "string",
            "gbfs_version": "string",
        }
    )


def quality_warnings(status: pd.DataFrame) -> list[str]:
    """Contrôles légers : on alerte sans bloquer la collecte."""
    warnings = []
    duplicated = int(status["station_id"].duplicated().sum())
    if duplicated:
        warnings.append(f"{duplicated} station_id en double")
    negative = int(((status["num_bikes_available"] < 0) | (status["num_docks_available"] < 0)).sum())
    if negative:
        warnings.append(f"{negative} stations avec un compteur négatif")
    missing = int(status["num_bikes_available"].isna().sum())
    if missing:
        warnings.append(f"{missing} stations sans nombre de vélos")
    return warnings
