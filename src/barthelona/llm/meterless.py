r"""Meterless Runtime provider helpers (provider contract v4, Runtime 1.4).

Pure URL and key handling plus one honest probe. ``GET /healthz`` only proves the process is up, so the
state comes from ``GET /v1/models``: 401/403 is unauthorized, 200 with ``meterless/*`` ids is online and
anything else is offline.

``GET /v1/models`` also lists the *concrete* models the runtime can serve, with their kind, tier, context and
price, and those ids are callable directly (a request naming one bypasses the router). What a routing mode
resolves to is published nowhere: no endpoint lists a lane's members, so ``route_probe`` asks the mode and
reads the ``model`` field of the answer, which is the one honest source (§16.2).
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
# A routing mode may load a model before it answers (the provider contract allows 180 s for chat), so the
# lane probe waits like any other chat call instead of reading a cold lane as a refusal.
ROUTE_TIMEOUT_S = 180.0
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


@dataclass(frozen=True)
class Route:
    """One ``meterless/*`` routing mode: a disposition or a class, not a model file."""

    id: str
    name: str = ""
    availability: str = ""  # what the runtime says now, e.g. "ready"
    description: str = ""


@dataclass(frozen=True)
class Served:
    """A concrete model id the runtime will serve, with what its catalog entry claims about it."""

    id: str
    owner: str = ""
    kind: str = ""  # cloud | local
    tier: str = ""
    context: int | None = None
    price_in: float | None = None  # USD per 1M input tokens, when the runtime states a price
    price_out: float | None = None


@dataclass(frozen=True)
class Offer:
    """What the runtime advertises: its routing modes and the models behind them."""

    routes: tuple[Route, ...] = ()
    served: tuple[Served, ...] = ()
    reason: str = ""  # why the lists are empty, when they are


@dataclass(frozen=True)
class Routed:
    """What one routing mode answered with: the concrete model id, or the failure."""

    route: str
    model: str = ""
    status: int = 0
    reason: str = ""


def _rows(response: httpx.Response) -> list[dict[str, object]]:
    """The ``data`` array of a listing reply, or nothing when the reply is not a JSON listing."""
    if not response.headers.get("content-type", "").startswith("application/json"):
        return []
    rows = response.json().get("data", [])
    return [row for row in rows if isinstance(row, dict)]


def _meta(row: dict[str, object]) -> dict[str, object]:
    meta = row.get("meterless")
    return meta if isinstance(meta, dict) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def offer(base_url: str, token: str | None, client: httpx.Client | None = None) -> Offer:
    """``GET /v1/models`` as two lists: the routing modes and the concrete models that can be called."""
    url = normalize_base_url(base_url)
    headers = {"meterless-app": APP_ID}
    if usable_token(token):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with client or httpx.Client(timeout=PROBE_TIMEOUT_S) as http:
            response = http.get(f"{url}/models", headers=headers)
    except httpx.HTTPError as exc:
        return Offer(reason=f"{type(exc).__name__}: {exc}")
    if response.status_code in (401, 403):
        return Offer(reason="unauthorized: paste the runtime's access token (Nightshift Console)")
    if response.status_code != 200:
        return Offer(reason=f"HTTP {response.status_code}")
    routes: list[Route] = []
    served: list[Served] = []
    for row in _rows(response):
        model_id = _text(row.get("id"))
        meta = _meta(row)
        if model_id.startswith("meterless/"):
            routes.append(
                Route(
                    model_id,
                    _text(meta.get("name")),
                    _text(meta.get("availability")),
                    _text(meta.get("description")),
                )
            )
            continue
        price = meta.get("price")
        priced = price if isinstance(price, dict) else {}
        context = meta.get("context")
        served.append(
            Served(
                model_id,
                _text(row.get("owned_by")),
                _text(meta.get("kind")),
                _text(meta.get("tier")),
                context if isinstance(context, int) else None,
                _number(priced.get("input_per_m")),
                _number(priced.get("output_per_m")),
            )
        )
    if not routes and not served:
        return Offer(reason="the runtime listed no models")
    return Offer(tuple(routes), tuple(served))


def route_probe(base_url: str, token: str | None, route: str, client: httpx.Client | None = None) -> Routed:
    """Ask *route* one token and report the concrete model that answered.

    This is the only way to learn what a routing mode resolves to: the runtime publishes no lane
    membership, and the same mode may answer from a different model on the next call (it prefers what is
    already loaded). One call costs a handful of tokens; a paid route makes it a paid call.
    """
    url = normalize_base_url(base_url)
    headers = {"meterless-app": APP_ID, "meterless-scope": "user"}
    if usable_token(token):
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "model": route,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "max_tokens": 4,
        "temperature": 0,
    }
    try:
        with client or httpx.Client(timeout=ROUTE_TIMEOUT_S) as http:
            response = http.post(f"{url}/chat/completions", headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return Routed(route, status=0, reason=f"{type(exc).__name__}: {exc}")
    if response.status_code != 200:
        return Routed(route, status=response.status_code, reason=response.text[:200])
    body = response.json()
    return Routed(route, _text(body.get("model")), response.status_code)
