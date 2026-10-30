"""Configuration centralisée, lue depuis les variables d'environnement.

Aucun secret n'est écrit dans le code : en local, ils viennent d'un fichier .env
(non versionné) ; dans GitHub Actions, des GitHub Secrets / Variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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

# Flux ImpactCO2 (API key gratuite, https://impactco2.fr/api).
USER_AGENT = os.getenv(
    "PIPELINE_USER_AGENT",
    "lyon-bas-carbone/0.1 (projet portfolio open source)",
)
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "20"))

# Développement local sans accès à Hugging Face).
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
