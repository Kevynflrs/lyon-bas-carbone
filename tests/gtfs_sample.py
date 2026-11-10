"""Petit GTFS synthétique inspiré du réseau TCL, pour les tests sans réseau.

Contenu volontairement piégeux : BOM UTF-8, arrêt en (0, 0), horaire après minuit (25:10:00),
jour férié retiré du calendrier (11 novembre), service exceptionnel qui prolonge la validité.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def _minutes(hhmm: str, plus: int = 0) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    total = h * 60 + m + plus
    return f"{total // 60:02d}:{total % 60:02d}:00"


# (trip_id, route_id, service_id, direction_id, départ, arrêt de départ, arrêt d'arrivée)
TRIPS = (
    [(f"A0_{i}", "A", "WEEK", "0", _minutes("07:00", 15 * i), "1001", "2001") for i in range(8)]
    + [(f"A1_{i}", "A", "WEEK", "1", _minutes("07:00", 30 * i), "2001", "1001") for i in range(4)]
    + [
        ("A0_night", "A", "WEEK", "0", "25:10:00", "1001", "2001"),
        ("T1_0", "T1", "WEEK", "0", "07:05:00", "2001", "1002"),
        ("T1_1", "T1", "WEEK", "0", "10:05:00", "2001", "1002"),
        ("F1_0", "F1", "WEEK", "0", "08:00:00", "1002", "3001"),
        ("C3_we", "C3", "WE", "0", "09:00:00", "1001", "3001"),
        ("A0_special", "A", "SPECIAL", "0", "08:00:00", "1001", "2001"),
    ]
)


def sample_files() -> dict[str, str]:
    trips = ["route_id,service_id,trip_id,direction_id"]
    stop_times = ["trip_id,arrival_time,departure_time,stop_id,stop_sequence"]
    for trip_id, route_id, service_id, direction, start, origin, destination in TRIPS:
        trips.append(f"{route_id},{service_id},{trip_id},{direction}")
        h, m, _ = (int(x) for x in start.split(":"))
        arrival = f"{h + (m + 5) // 60:02d}:{(m + 5) % 60:02d}:00"
        stop_times.append(f"{trip_id},{start},{start},{origin},1")
        stop_times.append(f"{trip_id},{arrival},{arrival},{destination},2")

    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\n"
        "TCL,TCL SYTRAL,https://www.tcl.fr,Europe/Paris\n",
        # BOM UTF-8 en tête, comme dans beaucoup de GTFS produits sous Windows
        "stops.txt": "\ufeffstop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "S_BEL,Bellecour,45.7578,4.8320,1,\n"
        "1001,Bellecour A,45.7577,4.8321,0,S_BEL\n"
        "1002,Bellecour D,45.7579,4.8319,0,S_BEL\n"
        "2001,Perrache,45.7486,4.8258,0,\n"
        "3001,Fourvière,45.7622,4.8222,0,\n"
        "9999,Arrêt fantôme,0,0,0,\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\n"
        "A,A,Perrache - Vaulx-en-Velin La Soie,1\n"
        "T1,T1,IUT Feyssine - Debourg,0\n"
        "F1,F1,Saint-Jean - Fourvière,7\n"
        "C3,C3,Gare Saint-Paul - Vaulx-en-Velin,3\n",
        "trips.txt": "\n".join(trips) + "\n",
        "stop_times.txt": "\n".join(stop_times) + "\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "WEEK,1,1,1,1,1,0,0,20261102,20261231\n"
        "WE,0,0,0,0,0,1,1,20261102,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\n"
        "WEEK,20261111,2\n"
        "WE,20261111,1\n"
        "SPECIAL,20270105,1\n",
    }


def write_zip(path: Path, files: dict[str, str] | None = None, prefix: str = "") -> Path:
    """Écrit un ZIP GTFS. `prefix` simule une archive dont les fichiers sont dans un sous-dossier."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in (files if files is not None else sample_files()).items():
            archive.writestr(prefix + name, content.encode("utf-8"))
    return path


def write_extracted(folder: Path, files: dict[str, str] | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in (files if files is not None else sample_files()).items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder
