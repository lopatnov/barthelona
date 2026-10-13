# D-025: Dropped or deferred patterns from the Gemini draft

- Status: Proposed
- Date: 2026-10-13

## Decision

Dropped:
- multi-agent debate
- Tree-of-Thought scored on LLM-guessed cycle counts
- LLM dry-run review as a gate
- GPUtil hardware profiles
- rolling chat summaries
- YaRN context stretching
- two large models resident at once
- LLM-written Makefiles
- code RAG

Deferred, and gated by approval and the benchmark:
- web search agent (P5, results stored as low-trust candidates)
- optional cross-model critic (as an advisory llm_review slot)
- KolibriOS
- OpenVINO trial
- fine-tuning

## Rationale

Evidence:
- Debate doesn't beat sampling plus voting, at 3× or more tokens.
- Self-correction without external feedback fails.
- GPUtil is NVIDIA-only.

The oracle-ranked candidates template replaces Tree-of-Thought, and the repo map replaces code RAG.

## Alternatives considered

Keep them all, as in the draft: high cost on a slow machine with no evidence of benefit.
