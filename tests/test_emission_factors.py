from __future__ import annotations

import dataclasses
import datetime as dt
import logging

import pytest
from impactco2_sample import api_response

from pipeline.ingest import emission_factors as ef

TODAY = dt.date(2026, 11, 10)


class FakeResponse:
    def __init__(self, doc, status_code=200):
        self._doc = doc
        self.status_code = status_code

    def json(self):
        return self._doc

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Imite l'API : renvoie la réponse avec ou sans construction selon le paramètre reçu."""

    def __init__(self, status_code=200):
        self.calls = []
        self.status_code = status_code

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(api_response(bool(params["includeConstruction"])), self.status_code)


@pytest.fixture
def factors():
    return ef.build_factors(api_response(True), api_response(False), TODAY)


def by_mode(factors):
    return {f.mode: f for f in factors}

# Appel de l'API

def test_fetch_sends_bearer_key_and_parameters():
    session = FakeSession()
    ef.fetch(True, "ma-cle", session=session)
    call = session.calls[0]
    assert call["headers"] == {"Authorization": "Bearer ma-cle"}
    assert call["params"]["km"] == 1
    assert call["params"]["includeConstruction"] == 1
    assert call["params"]["transports"] == "4,5,9,16,10,11,7,8,30"


def test_fetch_without_key_is_anonymous():
    session = FakeSession()
    ef.fetch(False, None, session=session)
    assert session.calls[0]["headers"] == {}
    assert session.calls[0]["params"]["includeConstruction"] == 0


def test_api_warning_is_logged_once(caplog):
    with caplog.at_level(logging.WARNING, logger="emission_factors"):
        ef.run(None, session=FakeSession(), today=TODAY)
    assert caplog.text.count("pas authentifiée") == 1


def test_fetch_refused_key():
    with pytest.raises(ef.FactorsError, match="403"):
        ef.fetch(True, "mauvaise", session=FakeSession(status_code=403))


def test_run_makes_two_calls():
    session = FakeSession()
    factors = ef.run("ma-cle", session=session, today=TODAY)
    assert [c["params"]["includeConstruction"] for c in session.calls] == [1, 0]
    assert len(factors) == len(ef.MODES)

# Construction des facteurs

def test_values_in_grams_per_km(factors):
    f = by_mode(factors)
    assert f["voiture_thermique"].total_g_per_km == pytest.approx(142.2534, abs=1e-3)
    assert f["voiture_thermique"].usage_g_per_km == pytest.approx(110.5578, abs=1e-3)
    assert f["voiture_thermique"].construction_g_per_km == pytest.approx(31.6957, abs=1e-3)
    assert f["voiture_electrique"].total_g_per_km == pytest.approx(67.3653, abs=1e-3)
    assert f["bus_thermique"].total_g_per_km == pytest.approx(122.42)
    assert f["bus_electrique"].total_g_per_km == pytest.approx(21.7)
    assert f["tramway"].total_g_per_km == pytest.approx(4.28)
    assert f["metro"].total_g_per_km == pytest.approx(4.44)
    assert f["velo_electrique"].total_g_per_km == pytest.approx(10.95)
    assert f["marche"].total_g_per_km == 0


def test_bike_is_construction_only(factors):
    velo = by_mode(factors)["velo"]
    assert velo.usage_g_per_km == 0
    assert velo.construction_g_per_km == pytest.approx(0.17)


def test_metadata(factors):
    car = by_mode(factors)["voiture_thermique"]
    assert car.impactco2_id == 4
    assert car.impactco2_name == "Voiture thermique"
    assert car.hypothese == "voiture moyenne, conducteur seul"
    assert "Modélisation de l'empreinte carbone de la voiture" in car.source
    assert car.retrieved_on == "2026-11-10"


def test_missing_mode_in_response():
    with pytest.raises(ef.FactorsError, match="tramway"):
        ef.build_factors(api_response(True, drop=10), api_response(False), TODAY)


def test_response_without_data():
    with pytest.raises(ef.FactorsError, match="data"):
        ef.parse_response({"error": "oops"})

# Contrôles de cohérence

def replace(factors, mode, **changes):
    return [dataclasses.replace(f, **changes) if f.mode == mode else f for f in factors]


def test_validate_accepts_real_values(factors):
    ef.validate(factors)


def test_validate_rejects_negative_value(factors):
    with pytest.raises(ef.FactorsError, match="négative"):
        ef.validate(replace(factors, "tramway", construction_g_per_km=-1.0))


def test_validate_rejects_walking_emissions(factors):
    with pytest.raises(ef.FactorsError, match="marche"):
        ef.validate(replace(factors, "marche", total_g_per_km=3.0))


def test_validate_rejects_absurd_ordering(factors):
    with pytest.raises(ef.FactorsError, match="ordre"):
        ef.validate(replace(factors, "metro", total_g_per_km=500.0))


def test_validate_rejects_wrong_unit():
    # Réponse pour 1000 km au lieu de 1 : tout est multiplié par 1000, l'ordre reste juste.
    with pytest.raises(ef.FactorsError, match="unité"):
        ef.build_factors(api_response(True, km=1000), api_response(False, km=1000), TODAY)

# CSV versionné et dérive

def test_csv_roundtrip(factors, tmp_path):
    path = ef.write_csv(factors, tmp_path / "reference" / "emission_factors.csv")
    assert ef.read_csv(path) == factors
    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(ef.COLUMNS)


def test_differences_ignore_tiny_changes(factors):
    nudged = replace(factors, "metro", total_g_per_km=4.44 * 1.005)
    assert ef.differences(nudged, factors) == []


def test_differences_report_real_changes(factors):
    changed = replace(factors, "bus_thermique", total_g_per_km=130.0)
    assert ef.differences(changed, factors) == ["bus_thermique.total_g_per_km : 122.42 -> 130.0"]


def test_main_writes_then_checks(monkeypatch, tmp_path, factors):
    monkeypatch.setattr(ef, "run", lambda api_key: factors)
    monkeypatch.setenv("IMPACTCO2_API_KEY", "ne-doit-pas-fuiter")
    path = tmp_path / "emission_factors.csv"
    assert ef.main(["--csv", str(path)]) == 0
    assert "ne-doit-pas-fuiter" not in path.read_text(encoding="utf-8")
    assert ef.main(["--check", "--csv", str(path)]) == 0

    monkeypatch.setattr(ef, "run", lambda api_key: replace(factors, "tramway", total_g_per_km=9.0))
    assert ef.main(["--check", "--csv", str(path)]) == 1


def test_versioned_reference_csv_is_valid():
    factors = ef.read_csv()
    ef.validate(factors)
    assert [f.mode for f in factors] == [mode for mode, _, _, _ in ef.MODES]
