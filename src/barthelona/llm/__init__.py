"""Model gateway: catalog, role router, backends (docs/architecture.md §16)."""

from barthelona.llm.backend import Backend, RawReply
from barthelona.llm.catalog import Catalog, CatalogError, ModelTarget, load_catalog
from barthelona.llm.fake import FakeGateway
from barthelona.llm.gateway import Gateway, ModelGateway
from barthelona.llm.markovian import ChunkStat, MarkovianConfig, MarkovianResult, extract_code, run_markovian
from barthelona.llm.openai_chat import OpenAIChatBackend
from barthelona.llm.thinking import strip_think
from barthelona.llm.types import (
    ChatMessage,
    Completion,
    CompletionRequest,
    FailureKind,
    GatewayError,
    ModelCallError,
)

__all__ = [
    "Backend",
    "Catalog",
    "CatalogError",
    "ChatMessage",
    "ChunkStat",
    "Completion",
    "CompletionRequest",
    "FailureKind",
    "FakeGateway",
    "Gateway",
    "GatewayError",
    "MarkovianConfig",
    "MarkovianResult",
    "ModelCallError",
    "ModelGateway",
    "ModelTarget",
    "OpenAIChatBackend",
    "RawReply",
    "extract_code",
    "load_catalog",
    "run_markovian",
    "strip_think",
]
