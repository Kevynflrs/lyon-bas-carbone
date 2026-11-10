"""Téléchargement du GTFS TCL (horaires théoriques du réseau, SYTRAL Mobilités).

Usage :
    python -m pipeline.ingest.gtfs               # télécharge, contrôle et extrait dans ./data
    python -m pipeline.ingest.gtfs --no-extract  # garde seulement le ZIP et le manifeste

Le fichier est servi par data.grandlyon.com derrière une authentification HTTP Basic
(GRANDLYON_USERNAME / GRANDLYON_PASSWORD) et publié sous Licence Mobilités. Il reste donc en
local, dans le dossier data/ non versionné : il n'est pas republié sur Hugging Face.

Fichiers produits (dates en UTC) :
    data/raw/gtfs/tcl/date=YYYY-MM-DD/GTFS_TCL.zip
    data/raw/gtfs/tcl/date=YYYY-MM-DD/manifest.json   (empreinte, validité, comptages, alertes)
    data/raw/gtfs/tcl/date=YYYY-MM-DD/extracted/*.txt (lu par pipeline.explore.gtfs)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import logging
import shutil
import sys
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import requests

from pipeline.config import (
    GTFS_TCL_URL,
    HTTP_TIMEOUT_S,
    LOCAL_DATA_DIR,
    GrandLyonCredentials,
    grandlyon_credentials,
)
from pipeline.http import build_session

log = logging.getLogger("gtfs")

GTFS_PREFIX = Path("raw") / "gtfs" / "tcl"
ARCHIVE_NAME = "GTFS_TCL.zip"
SOURCE = {
    "producer": "SYTRAL Mobilités",
    "dataset": "Horaires théoriques du réseau Transports en Commun Lyonnais",
    "portal": "https://data.grandlyon.com",
    "licence": "Licence Mobilités",
}

REQUIRED_FILES = ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt")
CALENDAR_FILES = ("calendar.txt", "calendar_dates.txt")  # au moins l'un des deux

# Types de lignes GTFS (route_type), y compris quelques types étendus courants.
ROUTE_TYPES = {
    0: "tramway",
    1: "metro",
    2: "train",
    3: "bus",
    4: "ferry",
    5: "tramway_a_cable",
    6: "telepherique",
    7: "funiculaire",
    11: "trolleybus",
    12: "monorail",
    700: "bus",
    800: "trolleybus",
    900: "tramway",
    1400: "funiculaire",
}
EXPECTED_MODES = ("metro", "tramway", "funiculaire", "bus")

# Emprise large des réseaux SYTRAL (bien plus large que la métropole) : (lat_min, lat_max, lon_min, lon_max).
GTFS_BBOX = (45.40, 46.15, 4.30, 5.35)
EXPIRY_WARNING_DAYS = 7
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # garde-fou : le GTFS TCL fait quelques dizaines de Mo


class GtfsError(RuntimeError):
    """Erreur bloquante : téléchargement refusé ou archive inutilisable."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size_bytes: int
    last_modified: str | None
    etag: str | None


# --- Téléchargement -----------------------------------------------------------------------------


