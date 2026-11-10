"""Exploration du GTFS TCL avec DuckDB : modes, jours de service, fréquences, arrêts les plus desservis.

Usage (après `python -m pipeline.ingest.gtfs`) :
    python -m pipeline.explore.gtfs                      # dernier GTFS téléchargé, prochain mardi
    python -m pipeline.explore.gtfs --date 2026-11-17    # un jour précis
    python -m pipeline.explore.gtfs --dir chemin/vers/extracted

DuckDB lit directement les fichiers .txt (CSV) extraits ; tout est lu en texte (all_varchar)
pour ne pas perdre les zéros en tête des identifiants.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.config import LOCAL_DATA_DIR
from pipeline.ingest.gtfs import GTFS_PREFIX, ROUTE_TYPES, mode_name

TABLES = ("agency", "stops", "routes", "trips", "stop_times", "calendar", "calendar_dates", "feed_info")

# Colonnes facultatives dans la norme : ajoutées à NULL si absentes, pour garder des requêtes simples.
OPTIONAL_COLUMNS = {
    "stops": ("location_type", "parent_station"),
    "routes": ("route_short_name", "route_long_name"),
    "trips": ("direction_id", "trip_headsign"),
}
EMPTY_TABLES = {
    "calendar": (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ),
    "calendar_dates": ("service_id", "date", "exception_type"),
}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def latest_extracted_dir(root: Path = LOCAL_DATA_DIR) -> Path:
    candidates = sorted((root / GTFS_PREFIX).glob("date=*/extracted"))
    if not candidates:
        raise FileNotFoundError(
            f"Aucun GTFS extrait sous {root / GTFS_PREFIX} : lance d'abord python -m pipeline.ingest.gtfs"
        )
    return candidates[-1]


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def connect(gtfs_dir: Path) -> duckdb.DuckDBPyConnection:
    """Connexion en mémoire avec une vue par fichier GTFS et quelques macros utiles."""
    con = duckdb.connect()
    for table in TABLES:
        path = gtfs_dir / f"{table}.txt"
        if path.exists():
            # hive_partitioning = false : sinon DuckDB lit « date=AAAA-MM-JJ » dans le chemin et
            # ajoute une colonne `date` qui écrase celle de calendar_dates.txt.
            con.execute(
                f"CREATE VIEW raw_{table} AS SELECT * FROM read_csv('{_sql_path(path)}', "
                "header = true, all_varchar = true, encoding = 'utf-8', hive_partitioning = false)"
            )
            columns = {row[0] for row in con.execute(f"DESCRIBE raw_{table}").fetchall()}
            extra = [c for c in OPTIONAL_COLUMNS.get(table, ()) if c not in columns]
            select = ", ".join(["*", *(f"NULL::VARCHAR AS {c}" for c in extra)])
            con.execute(f"CREATE VIEW {table} AS SELECT {select} FROM raw_{table}")
        elif table in EMPTY_TABLES:
            cols = ", ".join(f"NULL::VARCHAR AS {c}" for c in EMPTY_TABLES[table])
            con.execute(f"CREATE VIEW {table} AS SELECT {cols} WHERE false")

    # Les heures GTFS peuvent dépasser 24:00:00 (services après minuit) : on compte en secondes.
    con.execute(
        """
        CREATE MACRO gtfs_seconds(t) AS
            TRY_CAST(split_part(trim(t), ':', 1) AS INTEGER) * 3600
            + TRY_CAST(split_part(trim(t), ':', 2) AS INTEGER) * 60
            + TRY_CAST(split_part(trim(t), ':', 3) AS INTEGER)
        """
    )
    modes = pd.DataFrame({"route_type": [str(k) for k in ROUTE_TYPES], "mode": list(ROUTE_TYPES.values())})
    con.register("route_modes_df", modes)
    con.execute("CREATE TABLE route_modes AS SELECT * FROM route_modes_df")
    con.unregister("route_modes_df")
    return con


def active_services_sql(day: dt.date) -> tuple[str, list[str]]:
    """Requête des service_id actifs un jour donné (calendrier + exceptions de calendar_dates)."""
    weekday = WEEKDAYS[day.weekday()]  # issu d'une liste fixe : pas d'injection possible
    ymd = day.strftime("%Y%m%d")
    sql = f"""
        WITH base AS (
            SELECT service_id FROM calendar
            WHERE trim({weekday}) = '1' AND trim(start_date) <= ? AND trim(end_date) >= ?
        ),
        added AS (
            SELECT service_id FROM calendar_dates WHERE trim(date) = ? AND trim(exception_type) = '1'
        ),
        removed AS (
            SELECT service_id FROM calendar_dates WHERE trim(date) = ? AND trim(exception_type) = '2'
        ),
        candidates AS (SELECT service_id FROM base UNION SELECT service_id FROM added)
        SELECT service_id FROM candidates WHERE service_id NOT IN (SELECT service_id FROM removed)
    """
    return sql, [ymd, ymd, ymd, ymd]


def trips_on(con: duckdb.DuckDBPyConnection, day: dt.date) -> int:
    services, params = active_services_sql(day)
    query = f"SELECT count(*) FROM trips WHERE service_id IN ({services})"
    return con.execute(query, params).fetchone()[0]


def reference_day(con: duckdb.DuckDBPyConnection, start: dt.date, horizon_days: int = 60) -> dt.date:
    """Premier mardi (jour ouvré « type ») avec des courses, sinon premier jour avec des courses."""
    days = [start + dt.timedelta(days=i) for i in range(horizon_days)]
    for day in days:
        if day.weekday() == 1 and trips_on(con, day) > 0:
            return day
    for day in days:
        if trips_on(con, day) > 0:
            return day
    raise ValueError(f"Aucune course entre le {days[0]} et le {days[-1]}")


def overview(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT 'arrêts (location_type 0)' AS element,
               count(*) FILTER (WHERE coalesce(nullif(trim(location_type), ''), '0') = '0') AS nombre
        FROM stops
        UNION ALL SELECT 'stations (location_type 1)', count(*) FILTER (WHERE trim(location_type) = '1')
        FROM stops
        UNION ALL SELECT 'lignes', count(*) FROM routes
        UNION ALL SELECT 'courses', count(*) FROM trips
        UNION ALL SELECT 'horaires (stop_times)', count(*) FROM stop_times
        """
    ).df()


