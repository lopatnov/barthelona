"""Zetaris as a structured knowledge store next to Qdrant: read-only SQL over its REST API.

The contract is the Open Agent Hackathon participant guide (Data 1.9):
``POST <rest url>/sql-editor/sqls/run`` with ``Authorization: Bearer <API key>``, ``X-Org-ID`` and a fresh
``X-Request-ID``; the body carries ``queryId``, ``sql``, ``source`` and ``limit`` and the rows come back under
``data``. Rows are untrusted text (the guard wraps them) and the key comes only from the environment
(invariant 10). Only a single read-only statement is sent.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import httpx

from barthelona.llm.guard import inspect, wrap_untrusted

DEFAULT_REST_URL = "http://localhost:8888/api/v1.0"
DEFAULT_ORG_ID = "1"
TIMEOUT_S = 60.0
DEFAULT_LIMIT = 50
_MAX_FACT_CHARS = 4000
_READ_ONLY = re.compile(r"^\s*(select|show|describe|with)\b", re.IGNORECASE)

ZetarisState = Literal["online", "unauthorized", "offline", "unconfigured"]


class ZetarisError(RuntimeError):
    """A refused statement, an unreachable Zetaris or a reply that is not rows."""


@dataclass(frozen=True)
class ZetarisConfig:
    rest_url: str
    org_id: str
    api_key: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ZetarisConfig | None:
        """None when ZETARIS_API_KEY is not set: Zetaris is optional (invariant 11)."""
        key = env.get("ZETARIS_API_KEY", "").strip()
        if not key:
            return None
        return cls(
            env.get("ZETARIS_REST_URL", "").strip().rstrip("/") or DEFAULT_REST_URL,
            env.get("ZETARIS_ORG_ID", "").strip() or DEFAULT_ORG_ID,
            key,
        )


@dataclass(frozen=True)
class SqlResult:
    rows: tuple[tuple[str, ...], ...]

    def as_text(self) -> str:
        return "\n".join(" | ".join(row) for row in self.rows)


def check_read_only(sql: str) -> str:
    """The statement without its semicolon; ZetarisError unless one SELECT, SHOW, DESCRIBE or WITH."""
    statement = sql.strip().rstrip(";").strip()
    if not statement or ";" in statement:
        raise ZetarisError("send exactly one statement")
    if not _READ_ONLY.match(statement):
        raise ZetarisError("only SELECT, SHOW, DESCRIBE and WITH statements are sent")
    return statement


def run_sql(
    config: ZetarisConfig, sql: str, limit: int = DEFAULT_LIMIT, client: httpx.Client | None = None
) -> SqlResult:
    """Run one read-only statement and return its rows as text cells."""
    statement = check_read_only(sql)
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "X-Org-ID": config.org_id,
        "X-Request-ID": str(uuid.uuid4()),
    }
    body = {"queryId": str(uuid.uuid4()), "sql": statement, "source": "SqlEditor", "limit": limit}
    try:
        with client or httpx.Client(timeout=TIMEOUT_S) as http:
            response = http.post(f"{config.rest_url}/sql-editor/sqls/run", headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ZetarisError(f"Zetaris is not reachable: {type(exc).__name__}") from exc
    if response.status_code in (401, 403):
        raise ZetarisError("Zetaris refused the API key (ZETARIS_API_KEY)")
    if response.status_code != 200:
        raise ZetarisError(f"Zetaris answered HTTP {response.status_code}: {response.text[:200]}")
    try:
        data = response.json().get("data")
    except ValueError as exc:
        raise ZetarisError("Zetaris did not answer with JSON") from exc
    if not isinstance(data, list):
        raise ZetarisError(f"no rows in the reply: {response.text[:200]}")
    return SqlResult(tuple(tuple(str(cell) for cell in row) for row in data if isinstance(row, list)))


def probe(config: ZetarisConfig | None, client: httpx.Client | None = None) -> tuple[ZetarisState, str]:
    """The honest state: ``SELECT 1`` must come back as one row containing 1."""
    if config is None:
        return (
            "unconfigured",
            "set ZETARIS_API_KEY (and ZETARIS_REST_URL, ZETARIS_ORG_ID if not the defaults)",
        )
    try:
        result = run_sql(config, "SELECT 1", 1, client)
    except ZetarisError as exc:
        state: ZetarisState = "unauthorized" if "refused" in str(exc) else "offline"
        return state, str(exc)
    return ("online", config.rest_url) if result.rows[:1] == (("1",),) else ("offline", "SELECT 1 gave no 1")


def facts_block(result: SqlResult, sql: str) -> str:
    """Rows as a delimited untrusted block for the first chunk; text the guard blocks is refused."""
    text = result.as_text()[:_MAX_FACT_CHARS]
    if not text:
        raise ZetarisError("the query returned no rows")
    if inspect(text).blocked:
        raise ZetarisError("the rows were blocked by the injection guard")
    return f"[ZETARIS FACTS] rows of: {sql.strip()}\n{wrap_untrusted(text, 'zetaris')}"
