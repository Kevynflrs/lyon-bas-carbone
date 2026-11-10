"""Tests de l'exploration DuckDB du GTFS, sur le petit GTFS synthétique."""

from __future__ import annotations

import datetime as dt

import pytest
from gtfs_sample import sample_files, write_extracted

from pipeline.explore import gtfs as explore

TUESDAY = dt.date(2026, 11, 10)
HOLIDAY = dt.date(2026, 11, 11)  # mercredi 11 novembre : services de semaine retirés
SATURDAY = dt.date(2026, 11, 14)


@pytest.fixture
def con(tmp_path):
    # Même arborescence qu'en vrai : le motif « date=… » du chemin ne doit pas perturber DuckDB.
    folder = tmp_path / "raw" / "gtfs" / "tcl" / "date=2026-11-10" / "extracted"
    connection = explore.connect(write_extracted(folder))
    yield connection
    connection.close()


def test_hive_style_path_does_not_override_columns(con):
    types = dict(con.execute("SELECT column_name, column_type FROM (DESCRIBE calendar_dates)").fetchall())
    assert types == {"service_id": "VARCHAR", "date": "VARCHAR", "exception_type": "VARCHAR"}


def test_overview_reads_files_with_bom(con):
    counts = dict(explore.overview(con).itertuples(index=False))
    assert counts["arrêts (location_type 0)"] == 5
    assert counts["stations (location_type 1)"] == 1
    assert counts["lignes"] == 4
    assert counts["horaires (stop_times)"] == 36


def test_routes_by_mode(con):
    df = explore.routes_by_mode(con)
    assert dict(zip(df["mode"], df["lignes"], strict=True)) == {
        "metro": 1,
        "tramway": 1,
        "funiculaire": 1,
        "bus": 1,
    }


def test_trips_on_weekday_holiday_weekend_and_special_day(con):
    assert explore.trips_on(con, TUESDAY) == 16  # toutes les courses WEEK
    assert explore.trips_on(con, HOLIDAY) == 1  # seule la course du week-end, ajoutée ce jour-là
    assert explore.trips_on(con, SATURDAY) == 1
    assert explore.trips_on(con, dt.date(2027, 1, 5)) == 1  # service exceptionnel hors calendrier
    assert explore.trips_on(con, dt.date(2027, 3, 1)) == 0


def test_reference_day_is_first_tuesday_with_trips(con):
    assert explore.reference_day(con, dt.date(2026, 11, 7)) == TUESDAY
    # après la fin du calendrier, il ne reste que le service exceptionnel (un mardi)
    assert explore.reference_day(con, dt.date(2027, 1, 1)) == dt.date(2027, 1, 5)
    with pytest.raises(ValueError):
        explore.reference_day(con, dt.date(2027, 6, 1))


def test_headways_in_morning_peak(con):
    df = explore.headways(con, TUESDAY).set_index(["ligne", "sens"])
    assert df.loc[("A", "0"), "departs"] == 8  # la course de 25:10 n'est pas comptée
    assert df.loc[("A", "0"), "intervalle_moyen_min"] == 15.0
    assert df.loc[("A", "1"), "intervalle_moyen_min"] == 30.0
    assert df.loc[("T1", "0"), "departs"] == 1  # la course de 10:05 est hors plage
    assert "C3" not in df.index.get_level_values("ligne")  # bus exclu par défaut, et pas en semaine


def test_times_after_midnight_are_parsed(con):
    late = explore.headways(con, TUESDAY, start="25:00:00", end="26:00:00")
    assert late["departs"].tolist() == [1]


def test_busiest_stops_group_platforms_by_station(con):
    df = explore.busiest_stops(con, TUESDAY)
    top = df.iloc[0]
    # Bellecour A + Bellecour D regroupés sous la station parente S_BEL
    assert (top["station_id"], top["nom"]) == ("S_BEL", "Bellecour")
    assert top["passages"] == 16


def with_closed_metro_c(files: dict[str, str]) -> dict[str, str]:
    """Ajoute un métro C qui ne circule qu'à partir du lundi 16/11 (cas réel de novembre 2026)."""
    files = dict(files)
    files["routes.txt"] += "C,C,Hôtel de Ville - Cuire,1\nJD300,JD300,Ligne scolaire 300,713\n"
    files["trips.txt"] += "C,C_LATER,C_0,0\nJD300,WEEK,JD_0,0\n"
    files["stop_times.txt"] += (
        "C_0,07:30:00,07:30:00,1001,1\nC_0,07:35:00,07:35:00,2001,2\n"
        "JD_0,07:40:00,07:40:00,2001,1\nJD_0,07:50:00,07:50:00,3001,2\n"
    )
    files["calendar.txt"] += "C_LATER,1,1,1,1,1,0,0,20261116,20261231\n"
    return files


@pytest.fixture
def con_closure(tmp_path):
    connection = explore.connect(write_extracted(tmp_path / "extracted", with_closed_metro_c(sample_files())))
    yield connection
    connection.close()


def test_lines_on_shows_stopped_structuring_lines(con_closure):
    lines = explore.lines_on(con_closure, TUESDAY).set_index("ligne")
    assert lines.loc["C", "courses"] == 0
    assert lines.loc["A", "courses"] == 13
    assert "JD300" not in lines.index  # bus scolaire : pas une ligne structurante


def test_reference_day_avoids_a_closed_metro_line(con_closure):
    # Le mardi 10/11, le métro C est fermé : le jour représentatif est le mardi 17/11.
    assert explore.reference_day(con_closure, dt.date(2026, 11, 7)) == dt.date(2026, 11, 17)


def test_extended_route_types_join_their_family(con_closure):
    buses = explore.headways(con_closure, TUESDAY, modes=("bus",))
    assert buses["ligne"].tolist() == ["JD300"]  # route_type 713 classé dans la famille bus


def test_works_without_calendar_txt(tmp_path):
    files = sample_files()
    del files["calendar.txt"]
    con = explore.connect(write_extracted(tmp_path / "extracted", files))
    assert explore.trips_on(con, SATURDAY) == 0
    assert explore.trips_on(con, HOLIDAY) == 1
    con.close()


def test_latest_extracted_dir(tmp_path):
    for day in ("2026-11-01", "2026-11-10"):
        (tmp_path / "raw" / "gtfs" / "tcl" / f"date={day}" / "extracted").mkdir(parents=True)
    assert explore.latest_extracted_dir(tmp_path).parent.name == "date=2026-11-10"
    with pytest.raises(FileNotFoundError):
        explore.latest_extracted_dir(tmp_path / "vide")
