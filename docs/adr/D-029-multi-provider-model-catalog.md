# D-029: Multi-provider model catalog (Anthropic, OpenAI, Google Gemini, DeepSeek) in config/models.yaml

- Status: Proposed
- Date: 2026-10-13
- Amends: D-011, D-012, D-014

## Context

D-012 and D-014 assumed a single cloud provider, Anthropic. The owner holds API keys for Anthropic, OpenAI, Google Gemini and DeepSeek. The owner wants a configuration file that states which cloud models may be used, so they can be built into the system's capabilities, plus a UI where a budget can be entered.

## Decision

1. **`config/models.yaml`** is the single catalog. It is committed and contains no secrets. Its sections:
   - `providers`: kind, base URL, `api_key_env`, concurrency, structured-output mode;
   - `models`: id, price class (`price_class`), context, max output, reasoning controls, `price` per 1M tokens (input, cached input, output) and `pricing_checked`;
   - `profiles`: ordered role → model chains for `local-only`, `hybrid` and `cloud`;
   - `budget` and `resilience`.
2. **Backends**, each using the provider's official SDK:
   - OpenAI-compatible Chat Completions (`openai` 3.x): LM Studio, Ollama, DeepSeek;
   - OpenAI Responses API (`openai` 3.x): OpenAI GPT-6 models, which need it for tool calls with reasoning;
   - Anthropic (`anthropic` 1.x);
   - Gemini (`google-genai` 2.x; the OpenAI-compatible endpoint's schema enforcement is unverified).
3. **Initial catalog** (verified 2026-10-13):
   - Anthropic: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`; `claude-fable-5-1` is disabled.
   - OpenAI: `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`.
   - Google: `gemini-3.1-pro-preview`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`.
   - DeepSeek: `deepseek-v4-pro`, `deepseek-flash`.
   - Excluded: retiring or legacy models (`o3-pro` retires 2026-12-11; o-series; gpt-4.x; Gemini 2.5, restricted to previous users; DeepSeek legacy aliases).
4. **Role chains** interleave providers, so one provider's outage or empty balance moves the work to another. Every chain ends in the local model. The order is the owner's preference and can be edited freely.
5. **Provider differences are normalized in the gateway**, not in prompts:
   - reasoning controls: `output_config.effort`, `reasoning.effort`, `thinking_level`, DeepSeek `thinking` + `reasoning_effort`;
   - structured output: DeepSeek supports only `json_object`, so its output is validated with Pydantic and repaired;
   - refusals;
   - echoing reasoning items / `reasoning_content` in tool loops.
6. **The UI** shows:
   - the catalog with prices and `pricing_checked` dates;
   - provider health (key present, circuit state);
   - per-run choices: profile, allowed providers, optional dollar budget.

## Rationale

- Four providers give redundancy against outages and empty balances, and let the bench compare quality per dollar.
- Prices are not exposed by provider APIs, so the catalog stores them, with a check date, to compute cost from the reported usage.
- Official SDKs avoid the LiteLLM supply-chain risk (D-012) and expose provider-specific features: Anthropic server-side refusal fallbacks, OpenAI reasoning items, Gemini thinking levels, DeepSeek off-peak pricing.

## Alternatives considered

- **A single OpenAI-compatible adapter for every provider:** loses OpenAI tool calling with reasoning on GPT-6, Anthropic structured outputs and caching, and verified Gemini schema enforcement.
- **LiteLLM:** rejected (D-012).
- **Hard-coding models in code:** model ids and prices change monthly; config keeps them editable.

## Consequences

- `pricing_checked` must be refreshed when providers change prices. Known upcoming changes: Gemini 3.6/3.8 Flash prices double on 2027-01-01; `gemini-3.1-pro-preview` is a preview and may be deprecated at short notice; DeepSeek has announced V4.1-Pro, and its docs conflict on whether `deepseek-v4-pro` is currently routed to V4.1-Flash, so check `GET /models` at startup.
- Each backend needs a cassette-based contract test, plus error-mapping tests built from captured error bodies.
- The bench reports quality, cost and latency per provider and model.
