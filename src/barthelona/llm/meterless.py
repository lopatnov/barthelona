r"""Meterless Runtime provider helpers (provider contract v4, Runtime 1.4).

Pure URL and key handling plus one honest probe. ``GET /healthz`` only proves the process is up, so the
state comes from ``GET /v1/models``: 401/403 is unauthorized, 200 with ``meterless/*`` ids is online and
anything else is offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote, urlsplit

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
PLACEHOLDER_TOKEN = "rt-local"  # noqa: S105 - not a secret: the placeholder the runtime rejects
APP_ID = "barthelona"
PROBE_TIMEOUT_S = 10.0
_SUFFIX = re.compile(r"/(v1(/(chat/completions|models))?|healthz)/?$")

State = Literal["online", "unauthorized", "offline"]


@dataclass(frozen=True)
class ConnectLink:
    base_url: str
    api_key: str
    model: str
    app: str


@dataclass(frozen=True)
class Probe:
    state: State
    base_url: str
    models: tuple[str, ...] = ()
    reason: str = ""


def normalize_base_url(raw: str) -> str:
    """``<host>/v1`` from a pasted URL (any scheme, /v1, /v1/chat/completions, /v1/models or /healthz)."""
    text = raw.strip()
    if not text:
        return DEFAULT_BASE_URL
    if "://" not in text:
        text = f"http://{text}"
    text = _SUFFIX.sub("", text.rstrip("/"))
    return f"{text.rstrip('/')}/v1"


def parse_connect_link(text: str) -> ConnectLink | None:
    """A connect link ``http(s)://<host>:<port>/connect#k=<key>[&m=<model>][&n=<app>]``, else None."""
    parts = urlsplit(text.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path.rstrip("/") != "/connect":
        return None
    fields = dict(pair.split("=", 1) for pair in parts.fragment.split("&") if "=" in pair)
    if not fields.get("k"):
        return None
    return ConnectLink(
        base_url=f"{parts.scheme}://{parts.netloc}/v1",
        api_key=unquote(fields["k"]),
        model=unquote(fields.get("m", "")) or "meterless/auto",
        app=unquote(fields.get("n", "")) or APP_ID,
    )


def usable_token(token: str | None) -> bool:
    return bool(token) and token != PLACEHOLDER_TOKEN


def probe(base_url: str, token: str | None, client: httpx.Client | None = None) -> Probe:
    """The runtime's honest state: asks ``/v1/models`` with the real token."""
    url = normalize_base_url(base_url)
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        return Probe("offline", url, reason="not an http(s) URL with a host")
    headers = {"meterless-app": APP_ID}
    if usable_token(token):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with client or httpx.Client(timeout=PROBE_TIMEOUT_S) as http:
            response = http.get(f"{url}/models", headers=headers)
    except httpx.HTTPError as exc:
        return Probe("offline", url, reason=f"{type(exc).__name__}: {exc}")
    if response.status_code in (401, 403):
        return Probe("unauthorized", url, reason="Paste the runtime's access token (Nightshift Console).")
    if response.status_code != 200:
        return Probe("offline", url, reason=f"HTTP {response.status_code}")
    rows = (
        response.json().get("data", [])
        if response.headers.get("content-type", "").startswith("application/json")
        else []
    )
    models = tuple(str(row.get("id")) for row in rows if str(row.get("id", "")).startswith("meterless/"))
    return Probe(
        "online" if models else "offline", url, models, "" if models else "no meterless/* models listed"
    )
