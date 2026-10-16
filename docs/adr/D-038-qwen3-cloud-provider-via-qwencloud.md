# D-038 Add Qwen3 as a cloud provider via Alibaba QwenCloud

## Context

`config/models.yaml` currently lists four cloud providers: Anthropic, OpenAI, Google Gemini, and
DeepSeek (D-029). All four use tokenizers optimised for Latin scripts. Barthelona accepts
user descriptions in English, Russian, and Ukrainian (§1, D-022), and the local-model bake-off
already lists Qwen3 MoE models as candidates (D-013). Alibaba's Qwen3 family uses a CJK- and
Slavic-optimised tokenizer that produces 40–65 % fewer tokens than the Claude/GPT tokenizer for
Cyrillic text, which lowers cost proportionally for the parts of a run that process Russian or
Ukrainian input.

Note: Barthelona's own prompts (rule cards, contracts, code, envelopes) are English, so the
tokenizer advantage is largest for user-supplied text in the `main` (intake/localizer) and
`cheap` (classification) roles, and smallest for the `worker` role that generates assembly code.

## Decision

Add `dashscope` as a fifth cloud provider in `config/models.yaml`, using the Alibaba QwenCloud
OpenAI-compatible endpoint (`maas.qwencloudapi.com`). Keys are created at
`home.qwencloud.com/api-keys` and set in `DASHSCOPE_API_KEY`. Register three Qwen3 models:

| Catalog key | API model id | Price class | Thinking |
| --- | --- | --- | --- |
| `qwen3-235b-a22b` | `qwen3-235b-a22b` | flagship | on by default |
| `qwen3-30b-a3b` | `qwen3-30b-a3b` | mid (MoE) | on by default |
| `qwen-turbo` | `qwen-turbo-latest` | cheap | none (disabled) |

Insert `qwen3-235b-a22b` as the second entry in the `planner` and `escalation` chains for the
`hybrid` and `cloud` profiles (after the Anthropic option). Insert `qwen3-30b-a3b` with thinking
disabled as the second entry in the `main` and `worker` chains of the `cloud` profile.
`qwen-turbo` is registered but set `enabled: false` until output quality is verified.

`DASHSCOPE_BASE_URL` can be overridden in `.env` to point to OpenRouter
(`https://openrouter.ai/api/v1`) as an alternative if the QwenCloud endpoint is unreachable.

## Rationale

- **Tokenizer economy.** The Qwen3 tokenizer encodes Cyrillic at roughly 1.2–1.5 tok/char
  versus 3–4 tok/char for the Claude/GPT BPE tokenizer. A 1 000-character Russian description
  costs ~1 500 Qwen3 input tokens vs ~4 000 Claude tokens — roughly 60 % cheaper for the
  non-English portion.
- **Open weights, non-politicised.** The Qwen3 weights are Apache-2.0-licensed. Unlike Anthropic
  and OpenAI, Alibaba has not publicly restricted use of its models based on geopolitical origin.
- **MoE cost.** Qwen3-30B-A3B activates only ~3B parameters, giving mid-tier quality at near-
  cheap pricing — a good fit for the `worker` role.
- **Architecture fit.** QwenCloud's OpenAI-compatible endpoint means the existing
  `OpenAIChatBackend` handles it with no new SDK or backend code. The provider normalizes to the
  same `json_object` path as DeepSeek (Pydantic validation + repair).

## Alternatives considered

- **OpenRouter only** — simpler key management, but a 5–10 % markup over QwenCloud direct.
  Kept as an opt-in via `DASHSCOPE_BASE_URL` override.
- **Self-hosted Qwen3 on `cloud_gpu`** — already in the catalog as `cloud_gpu`; the comment
  there already names Qwen3-Coder-30B-A3B as the example model. Not a substitute for API
  access when the rented GPU is idle.
- **Replace Anthropic with Qwen3 as primary planner** — not done yet: Opus 5.5 remains better
  benchmarked for complex multi-step reasoning; Qwen3-235B is placed second to try it as a
  fallback and gather empirical data.
- **DashScope International (dashscope-intl.aliyuncs.com)** — this is a different Alibaba cloud
  portal than QwenCloud. Keys from home.qwencloud.com are bound to maas.qwencloudapi.com and
  are not interchangeable with DashScope International keys.

## Consequences

- A new env var `DASHSCOPE_API_KEY` (set from `home.qwencloud.com/api-keys`) is required to
  enable this provider. Missing key = provider disabled, same as the existing providers.
- Pricing figures in `config/models.yaml` are approximate (source: third-party aggregator
  anotherwrapper.com; verify against the QwenCloud console). See issue #24 "Verify Qwen3 pricing
  on QwenCloud" to track the authoritative numbers before setting a dollar budget.
- The gateway must normalize `enable_thinking → extra_body.enable_thinking` for Qwen3 calls
  and must strip `<think>…</think>` from Qwen3 cloud responses (same strip_think logic as local
  models). This is a Phase 1 gateway implementation item.
- The gateway config loader must expand `${VAR:-default}` patterns in `base_url` values so the
  QwenCloud override works (and `LAN_LMSTUDIO_BASE_URL`, `OLLAMA_BASE_URL`, `CLOUD_GPU_BASE_URL`
  can use the same pattern). See issue #25.
- `reasoning_content` echoing in multi-turn tool loops applies to Qwen3 exactly as for
  DeepSeek.

## Status

Proposed

## Date

2026-10-14

## Amends

D-029 (adds a fifth provider to the multi-provider catalog)
