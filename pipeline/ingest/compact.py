"""Compaction quotidienne : fusionne les ~96 petits fichiers d'une journée en un seul.

Pourquoi : collecter toutes les 15 min produit ~35 000 fichiers par an. Hugging Face
recommande de rester bien en dessous de 100 000 fichiers par dépôt, et les moteurs
analytiques (DuckDB) lisent beaucoup plus vite peu de gros fichiers que beaucoup de
petits (« small files problem »).

La compaction est idempotente : relancée sur un jour déjà compacté, elle fusionne
le fichier compacté avec d'éventuels retardataires et dédoublonne.

Usage :
    python -m pipeline.ingest.compact # compacte la veille (UTC)
    python -m pipeline.ingest.compact --date 2026-11-02
"""

from __future__ import annotations
import argparse
import logging
import sys
from datetime import date, timedelta
import pandas as pd
from pipeline.config import hub_settings
from pipeline.ingest.velov import STATUS_PREFIX
from pipeline.storage import to_parquet_bytes

log = logging.getLogger("compact")
COMPACTED_NAME = "compacted.parquet"


def merge_parts(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatène, dédoublonne (station, instant de collecte) et trie."""
    if not parts:
        raise ValueError("Aucun fichier à fusionner")
    merged = pd.concat(parts, ignore_index=True)
    merged = merged.drop_duplicates(subset=["station_id", "collected_at"], keep="last")
    return merged.sort_values(["collected_at", "station_id"]).reset_index(drop=True)


def compact_day(day: date, prefix: str = STATUS_PREFIX) -> str | None:
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi, hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError

    hub = hub_settings()
    if not hub.enabled:
        raise SystemExit("HF_TOKEN et HF_DATASET_REPO sont requis pour la compaction")
    api = HfApi(token=hub.token)
    folder = f"{prefix}/date={day:%Y-%m-%d}"

    try:
        files = [
            entry.path
            for entry in api.list_repo_tree(hub.repo_id, path_in_repo=folder, repo_type="dataset")
            if entry.path.endswith(".parquet")
        ]
    except EntryNotFoundError:
        log.warning("Aucune donnée pour %s", day)
        return None

    small_files = [f for f in files if not f.endswith(COMPACTED_NAME)]
    if not small_files:
        log.info("%s déjà compacté (%s fichier)", day, len(files))
        return None

    parts = [
        pd.read_parquet(hf_hub_download(hub.repo_id, f, repo_type="dataset", token=hub.token)) for f in files
    ]
    merged = merge_parts(parts)
    target = f"{folder}/{COMPACTED_NAME}"

    operations = [CommitOperationAdd(path_in_repo=target, path_or_fileobj=to_parquet_bytes(merged))]
    operations += [CommitOperationDelete(path_in_repo=f) for f in small_files]
    api.create_commit(
        hub.repo_id,
        operations=operations,
        commit_message=f"compaction {folder} ({len(small_files)} fichiers -> 1)",
        repo_type="dataset",
    )
    log.info("%s : %s fichiers -> %s (%s lignes)", day, len(files), target, len(merged))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date", type=date.fromisoformat, default=None, help="AAAA-MM-JJ (défaut : veille UTC)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    day = args.date or (pd.Timestamp.now(tz="UTC").date() - timedelta(days=1))
    compact_day(day)
    return 0


if __name__ == "__main__":
    sys.exit(main())