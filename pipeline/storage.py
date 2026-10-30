"""Écriture des fichiers : dataset Hugging Face, ou disque local en dev."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd

from pipeline.config import LOCAL_DATA_DIR, HubSettings

log = logging.getLogger(__name__)


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", compression="zstd", index=False)
    return buffer.getvalue()


def write_bytes(
    payload: bytes,
    path_in_repo: str,
    hub: HubSettings,
    commit_message: str,
    local_dir: Path = LOCAL_DATA_DIR,
) -> str:
    """Écrit `payload` sur le Hub si configuré, sinon dans `local_dir`. Renvoie la destination."""
    if hub.enabled:
        from huggingface_hub import HfApi  # import local : inutile en mode dev

        HfApi(token=hub.token).upload_file(
            path_or_fileobj=payload,
            path_in_repo=path_in_repo,
            repo_id=hub.repo_id,
            repo_type="dataset",
            commit_message=commit_message,
        )
        return f"hf://datasets/{hub.repo_id}/{path_in_repo}"
    target = local_dir / path_in_repo
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return str(target)


def write_parquet(
    df: pd.DataFrame,
    path_in_repo: str,
    hub: HubSettings,
    commit_message: str,
    local_dir: Path = LOCAL_DATA_DIR,
) -> str:
    payload = to_parquet_bytes(df)
    destination = write_bytes(payload, path_in_repo, hub, commit_message, local_dir)
    log.info("Écrit %s lignes (%s Ko) -> %s", len(df), len(payload) // 1024, destination)
    return destination
