"""Ask a model endpoint what it serves, so a bake-off fails fast and says why when the server is down."""

from __future__ import annotations

import openai
from openai import AsyncOpenAI

from barthelona.llm.catalog import ModelTarget

_NO_KEY = "not-needed"  # LM Studio and Ollama ignore the key but the SDK insists on one
_TIMEOUT_S = 10.0


class EndpointError(RuntimeError):
    """The endpoint of a model target did not answer the model listing."""


async def served_models(target: ModelTarget) -> list[str]:
    """Model ids the target's endpoint lists; `EndpointError` names the URL when it cannot be reached."""
    url = target.provider.base_url
    client = AsyncOpenAI(base_url=url, api_key=_NO_KEY, max_retries=0, timeout=_TIMEOUT_S)
    try:
        listing = await client.models.list()
    except openai.OpenAIError as exc:
        raise EndpointError(
            f"{target.provider_id} at {url} did not list its models ({type(exc).__name__}); "
            "is the server running and a model loaded?"
        ) from exc
    finally:
        await client.close()
    return sorted(model.id for model in listing.data)