def download(
    url: str,
    destination: Path,
    credentials: GrandLyonCredentials,
    session: requests.Session | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> DownloadResult:
    """Télécharge `url` en streaming vers `destination` (écriture atomique via un fichier .part)."""
    session = session or build_session()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    size = 0

    with session.get(url, auth=credentials.as_auth(), stream=True, timeout=HTTP_TIMEOUT_S) as response:
        if response.status_code == 401:
            raise GtfsError(
                "Identifiants refusés (HTTP 401). Vérifie GRANDLYON_USERNAME / GRANDLYON_PASSWORD : "
                "le mot de passe attendu est celui défini pour les services de données dans ton profil "
                "data.grandlyon.com, pas forcément celui de ton compte GrandLyon Connect."
            )
        if response.status_code == 403:
            raise GtfsError(
                "Accès refusé (HTTP 403) : ton compte est reconnu mais n'a pas accès à ce jeu de données. "
                "Demande l'accès au jeu « Horaires théoriques du réseau TCL » sur data.grandlyon.com."
            )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "html" in content_type.lower():
            raise GtfsError(f"Réponse HTML au lieu d'un ZIP (Content-Type : {content_type}).")

        with partial.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                if size == 0 and not chunk.startswith(b"PK"):
                    out.close()
                    partial.unlink(missing_ok=True)
                    raise GtfsError("Le fichier reçu n'est pas un ZIP (signature PK absente).")
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    partial.unlink(missing_ok=True)
                    raise GtfsError(f"Fichier plus gros que prévu (> {max_bytes // 2**20} Mo), abandon.")
                digest.update(chunk)
                out.write(chunk)
        last_modified = response.headers.get("Last-Modified")
        etag = response.headers.get("ETag")

    if size == 0:
        partial.unlink(missing_ok=True)
        raise GtfsError("Fichier vide.")
    partial.replace(destination)  # remplace l'éventuel fichier du jour, y compris sous Windows
    return DownloadResult(destination, digest.hexdigest(), size, last_modified, etag)


# --- Lecture de l'archive -------------------------------------------------------------------------


def gtfs_members(archive: zipfile.ZipFile) -> dict[str, str]:
    """Associe chaque fichier GTFS (ex. 'stops.txt') à son nom dans l'archive.

    Accepte les fichiers à la racine ou dans un unique sous-dossier ; refuse les chemins
    dangereux (absolus, '..') et les doublons.
    """
    members: dict[str, str] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in info.filename:
            raise GtfsError(f"Chemin suspect dans l'archive : {info.filename!r}")
        if path.suffix.lower() != ".txt" or len(path.parts) > 2:
            continue
        name = path.name.lower()
        if name in members:
            raise GtfsError(f"Fichier présent deux fois dans l'archive : {name}")
        members[name] = info.filename

    missing = [name for name in REQUIRED_FILES if name not in members]
    if not any(name in members for name in CALENDAR_FILES):
        missing.append("calendar.txt ou calendar_dates.txt")
    if missing:
        raise GtfsError(f"GTFS incomplet, fichiers manquants : {', '.join(missing)}")
    return members


def open_archive(path: Path) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise GtfsError(f"Archive ZIP illisible : {exc}") from exc
    corrupted = archive.testzip()
    if corrupted:
        archive.close()
        raise GtfsError(f"Archive corrompue (premier fichier en erreur : {corrupted})")
    return archive


def read_rows(archive: zipfile.ZipFile, member: str) -> Iterator[dict[str, str]]:
    """Lit un fichier CSV GTFS ligne à ligne (BOM UTF-8 toléré, espaces des en-têtes retirés)."""
    with archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        reader = csv.reader(text)
        header = [column.strip() for column in next(reader, [])]
        for values in reader:
            if values:
                yield {column: value.strip() for column, value in zip(header, values, strict=False)}


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def mode_name(route_type: str) -> str:
    try:
        code = int(route_type)
    except ValueError:
        return f"inconnu ({route_type})"
    return ROUTE_TYPES.get(code, f"autre ({code})")


# --- Résumé et contrôles qualité ------------------------------------------------------------------


def validity_window(archive: zipfile.ZipFile, members: dict[str, str]) -> dict[str, str | None]:
    """Période couverte : feed_info.txt si renseigné, sinon calendrier + exceptions."""
    if "feed_info.txt" in members:
        for row in read_rows(archive, members["feed_info.txt"]):
            start, end = parse_date(row.get("feed_start_date", "")), parse_date(row.get("feed_end_date", ""))
            if start and end:
                return {"start": start.isoformat(), "end": end.isoformat(), "source": "feed_info.txt"}

    dates: list[dt.date] = []
    if "calendar.txt" in members:
        for row in read_rows(archive, members["calendar.txt"]):
            bounds = (parse_date(row.get("start_date", "")), parse_date(row.get("end_date", "")))
            dates += [d for d in bounds if d]
    if "calendar_dates.txt" in members:
        for row in read_rows(archive, members["calendar_dates.txt"]):
            day = parse_date(row.get("date", ""))
            if day and row.get("exception_type") == "1":
                dates.append(day)
    if not dates:
        return {"start": None, "end": None, "source": None}
    return {"start": min(dates).isoformat(), "end": max(dates).isoformat(), "source": "calendar"}


def summarize(archive: zipfile.ZipFile, members: dict[str, str], today: dt.date) -> dict:
    """Comptages et alertes qualité, sans charger les gros fichiers en mémoire."""
    warnings: list[str] = []

    validity = validity_window(archive, members)
    if validity["end"] is None:
        warnings.append("Période de validité introuvable (ni feed_info, ni calendrier exploitable)")
    else:
        end = dt.date.fromisoformat(validity["end"])
        if end < today:
            warnings.append(f"GTFS périmé : validité terminée le {end}")
        elif (end - today).days < EXPIRY_WARNING_DAYS:
            warnings.append(f"GTFS bientôt périmé : validité jusqu'au {end}")

    lat_min, lat_max, lon_min, lon_max = GTFS_BBOX
    stops_by_type: Counter[str] = Counter()
    missing_coords, outside = [], []
    for row in read_rows(archive, members["stops.txt"]):
        location_type = row.get("location_type") or "0"
        stops_by_type[location_type] += 1
        if location_type not in ("0", "1"):
            continue  # entrées, nœuds génériques... : coordonnées facultatives
        try:
            lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
        except (KeyError, ValueError):
            missing_coords.append(row.get("stop_id", "?"))
            continue
        if lat == 0 and lon == 0:
            missing_coords.append(row.get("stop_id", "?"))
        elif not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            outside.append(f"{row.get('stop_id', '?')} {row.get('stop_name', '')}".strip())
    if missing_coords:
        sample = ", ".join(missing_coords[:10])
        warnings.append(f"{len(missing_coords)} arrêts sans coordonnées valides : {sample}")
    if outside:
        warnings.append(f"{len(outside)} arrêts hors de l'emprise attendue : {', '.join(outside[:10])}")

    routes_by_mode: Counter[str] = Counter(
        mode_name(row.get("route_type", "")) for row in read_rows(archive, members["routes.txt"])
    )
    absent = [mode for mode in EXPECTED_MODES if mode not in routes_by_mode]
    if absent:
        warnings.append(f"Modes attendus absents : {', '.join(absent)}")

    trips = sum(1 for _ in read_rows(archive, members["trips.txt"]))
    stop_times = sum(1 for _ in read_rows(archive, members["stop_times.txt"]))
    if trips == 0 or stop_times == 0:
        warnings.append("Aucune course ou aucun horaire dans le GTFS")

    return {
        "validity": validity,
        "counts": {
            "agencies": sum(1 for _ in read_rows(archive, members["agency.txt"])),
            "stops": stops_by_type.get("0", 0),
            "stations": stops_by_type.get("1", 0),
            "routes": sum(routes_by_mode.values()),
            "routes_by_mode": dict(sorted(routes_by_mode.items())),
            "trips": trips,
            "stop_times": stop_times,
        },
        "files": sorted(members),
        "warnings": warnings,
    }


def extract(archive: zipfile.ZipFile, members: dict[str, str], target: Path) -> Path:
    """Extrait les fichiers GTFS à plat dans `target` (vidé au préalable)."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, member in members.items():
        with archive.open(member) as source, (target / name).open("wb") as out:
            shutil.copyfileobj(source, out)
    return target


# --- Orchestration --------------------------------------------------------------------------------


def snapshot_dir(root: Path, now: dt.datetime) -> Path:
    return root / GTFS_PREFIX / f"date={now:%Y-%m-%d}"


def run(
    credentials: GrandLyonCredentials,
    root: Path = LOCAL_DATA_DIR,
    url: str = GTFS_TCL_URL,
    now: dt.datetime | None = None,
    do_extract: bool = True,
    session: requests.Session | None = None,
) -> Path:
    """Télécharge, contrôle, extrait et écrit le manifeste. Renvoie le dossier du jour."""
    now = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    folder = snapshot_dir(root, now)

    result = download(url, folder / ARCHIVE_NAME, credentials, session=session)
    log.info("Téléchargé %.1f Mo (sha256 %s...)", result.size_bytes / 2**20, result.sha256[:12])

    with open_archive(result.path) as archive:
        members = gtfs_members(archive)
        summary = summarize(archive, members, today=now.date())
        if do_extract:
            extracted = extract(archive, members, folder / "extracted")
            log.info("Extrait %s fichiers dans %s", len(members), extracted)

    for warning in summary["warnings"]:
        log.warning("Qualité : %s", warning)
    counts = summary["counts"]
    log.info(
        "Validité %s -> %s ; %s arrêts, %s lignes %s, %s courses",
        summary["validity"]["start"],
        summary["validity"]["end"],
        counts["stops"],
        counts["routes"],
        counts["routes_by_mode"],
        counts["trips"],
    )

    manifest = {
        "source": {**SOURCE, "url": url},
        "downloaded_at": now.isoformat().replace("+00:00", "Z"),
        "archive": {
            "name": ARCHIVE_NAME,
            "sha256": result.sha256,
            "size_bytes": result.size_bytes,
            "last_modified": result.last_modified,
            "etag": result.etag,
        },
        **summary,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    (folder / "manifest.json").write_text(manifest_text, encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=LOCAL_DATA_DIR, help="dossier racine (défaut : ./data)")
    parser.add_argument("--no-extract", action="store_true", help="ne pas extraire les fichiers .txt")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    credentials = grandlyon_credentials()
    if not credentials.enabled:
        log.error("GRANDLYON_USERNAME et GRANDLYON_PASSWORD doivent être définis (fichier .env en local)")
        return 2
    try:
        folder = run(credentials, root=args.root, do_extract=not args.no_extract)
    except GtfsError as exc:
        log.error("%s", exc)
        return 1
    log.info("GTFS prêt dans %s", folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
