"""Client HTTP avec retries : les flux open data tombent parfois quelques minutes."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pipeline.config import HTTP_TIMEOUT_S, USER_AGENT


def build_session() -> requests.Session:
    retry = Retry(
        total=4,
        backoff_factor=2,  # 0 s, 2 s, 4 s, 8 s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def fetch_json(url: str, session: requests.Session | None = None) -> Any:
    session = session or build_session()
    response = session.get(url, timeout=HTTP_TIMEOUT_S)
    response.raise_for_status()
    return response.json()
