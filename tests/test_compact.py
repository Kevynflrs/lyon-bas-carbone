"""Compaction testée avec un faux Hugging Face (aucun appel réseau)."""

import io
from datetime import date
from types import SimpleNamespace

import huggingface_hub
import pandas as pd
from conftest import STATUS_V2

from pipeline.config import HubSettings
from pipeline.ingest import compact
from pipeline.ingest.gbfs import parse_station_status

FOLDER = "raw/velov/station_status/date=2026-10-28"


class FakeApi:
    def __init__(self, files):
        self.files = files
        self.commits = []

    def list_repo_tree(self, repo_id, path_in_repo, repo_type):
        return [SimpleNamespace(path=p) for p in self.files if p.startswith(path_in_repo)]

    def create_commit(self, repo_id, operations, commit_message, repo_type):
        self.commits.append(operations)


def fake_hub(monkeypatch, api, local_files=None):
    monkeypatch.setattr(compact, "hub_settings", lambda: HubSettings("token", "user/dataset"))
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda token: api)
    if local_files is not None:
        monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda repo, f, **kw: local_files[f])


def test_compact_day_merges_and_deletes_small_files(tmp_path, monkeypatch):
    local_files = {}
    for i in range(3):
        ts = pd.Timestamp("2026-10-28T10:00:00Z") + pd.Timedelta(minutes=15 * i)
        path = tmp_path / f"{i}.parquet"
        parse_station_status(STATUS_V2, ts).to_parquet(path)
        local_files[f"{FOLDER}/status_{ts:%Y%m%dT%H%M%SZ}.parquet"] = path

    api = FakeApi(list(local_files))
    fake_hub(monkeypatch, api, local_files)

    target = compact.compact_day(date(2026, 10, 28))

    assert target == f"{FOLDER}/compacted.parquet"
    (operations,) = api.commits
    added = [op for op in operations if isinstance(op, huggingface_hub.CommitOperationAdd)]
    deleted = {op.path_in_repo for op in operations if isinstance(op, huggingface_hub.CommitOperationDelete)}
    assert deleted == set(local_files)
    merged = pd.read_parquet(io.BytesIO(added[0].path_or_fileobj))
    assert len(merged) == 9  # 3 stations x 3 collectes


def test_compact_day_skips_already_compacted(monkeypatch):
    api = FakeApi([f"{FOLDER}/compacted.parquet"])
    fake_hub(monkeypatch, api)
    assert compact.compact_day(date(2026, 10, 28)) is None
    assert api.commits == []


def test_compact_day_without_data_does_not_crash(monkeypatch):
    """Un jour sans données (dossier absent sur le Hub) ne doit pas faire planter la compaction."""
    from huggingface_hub.errors import RemoteEntryNotFoundError

    class EmptyApi(FakeApi):
        def list_repo_tree(self, repo_id, path_in_repo, repo_type):
            # Instance créée sans __init__ : le constructeur exige une vraie réponse HTTP.
            raise RemoteEntryNotFoundError.__new__(RemoteEntryNotFoundError)

    api = EmptyApi([])
    fake_hub(monkeypatch, api)
    assert compact.compact_day(date(2026, 10, 28)) is None
    assert api.commits == []
