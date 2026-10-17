"""Model gateway: catalog, role router, backends (docs/architecture.md §16)."""

from barthelona.llm.backend import Backend, RawReply
from barthelona.llm.catalog import Catalog, CatalogError, ModelTarget, load_catalog
from barthelona.llm.fake import FakeGateway
from barthelona.llm.gateway import Gateway, ModelGateway
from barthelona.llm.openai_chat import OpenAIChatBackend
from barthelona.llm.thinking import strip_think
from barthelona.llm.types import ChatMessage, Completion, CompletionRequest, GatewayError, ModelCallError

__all__ = [
    "Backend",
    "Catalog",
    "CatalogError",
    "ChatMessage",
    "Completion",
    "CompletionRequest",
    "FakeGateway",
    "Gateway",
    "GatewayError",
    "ModelCallError",
    "ModelGateway",
    "ModelTarget",
    "OpenAIChatBackend",
    "RawReply",
    "load_catalog",
    "strip_think",
]