def routes_by_mode(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        """
        SELECT trim(route_type) AS route_type, count(*) AS lignes,
               string_agg(route_short_name, ', ' ORDER BY route_short_name) AS exemples
        FROM routes GROUP BY 1 ORDER BY lignes DESC
        """
    ).df()
    df.insert(0, "mode", df["route_type"].map(mode_name))
    df["exemples"] = df["exemples"].fillna("").str.slice(0, 80)
    return df


def trips_per_day(con: duckdb.DuckDBPyConnection, start: dt.date, days: int = 14) -> pd.DataFrame:
    rows = []
    for i in range(days):
        day = start + dt.timedelta(days=i)
        rows.append(
            {
                "jour": day.isoformat(),
                "jour_semaine": WEEKDAYS[day.weekday()],
                "courses": trips_on(con, day),
            }
        )
    return pd.DataFrame(rows)


def headways(
    con: duckdb.DuckDBPyConnection,
    day: dt.date,
    start: str = "07:00:00",
    end: str = "09:00:00",
    modes: tuple[str, ...] = ("metro", "tramway", "funiculaire"),
) -> pd.DataFrame:
    """Intervalle moyen entre deux départs du terminus, par ligne et par sens, sur une plage horaire."""
    services, params = active_services_sql(day)
    mode_list = ", ".join(f"'{m}'" for m in modes)  # valeurs internes, pas de saisie utilisateur
    query = f"""
        WITH active_trips AS (
            SELECT trip_id, route_id, coalesce(nullif(trim(direction_id), ''), '?') AS sens
            FROM trips WHERE service_id IN ({services})
        ),
        first_departure AS (
            SELECT st.trip_id,
                   arg_min(gtfs_seconds(st.departure_time), TRY_CAST(st.stop_sequence AS INTEGER)) AS depart_s
            FROM stop_times st JOIN active_trips USING (trip_id)
            WHERE nullif(trim(st.departure_time), '') IS NOT NULL
            GROUP BY st.trip_id
        )
        SELECT r.route_short_name AS ligne, m.mode, a.sens, count(*) AS departs,
               round((gtfs_seconds(?) - gtfs_seconds(?)) / 60.0 / count(*), 1) AS intervalle_moyen_min
        FROM first_departure f
        JOIN active_trips a USING (trip_id)
        JOIN routes r USING (route_id)
        LEFT JOIN route_modes m ON m.route_type = trim(r.route_type)
        WHERE f.depart_s >= gtfs_seconds(?) AND f.depart_s < gtfs_seconds(?) AND m.mode IN ({mode_list})
        GROUP BY ALL
        ORDER BY m.mode, ligne, a.sens
    """
    return con.execute(query, [*params, end, start, start, end]).df()


def busiest_stops(con: duckdb.DuckDBPyConnection, day: dt.date, limit: int = 15) -> pd.DataFrame:
    """Arrêts (regroupés par station) avec le plus de passages sur la journée."""
    services, params = active_services_sql(day)
    query = f"""
        WITH active_trips AS (SELECT trip_id FROM trips WHERE service_id IN ({services})),
        passages AS (
            SELECT coalesce(nullif(trim(s.parent_station), ''), s.stop_id) AS station_id
            FROM stop_times st
            JOIN active_trips USING (trip_id)
            JOIN stops s ON s.stop_id = st.stop_id
        )
        SELECT p.station_id, any_value(s.stop_name) AS nom, count(*) AS passages
        FROM passages p
        LEFT JOIN stops s ON s.stop_id = p.station_id
        GROUP BY p.station_id
        ORDER BY passages DESC, p.station_id
        LIMIT {int(limit)}
    """
    return con.execute(query, params).df()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", type=Path, help="dossier des .txt extraits (défaut : dernier téléchargé)")
    parser.add_argument("--date", type=dt.date.fromisoformat, help="jour analysé (AAAA-MM-JJ)")
    args = parser.parse_args(argv)

    gtfs_dir = args.dir or latest_extracted_dir()
    con = connect(gtfs_dir)
    today = dt.date.today()
    day = args.date or reference_day(con, today)

    pd.set_option("display.width", 140)
    pd.set_option("display.max_rows", 200)
    sections = [
        (f"GTFS lu dans {gtfs_dir}", overview(con)),
        ("Lignes par mode", routes_by_mode(con)),
        ("Courses par jour (14 prochains jours)", trips_per_day(con, today)),
        (f"Intervalle moyen entre deux départs, 7 h - 9 h, le {day}", headways(con, day)),
        (f"Stations les plus desservies le {day}", busiest_stops(con, day)),
    ]
    for title, df in sections:
        print(f"\n=== {title}\n{df.to_string(index=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
