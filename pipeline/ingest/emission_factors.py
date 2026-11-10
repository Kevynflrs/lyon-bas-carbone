"""Facteurs d'émission des modes de transport, récupérés une fois via l'API Impact CO2 (ADEME).

Usage :
    python -m pipeline.ingest.emission_factors          # (ré)écrit reference/emission_factors.csv
    python -m pipeline.ingest.emission_factors --check  # compare l'API au CSV versionné, sans écrire

Le CSV est versionné dans reference/ (le dossier data/ est ignoré par Git) : le comparateur lit
toujours ce fichier, jamais l'API en direct. Le mode --check, lancé par les tests d'intégration,
signale si l'ADEME a modifié ses facteurs depuis la dernière mise à jour.

Unité : grammes de CO2e par personne et par km, cycle de vie (usage + construction du véhicule).
Deux appels sont faits : avec et sans la construction, pour garder le détail des deux postes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import math
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import requests

from pipeline.config import HTTP_TIMEOUT_S, IMPACTCO2_API_URL, impactco2_api_key
from pipeline.http import build_session

log = logging.getLogger("emission_factors")

REFERENCE_CSV = Path(__file__).resolve().parents[2] / "reference" / "emission_factors.csv"
API_SOURCE = "Impact CO2 (ADEME), API v1 /transport"
CAR_SOURCE = "ADEME, Modélisation de l'empreinte carbone de la voiture (2025)"
BASE_EMPREINTE = "Base Empreinte ADEME"

# (mode interne, identifiant Impact CO2, hypothèse, source sous-jacente)
MODES: tuple[tuple[str, int, str, str], ...] = (
    ("voiture_thermique", 4, "voiture moyenne, conducteur seul", CAR_SOURCE),
    ("voiture_electrique", 5, "voiture moyenne, conducteur seul", CAR_SOURCE),
    ("bus_thermique", 9, "moyenne nationale par voyageur", BASE_EMPREINTE),
    ("bus_electrique", 16, "moyenne nationale par voyageur", BASE_EMPREINTE),
    ("tramway", 10, "moyenne nationale par voyageur", BASE_EMPREINTE),
    ("metro", 11, "moyenne nationale par voyageur", BASE_EMPREINTE),
    ("velo", 7, "vélo mécanique personnel", BASE_EMPREINTE),
    ("velo_electrique", 8, "vélo à assistance électrique personnel", BASE_EMPREINTE),
    ("marche", 30, "aucune émission directe", "convention Impact CO2 (aucun véhicule)"),
)


class FactorsError(RuntimeError):
    """Réponse de l'API inutilisable ou facteurs incohérents."""


@dataclass(frozen=True)
class Factor:
    mode: str
    impactco2_id: int
    impactco2_name: str
    total_g_per_km: float
    usage_g_per_km: float
    construction_g_per_km: float
    hypothese: str
    source: str
    retrieved_on: str


#  API


def fetch(
    include_construction: bool,
    api_key: str | None,
    session: requests.Session | None = None,
    url: str = IMPACTCO2_API_URL,
) -> dict[str, Any]:
    """Émissions pour 1 km de chacun des modes suivis (valeurs en kg de CO2e)."""
    session = session or build_session()
    params = {
        "km": 1,
        "transports": ",".join(str(impactco2_id) for _, impactco2_id, _, _ in MODES),
        "includeConstruction": int(include_construction),
        "language": "fr",
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = session.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT_S)
    if response.status_code in (401, 403):
        raise FactorsError(
            f"Clé API Impact CO2 refusée (HTTP {response.status_code}) : vérifie IMPACTCO2_API_KEY"
        )
    response.raise_for_status()
    return response.json()


def parse_response(doc: dict[str, Any]) -> dict[int, tuple[str, float]]:
    """{identifiant: (nom, kg CO2e pour 1 km)} ; erreur si un mode suivi manque."""
    data = doc.get("data")
    if not isinstance(data, list):
        raise FactorsError("Réponse de l'API sans liste « data »")
    values = {int(item["id"]): (str(item["name"]), float(item["value"])) for item in data}
    missing = [f"{mode} ({impactco2_id})" for mode, impactco2_id, _, _ in MODES if impactco2_id not in values]
    if missing:
        raise FactorsError(f"Modes absents de la réponse de l'API : {', '.join(missing)}")
    return values


def build_factors(
    total_doc: dict[str, Any], usage_doc: dict[str, Any], retrieved_on: dt.date
) -> list[Factor]:
    """Assemble les facteurs à partir des réponses avec et sans construction (kg -> g)."""
    total, usage = parse_response(total_doc), parse_response(usage_doc)
    factors = []
    for mode, impactco2_id, hypothese, source in MODES:
        name, total_kg = total[impactco2_id]
        usage_kg = usage[impactco2_id][1]
        factors.append(
            Factor(
                mode=mode,
                impactco2_id=impactco2_id,
                impactco2_name=name,
                total_g_per_km=round(total_kg * 1000, 4),
                usage_g_per_km=round(usage_kg * 1000, 4),
                construction_g_per_km=round((total_kg - usage_kg) * 1000, 4),
                hypothese=hypothese,
                source=f"{API_SOURCE} ; {source}",
                retrieved_on=retrieved_on.isoformat(),
            )
        )
    validate(factors)
    return factors


