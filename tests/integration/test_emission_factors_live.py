"""Test d'intégration : vraie API Impact CO2 comparée au CSV versionné.

Exclu de `pytest -q`. À lancer avec : pytest -m integration
Échoue si l'ADEME a modifié ses facteurs : relancer `python -m pipeline.ingest.emission_factors`,
relire docs/methodologie-co2.md, puis commiter le CSV mis à jour.
"""

import pytest

from pipeline.config import impactco2_api_key
from pipeline.ingest import emission_factors as ef

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_factors():
    # Sans clé, l'API répond quand même (avec un avertissement) : le test reste utile en local.
    return ef.run(impactco2_api_key())


def test_live_factors_are_consistent(live_factors):
    ef.validate(live_factors)
    assert [f.mode for f in live_factors] == [mode for mode, _, _, _ in ef.MODES]


def test_live_factors_match_the_versioned_csv(live_factors):
    drift = ef.differences(live_factors, ef.read_csv())
    assert not drift, "Facteurs modifiés par l'ADEME, mettre à jour le CSV : " + " ; ".join(drift)
