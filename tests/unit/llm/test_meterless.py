"""Meterless provider contract v4: URL normalisation, connect links, the honest probe, placeholder token."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from barthelona.llm import Catalog, Gateway, GatewayError, load_catalog
from barthelona.llm.meterless import (
    normalize_base_url,
    offer,
    parse_connect_link,
    probe,
    route_probe,
    usable_token,
)


@pytest.mark.parametrize(
    "raw",
    [
        "127.0.0.1:8088",
        "http://127.0.0.1:8088",
        "http://127.0.0.1:8088/v1",
        "http://127.0.0.1:8088/v1/",
        "http://127.0.0.1:8088/v1/chat/completions",
        "http://127.0.0.1:8088/v1/models",
        "http://127.0.0.1:8088/healthz",
    ],
)
def test_pasted_urls_normalise_to_host_v1_and_never_v1_v1(raw: str) -> None:
    assert normalize_base_url(raw) == "http://127.0.0.1:8088/v1"


def test_connect_link_fills_url_key_and_model() -> None:
    link = parse_connect_link("http://192.168.1.5:8088/connect#k=a%2Bb&m=meterless/code&n=demo")
    assert link is not None
    assert (link.base_url, link.api_key, link.model, link.app) == (
        "http://192.168.1.5:8088/v1",
        "a+b",
        "meterless/code",
        "demo",
    )


@pytest.mark.parametrize(
    "text",
    [
        "http://127.0.0.1:8088/v1",
        "http://h:1/connect",
        "http://h:1/other#k=x",
        "not a url",
        "ftp://h/connect#k=x",
    ],
)
def test_anything_that_is_not_a_connect_link_is_left_alone(text: str) -> None:
    assert parse_connect_link(text) is None


def test_trailing_slash_and_https_are_links() -> None:
    link = parse_connect_link("https://rt.example:9/connect/#k=x")
    assert link is not None
    assert link.base_url == "https://rt.example:9/v1"
    assert link.model == "meterless/auto"


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_401_is_unauthorized_not_offline() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    assert probe("127.0.0.1:8088", "wrong", _client(transport)).state == "unauthorized"


def test_200_with_meterless_ids_is_online_and_sends_the_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "meterless/auto"}, {"id": "other"}]})

    result = probe("http://127.0.0.1:8088/v1", "tok", _client(httpx.MockTransport(handle)))
    assert (result.state, result.models) == ("online", ("meterless/auto",))
    assert seen[0].headers["authorization"] == "Bearer tok"
    assert seen[0].headers["meterless-app"] == "barthelona"


def test_a_healthy_process_without_meterless_models_is_offline() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    assert probe("127.0.0.1:8088", "tok", _client(transport)).state == "offline"


def test_connection_failure_is_offline() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert probe("127.0.0.1:8088", "tok", _client(httpx.MockTransport(refuse))).state == "offline"


def test_placeholder_token_is_not_usable() -> None:
    assert not usable_token("rt-local")
    assert not usable_token("")
    assert usable_token("real")


async def test_gateway_skips_meterless_with_the_placeholder_token() -> None:
    catalog: Catalog = load_catalog(Path("config/models.yaml"), env={})
    gateway = Gateway(catalog, {}, profile="meterless", env={"METERLESS_RUNTIME_TOKEN": "rt-local"})
    with pytest.raises(GatewayError, match="placeholder"):
        from barthelona.llm import ChatMessage, CompletionRequest

        await gateway.complete("worker", CompletionRequest(messages=(ChatMessage(role="user", content="x"),)))


def test_probe_refuses_urls_that_are_not_http() -> None:
    assert probe("file:///etc/passwd", "tok").state == "offline"
    assert probe("ftp://host/v1", "tok").reason == "not an http(s) URL with a host"


_LISTING = {
    "data": [
        {
            "id": "meterless/deep",
            "owned_by": "meterless",
            "meterless": {"name": "Meterless Deep", "availability": "ready", "description": "Top."},
        },
        {
            "id": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "owned_by": "nvidia",
            "meterless": {
                "kind": "cloud",
                "tier": "A",
                "context": 262144,
                "price": {"input_per_m": 0, "output_per_m": 0},
            },
        },
    ]
}


def test_offer_separates_the_routing_modes_from_the_models_that_can_be_called() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_LISTING))
    listed = offer("127.0.0.1:8088", "tok", _client(transport))
    assert [(route.id, route.availability, route.name) for route in listed.routes] == [
        ("meterless/deep", "ready", "Meterless Deep")
    ]
    assert [(m.id, m.kind, m.tier, m.context, m.price_in) for m in listed.served] == [
        ("nvidia/nemotron-3.5-lightning-30b-a3b", "cloud", "A", 262144, 0.0)
    ]


def test_offer_says_why_it_found_nothing_instead_of_returning_half_a_list() -> None:
    wrong_token = httpx.MockTransport(lambda request: httpx.Response(401))
    assert offer("127.0.0.1:8088", "wrong", _client(wrong_token)).reason.startswith("unauthorized")
    empty = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    assert offer("127.0.0.1:8088", "tok", _client(empty)).reason == "the runtime listed no models"


def test_route_probe_reports_the_concrete_model_that_answered() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"model": "gpt-4o-mini", "choices": []})

    routed = route_probe("127.0.0.1:8088", "tok", "meterless/auto", _client(httpx.MockTransport(handle)))
    assert (routed.route, routed.model, routed.status) == ("meterless/auto", "gpt-4o-mini", 200)
    assert seen[0].headers["meterless-scope"] == "user"


def test_route_probe_reports_a_failure_instead_of_a_model() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(502, text="upstream said no"))
    routed = route_probe("127.0.0.1:8088", "tok", "meterless/deep", _client(transport))
    assert (routed.model, routed.status, routed.reason) == ("", 502, "upstream said no")
