# D-012: Own thin ModelGateway over the official openai 3.x and anthropic 1.x SDKs; no LiteLLM

- Status: Proposed
- Date: 2026-10-13
- Amended by: D-029

## Decision

The gateway is a protocol with these backends:
- OpenAICompatBackend (LM Studio/Ollama/llama.cpp via base_url)
- AnthropicBackend
- FakeGateway
- a cassette backend for replay

Model capabilities come from models.yaml. The gateway provides:
- a semaphore per endpoint;
- a model-affinity scheduler;
- cost caps;
- an LLMCallRecord for every call.

## Rationale

With only 2–3 providers, a 40-line repair loop is simpler than a framework.

LiteLLM's PyPI releases 1.82.7 and 1.82.8 were malicious (March 2026).

The gateway lets us strip sampling parameters on Opus 5.5 and handle refusals in one place.

## Alternatives considered

- LiteLLM: supply-chain risk.
- langchain-openai/anthropic: workable, but an extra abstraction layer.
- Pydantic AI models: a second framework.
- instructor: optional; not needed.
