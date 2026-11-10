"""Tests du téléchargement et des contrôles du GTFS TCL, sans réseau extérieur.

Un petit serveur HTTP local imite data.grandlyon.com : authentification Basic, 401, 403,
page HTML à la place du ZIP.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from pipeline.config import GrandLyonCredentials
from pipeline.ingest import gtfs
from tests.gtfs_sample import sample_files, write_zip

GOOD = GrandLyonCredentials("kevyn", "s3cret")
BAD = GrandLyonCredentials("kevyn", "mauvais")
TODAY = dt.date(2026, 11, 10)


@pytest.fixture
def sample_zip(tmp_path):
    return write_zip(tmp_path / "GTFS_TCL.zip")


@pytest.fixture
def server(sample_zip):
    """Serveur local : /GTFS_TCL.ZIP (Basic Auth), /forbidden (403), /html (page de connexion)."""
    payload = sample_zip.read_bytes()
    expected = "Basic " + base64.b64encode(b"kevyn:s3cret").decode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/forbidden":
                self.send_response(403)
                self.end_headers()
                return
            if self.path == "/html":
                body = b"<html><body>Connexion</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.headers.get("Authorization") != expected:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="data.grandlyon"')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("ETag", '"abc123"')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silence dans la sortie de pytest
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def session():
    s = requests.Session()
    s.trust_env = False  # ignore un éventuel proxy système pour joindre 127.0.0.1
    return s


# Identifiants


def test_password_never_in_repr():
    assert "s3cret" not in repr(GOOD)
    assert "kevyn" in repr(GOOD)


def test_missing_credentials_are_rejected():
    with pytest.raises(ValueError):
        GrandLyonCredentials("kevyn", None).as_auth()


def test_main_exits_2_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("GRANDLYON_USERNAME", raising=False)
    monkeypatch.delenv("GRANDLYON_PASSWORD", raising=False)
    assert gtfs.main(["--root", str(tmp_path)]) == 2


# Téléchargement


def test_download_with_basic_auth(server, session, tmp_path, sample_zip):
    result = gtfs.download(f"{server}/GTFS_TCL.ZIP", tmp_path / "out" / "g.zip", GOOD, session=session)
    assert result.path.read_bytes() == sample_zip.read_bytes()
    assert result.size_bytes == sample_zip.stat().st_size
    assert len(result.sha256) == 64
    assert result.etag == '"abc123"'
    assert not (tmp_path / "out" / "g.zip.part").exists()


def test_download_wrong_password_gives_clear_error(server, session, tmp_path):
    with pytest.raises(gtfs.GtfsError, match="401"):
        gtfs.download(f"{server}/GTFS_TCL.ZIP", tmp_path / "g.zip", BAD, session=session)
    assert not (tmp_path / "g.zip").exists()


def test_download_forbidden_dataset(server, session, tmp_path):
    with pytest.raises(gtfs.GtfsError, match="403"):
        gtfs.download(f"{server}/forbidden", tmp_path / "g.zip", GOOD, session=session)


def test_download_html_instead_of_zip(server, session, tmp_path):
    with pytest.raises(gtfs.GtfsError, match="HTML"):
        gtfs.download(f"{server}/html", tmp_path / "g.zip", GOOD, session=session)
    assert not (tmp_path / "g.zip").exists()


def test_download_size_guard(server, session, tmp_path):
    with pytest.raises(gtfs.GtfsError, match="plus gros"):
        gtfs.download(f"{server}/GTFS_TCL.ZIP", tmp_path / "g.zip", GOOD, session=session, max_bytes=10)
    assert not (tmp_path / "g.zip.part").exists()


# Archive


def test_members_at_root(sample_zip):
    with gtfs.open_archive(sample_zip) as archive:
        members = gtfs.gtfs_members(archive)
    assert members["stops.txt"] == "stops.txt"
    assert set(gtfs.REQUIRED_FILES) <= set(members)


def test_members_in_a_subfolder(tmp_path):
    path = write_zip(tmp_path / "nested.zip", prefix="GTFS_TCL/")
    with gtfs.open_archive(path) as archive:
        assert gtfs.gtfs_members(archive)["stops.txt"] == "GTFS_TCL/stops.txt"


def test_missing_required_file(tmp_path):
    files = sample_files()
    del files["stop_times.txt"]
    with gtfs.open_archive(write_zip(tmp_path / "g.zip", files)) as archive:
        with pytest.raises(gtfs.GtfsError, match="stop_times.txt"):
            gtfs.gtfs_members(archive)


def test_missing_calendar_files(tmp_path):
    files = sample_files()
    del files["calendar.txt"], files["calendar_dates.txt"]
    with gtfs.open_archive(write_zip(tmp_path / "g.zip", files)) as archive:
        with pytest.raises(gtfs.GtfsError, match="calendar"):
            gtfs.gtfs_members(archive)


def test_unsafe_path_is_rejected(tmp_path):
    files = sample_files()
    files["../evil.txt"] = "x"
    with gtfs.open_archive(write_zip(tmp_path / "g.zip", files)) as archive:
        with pytest.raises(gtfs.GtfsError, match="suspect"):
            gtfs.gtfs_members(archive)


def test_not_a_zip(tmp_path):
    path = tmp_path / "g.zip"
    path.write_text("pas un zip")
    with pytest.raises(gtfs.GtfsError, match="illisible"):
        gtfs.open_archive(path)


# Résumé et qualité


def summary_of(path, today=TODAY):
    with gtfs.open_archive(path) as archive:
        return gtfs.summarize(archive, gtfs.gtfs_members(archive), today)


def test_summary_counts(sample_zip):
    counts = summary_of(sample_zip)["counts"]
    assert counts["stops"] == 5  # BOM ignoré : la colonne stop_id est bien reconnue
    assert counts["stations"] == 1
    assert counts["stops_in_metropole"] == 4  # l'arrêt en (0, 0) n'est pas compté
    assert counts["routes_by_route_type"] == {"0": 1, "1": 1, "3": 1, "7": 1}
    assert counts["routes_by_mode"] == {"bus": 1, "funiculaire": 1, "metro": 1, "tramway": 1}
    assert counts["trips"] == 18
    assert counts["stop_times"] == 36


def test_validity_from_calendar_and_exceptions(sample_zip):
    validity = summary_of(sample_zip)["validity"]
    # le service exceptionnel du 05/01/2027 prolonge la fin du calendrier
    assert validity == {"start": "2026-11-02", "end": "2027-01-05", "source": "calendar"}


def test_feed_info_takes_precedence(tmp_path):
    files = sample_files()
    files["feed_info.txt"] = (
        "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date\n"
        "SYTRAL,https://www.sytral.fr,fr,20261101,20261230\n"
    )
    validity = summary_of(write_zip(tmp_path / "g.zip", files))["validity"]
    assert validity == {"start": "2026-11-01", "end": "2026-12-30", "source": "feed_info.txt"}


def test_warnings_zero_coordinates(sample_zip):
    warnings = summary_of(sample_zip)["warnings"]
    assert any("sans coordonnées" in w and "9999" in w for w in warnings)
    assert not any("périmé" in w for w in warnings)


def test_warnings_expired_and_expiring(sample_zip):
    assert any("GTFS périmé" in w for w in summary_of(sample_zip, dt.date(2027, 2, 1))["warnings"])
    assert any("bientôt périmé" in w for w in summary_of(sample_zip, dt.date(2027, 1, 2))["warnings"])


def test_warnings_missing_mode_and_outside_stop(tmp_path):
    files = sample_files()
    files["routes.txt"] = "route_id,route_short_name,route_long_name,route_type\nA,A,x,1\n"
    files["stops.txt"] += "8888,Plaisir,48.81,1.95,0,\n"
    warnings = summary_of(write_zip(tmp_path / "g.zip", files))["warnings"]
    assert any("Modes attendus absents" in w and "tramway" in w for w in warnings)
    assert any("hors de l'emprise" in w and "8888" in w for w in warnings)


def test_school_stops_in_the_loire_are_inside_the_sytral_area(tmp_path):
    # Cas réel : 581 arrêts de lignes scolaires à Charlieu et au Coteau (Loire) dans le GTFS TCL.
    files = sample_files()
    files["stops.txt"] += (
        "21000,Charlieu Ecole Ste Marie,46.1610,4.1730,0,\n21007,Le Côteau Pincourt,46.0190,4.0890,0,\n"
    )
    summary = summary_of(write_zip(tmp_path / "g.zip", files))
    assert not any("hors de l'emprise" in w for w in summary["warnings"])
    assert summary["counts"]["stops_in_metropole"] == 4  # mais hors de la métropole


def test_extended_route_types_are_grouped_by_family(tmp_path):
    files = sample_files()
    files["routes.txt"] += (
        "PL1,PL1,Pleine Lune 1,705\nJD300,JD300,Ligne scolaire 300,713\nBRT4,BRT4,Substitution T4,714\n"
    )
    counts = summary_of(write_zip(tmp_path / "g.zip", files))["counts"]
    assert counts["routes_by_mode"]["bus"] == 4  # C3 + trois lignes 7xx
    assert counts["routes_by_route_type"] == {"0": 1, "1": 1, "3": 1, "7": 1, "705": 1, "713": 1, "714": 1}


def test_mode_names():
    assert gtfs.mode_name("1") == "metro"
    assert gtfs.mode_name("700") == "bus"
    assert gtfs.mode_name("705") == "bus"  # bus de nuit
    assert gtfs.mode_name("713") == "bus"  # bus scolaire
    assert gtfs.mode_name("401") == "metro"
    assert gtfs.mode_name("900") == "tramway"
    assert gtfs.mode_name("1400") == "funiculaire"
    assert gtfs.mode_name("42") == "autre (42)"
    assert gtfs.mode_name("") == "inconnu ()"


# Bout en bout


def test_run_end_to_end(server, session, tmp_path):
    now = dt.datetime(2026, 11, 10, 9, 30, tzinfo=dt.UTC)
    folder = gtfs.run(GOOD, root=tmp_path, url=f"{server}/GTFS_TCL.ZIP", now=now, session=session)

    assert folder == tmp_path / "raw" / "gtfs" / "tcl" / "date=2026-11-10"
    assert zipfile.is_zipfile(folder / "GTFS_TCL.zip")
    assert sorted(p.name for p in (folder / "extracted").iterdir()) == sorted(sample_files())

    manifest_text = (folder / "manifest.json").read_text(encoding="utf-8")
    assert "s3cret" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["downloaded_at"] == "2026-11-10T09:30:00Z"
    assert manifest["source"]["licence"] == "Licence Mobilités"
    assert manifest["counts"]["routes"] == 4
    assert manifest["validity"]["end"] == "2027-01-05"


def test_run_twice_same_day_replaces_files(server, session, tmp_path):
    now = dt.datetime(2026, 11, 10, 9, 30, tzinfo=dt.UTC)
    url = f"{server}/GTFS_TCL.ZIP"
    gtfs.run(GOOD, root=tmp_path, url=url, now=now, session=session)
    stale = tmp_path / "raw" / "gtfs" / "tcl" / "date=2026-11-10" / "extracted" / "ancien.txt"
    stale.write_text("reste d'une ancienne extraction")
    gtfs.run(GOOD, root=tmp_path, url=url, now=now, session=session)
    assert not stale.exists()
