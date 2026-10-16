# D-038: Caching strategy: provider prefix caching over semantic response caching

- Status: Proposed
- Date: 2026-10-16
- Amends: D-016

## Context

Aleksandr raised three related ideas (2026-10-14):

1. **CAG / Cache-Augmented Generation** – preload a static knowledge corpus into every prompt so the
   LLM provider can reuse the KV-cache across calls (Chan et al., arXiv 2412.15605, "Don't Do RAG").
2. **Semantic response caching** – cache the *answer* to a query in a vector store (e.g. Qdrant),
   and return the cached answer when a sufficiently similar query arrives instead of calling the LLM.
3. **KAG (Knowledge-Augmented Generation)** – augment prompts with a structured knowledge graph over
   the domain, rather than flat document chunks.

Aleksandr's hypothesis: CAG + RAG is a good fit for an assembler expert or architecture expert,
because that knowledge rarely changes.

Barthelona's architecture already states (§2 principle 5): "Fresh, budgeted context. No chat
histories. Every LLM call is assembled from the registry, files and facts, **with stable blocks
first**." That "stable blocks first" ordering is the prerequisite for provider prefix caching.

Concern raised: a Medium article notes that prefix caching in multi-agent systems is difficult when
each agent's prompt prefix diverges early. Barthelona's design already avoids this by separating the
stable knowledge prefix (system prompt, rule cards, asm facts) from the dynamic suffix (code state,
errors, task context).

MAG (Memory-Augmented Generation) is already covered by the Lessons system (D-017).

## Decision

### 1. Provider-side prefix / prompt caching — **Adopt in Phase 1**

The context assembler (Phase 1 deliverable) MUST order blocks as:
```
[system prompt]  [rule cards]  [asm facts / doc chunks]  [dynamic context]
```
The stable prefix (system prompt + rule cards + asm facts) must be byte-for-byte identical across
all calls within a sprint run that share the same dialect, arch and policy version. This makes
provider-side caching effective.

Provider integration:
- **Anthropic**: add `cache_control: {"type": "ephemeral"}` to the last content block of the stable
  prefix. Cached tokens cost ~10% of normal input token price after the first call.
  (https://platform.claude.com/docs/en/home, checked 2026-10-13)
- **LM Studio / vLLM**: no SDK change needed; automatic prefix caching reuses the KV cache when
  the prompt prefix matches. Effective only when the model stays loaded and the prefix is identical.
- **OpenAI, Gemini, DeepSeek**: caching support varies by tier and model; the gateway should
  populate provider-specific headers / params when configured in `config/models.yaml`.

The gateway records a `cache_hit` boolean per call in the `llm_calls` persistence table (§24)
and the observability event log.

### 2. Semantic response caching — **Rejected for coding generation tasks**

Semantic response caching stores the LLM's *answer* in a vector store keyed by query embedding,
returning a cached answer when the incoming query is similar enough.

This does not fit Barthelona's use case:
- Every coding call is context-specific: the same user goal with different code state, different
  errors or a different module yields a different correct answer. Hit rate would be near zero.
- Staleness is immediate: any code change or error change invalidates the cached answer.
- The multi-agent problem is acute: ten parallel sprint tasks with different prompts produce no
  reusable cache entries.
- Risk: a false cache hit (wrong code returned) could corrupt a workspace silently, violating
  the oracle-decides invariant (§2 principle 1).

For knowledge lookups that *could* benefit (e.g. "what does NASM `extern` mean?"), the stable-prefix
approach already covers this more safely: the answer is in the prefix that is cached at the provider.

### 3. CAG for static assembler knowledge — **Adopted as the stable-prefix pattern**

The CAG insight — preload a small, stable corpus rather than retrieve at query time — is correct
for the assembler expert context. Barthelona adopts this not as a separate caching layer but as the
stable-prefix pattern above:

- Rule cards (NASM, GAS-Intel, GAS-AT&T on linux-x64) are always injected (D-016, unchanged).
- ABI fact rows and key instruction references are placed in the stable prefix, not retrieved
  per call.
- Token budget for the stable prefix: at most 25% of the context window (the context assembler
  enforces this, with a hard error rather than silently truncating).
- When asm_doc/ chunks are needed (Phase 3 RAG), dense doc chunks also enter via a small stable
  block placed before the dynamic suffix.

Full CAG (the whole corpus in every call) is deferred to after Phase 3's retrieval eval: it is
viable only if the stable prefix fits within the chosen local model's context window (16K default)
and the provider's cache TTL covers a typical sprint run.

### 4. KAG (Knowledge-Augmented Generation) — **Deferred to Phase 3+**

KAG augments retrieval with a structured knowledge graph (entities + relations). For assembler
instructions and ABI rules, the existing `facts.sqlite` (exact lookup) + FTS5 + rule cards already
provides structured, precise knowledge without graph infrastructure. KAG adds real value only when:
- relationships between entities are queried (e.g. "which instructions clobber CF?"),
- and FTS5 recall is insufficient.

This is a Phase 3+ research item; `facts.sqlite` may be evolved into a lightweight knowledge graph
at that point if the retrieval eval shows a benefit.

### 5. MAG — Already covered

Memory-Augmented Generation = the Lessons system (D-017). Lessons are evidence-gated, scoped,
and injected into the dynamic part of the prompt per call. No change.

## Rationale

- **Prefix caching is free to adopt** given the "stable blocks first" design already planned.
  The only cost is making the stable-prefix bytes deterministic, which is also required for
  reproducibility (§2 principle 9).
- **Semantic response caching is harmful** for a code-generation agentic loop: it trades a small
  latency saving for correctness risk and architecture complexity.
- **The multi-agent prefix problem** from the Medium article is not a problem here because
  the Barthelona context assembler already puts all shared stable content before task-specific
  context. The dynamic suffix diverges per task, but the prefix is shared and cacheable.

## Alternatives considered

- **Semantic cache for all calls including coding** – rejected, correctness risk outweighs savings.
- **KAG from Phase 1** – rejected, heavy infrastructure with no measured benefit over facts.sqlite.
- **RAG-only (D-016 as-is)** – accepted for Phase 1/2; stable-prefix prefix caching extends it.
- **Redis semantic cache (as described in user's post)** – not adopting Redis; Qdrant is already
  the vector store, but it won't be used for response caching (semantic cache) for reasons above.

## Consequences

- Context assembler (Phase 1) must enforce stable-prefix block ordering and compute a stable prefix
  hash to detect accidental divergence.
- `config/models.yaml` gains a `prefix_cache` key per provider backend (on/off + cache_control
  type for Anthropic).
- `llm_calls` table gains `cache_hit bool` and `cache_tokens_saved int` columns.
- Observability: token savings from prefix caching are logged and shown in the Toolchains & models
  UI panel.
- No new runtime dependencies.