def validate(factors: list[Factor]) -> None:
    """Contrôles de cohérence : un facteur absurde ne doit jamais atteindre le site."""
    by_mode = {f.mode: f for f in factors}
    problems = []
    for f in factors:
        numbers = (f.total_g_per_km, f.usage_g_per_km, f.construction_g_per_km)
        if not all(math.isfinite(x) for x in numbers) or min(numbers) < 0:
            problems.append(f"{f.mode} : valeur négative ou non finie {numbers}")
    if by_mode["marche"].total_g_per_km != 0:
        problems.append("la marche doit valoir 0")
    ordering = ("voiture_thermique", "bus_electrique", "metro")
    totals = [by_mode[m].total_g_per_km for m in ordering]
    if not totals[0] > totals[1] > totals[2]:
        problems.append(f"ordre inattendu {dict(zip(ordering, totals, strict=True))}")
    if by_mode["tramway"].total_g_per_km > 50 or by_mode["metro"].total_g_per_km > 50:
        problems.append("tramway ou métro au-dessus de 50 gCO2e/km : unité suspecte")
    if problems:
        raise FactorsError("Facteurs incohérents : " + " ; ".join(problems))


#  CSV versionné

COLUMNS = [f.name for f in fields(Factor)]


def write_csv(factors: list[Factor], path: Path = REFERENCE_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(f) for f in factors)
    return path


def read_csv(path: Path = REFERENCE_CSV) -> list[Factor]:
    with path.open(encoding="utf-8", newline="") as source:
        return [
            Factor(
                **{
                    **row,
                    "impactco2_id": int(row["impactco2_id"]),
                    "total_g_per_km": float(row["total_g_per_km"]),
                    "usage_g_per_km": float(row["usage_g_per_km"]),
                    "construction_g_per_km": float(row["construction_g_per_km"]),
                }
            )
            for row in csv.DictReader(source)
        ]


def differences(current: list[Factor], reference: list[Factor], tolerance: float = 0.01) -> list[str]:
    """Écarts relatifs supérieurs à `tolerance` entre l'API et le CSV versionné."""
    ref = {f.mode: f for f in reference}
    found = []
    for f in current:
        old = ref.get(f.mode)
        if old is None:
            found.append(f"{f.mode} : absent du CSV")
            continue
        for column in ("total_g_per_km", "usage_g_per_km", "construction_g_per_km"):
            new_value, old_value = getattr(f, column), getattr(old, column)
            scale = max(abs(old_value), 1e-9)
            if abs(new_value - old_value) / scale > tolerance and abs(new_value - old_value) > 1e-6:
                found.append(f"{f.mode}.{column} : {old_value} -> {new_value}")
    return found


# CLI


def run(
    api_key: str | None,
    session: requests.Session | None = None,
    today: dt.date | None = None,
) -> list[Factor]:
    session = session or build_session()
    total_doc = fetch(True, api_key, session=session)
    usage_doc = fetch(False, api_key, session=session)
    # L'API peut renvoyer un avertissement (ex. requête non authentifiée) : affiché une seule fois.
    for warning in dict.fromkeys(doc.get("warning") for doc in (total_doc, usage_doc) if doc.get("warning")):
        log.warning("Impact CO2 : %s", warning)
    return build_factors(total_doc, usage_doc, today or dt.date.today())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="comparer au CSV versionné sans l'écrire")
    parser.add_argument("--csv", type=Path, default=REFERENCE_CSV, help="chemin du CSV de référence")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    api_key = impactco2_api_key()
    if not api_key:
        log.warning("IMPACTCO2_API_KEY absente : appel anonyme (toléré par l'API, mais déconseillé)")
    try:
        factors = run(api_key)
    except FactorsError as exc:
        log.error("%s", exc)
        return 1

    for f in factors:
        log.info(
            "%-18s %8.2f gCO2e/km (usage %.2f + construction %.2f)",
            f.mode,
            f.total_g_per_km,
            f.usage_g_per_km,
            f.construction_g_per_km,
        )
    if args.check:
        if not args.csv.exists():
            log.error("CSV de référence introuvable : %s", args.csv)
            return 1
        drift = differences(factors, read_csv(args.csv))
        for line in drift:
            log.error("Facteur modifié par l'ADEME : %s", line)
        if drift:
            log.error("Relance sans --check pour mettre à jour le CSV, puis relis la méthodologie.")
            return 1
        log.info("Facteurs identiques au CSV versionné")
        return 0
    log.info("Écrit %s", write_csv(factors, args.csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
