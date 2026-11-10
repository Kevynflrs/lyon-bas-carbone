"""Configuration centralisée, lue depuis les variables d'environnement.

Aucun secret n'est écrit dans le code : en local, ils viennent d'un fichier .env
(non versionné) ; dans GitHub Actions, des GitHub Secrets / Variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # en local, charge automatiquement le fichier .env s'il existe
    from dotenv import load_dotenv

    load_dotenv()

except ImportError:
    pass

# Flux GBFS Vélo'v (Métropole de Lyon / JCDecaux, Licence Ouverte 2.0, sans clé).
VELOV_GBFS_URL = os.getenv(
    "VELOV_GBFS_URL",
    "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/gbfs.json",
)

# GTFS TCL (horaires théoriques, SYTRAL Mobilités, Licence Mobilités, compte data.grandlyon requis).
GTFS_TCL_URL = os.getenv(
    "GTFS_TCL_URL",
    "https://download.data.grandlyon.com/files/rdata/tcl_sytral.tcltheorique/GTFS_TCL.ZIP",
)

# API Impact CO2 (ADEME).
IMPACTCO2_API_URL = os.getenv("IMPACTCO2_API_URL", "https://impactco2.fr/api/v1/transport")

def impactco2_api_key() -> str | None:
    return os.getenv("IMPACTCO2_API_KEY") or None

USER_AGENT = os.getenv(
    "PIPELINE_USER_AGENT",
    "lyon-bas-carbone/0.1 (projet portfolio open source)",
)
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "20"))

# Développement local sans accès à Hugging Face.
LOCAL_DATA_DIR = Path(os.getenv("LOCAL_DATA_DIR", "data"))


@dataclass(frozen=True)
class HubSettings:
    """Accès au dataset Hugging Face qui sert de stockage brut (Parquet)."""

    token: str | None
    repo_id: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo_id)


def hub_settings() -> HubSettings:
    return HubSettings(
        token=os.getenv("HF_TOKEN") or None,
        repo_id=os.getenv("HF_DATASET_REPO") or None,
    )


@dataclass(frozen=True)
class GrandLyonCredentials:
    """Identifiants des services data.grandlyon.com (authentification HTTP Basic).

    Le mot de passe est exclu de repr() : il ne peut pas finir dans un log par accident.
    """

    username: str | None
    password: str | None = field(repr=False)

    @property
    def enabled(self) -> bool:
        return bool(self.username and self.password)

    def as_auth(self) -> tuple[str, str]:
        if not self.enabled:
            raise ValueError("GRANDLYON_USERNAME et GRANDLYON_PASSWORD doivent être définis")
        return (self.username, self.password)  # type: ignore[return-value]


def grandlyon_credentials() -> GrandLyonCredentials:
    return GrandLyonCredentials(
        username=os.getenv("GRANDLYON_USERNAME") or None,
        password=os.getenv("GRANDLYON_PASSWORD") or None,
    )
