# D-013: One resident local MoE model chosen by a Phase 0 bake-off; explicit profiles

- Status: Proposed
- Date: 2026-10-13

## Decision

One local model (about 3B active parameters) serves every local role:
- default context 16K, maximum 32K;
- q8_0 KV cache.

Bake-off candidates:
- Qwen3-Coder-30B-A3B
- Qwen3.6-35B-A3B (thinking off for coding)
- gpt-oss-20b
- installed: lfm2-24b-a2b, ministral-3-14b-reasoning

Measured on: tok/s, JSON validity and pass@1 on 10 tasks, against a single-prompt baseline.

Profiles: local-only, hybrid and cloud, set in models.yaml and selectable in the UI. psutil is used only to read RAM. No GPUtil.

## Rationale

32 GB RAM is shared with the iGPU and WSL. Model swaps cost seconds to minutes and wipe the prefix cache.

No published NASM/FASM benchmark exists for these models, so we must measure ourselves.

GPUtil is NVIDIA-only and was last released in 2018.

## Alternatives considered

- A tiered set of local models (draft LOW/MEDIUM/HIGH, scrum-faithful T1+T2): does not fit in RAM at the same time.
- Qwen3-Coder-Next: needs about 48–52 GB.
