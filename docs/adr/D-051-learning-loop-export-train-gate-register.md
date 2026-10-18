# D-051: The learning loop: export training data, train outside the product, gate on the bench, register the model

- Status: Proposed
- Date: 2026-10-18
- Amends: D-036

## Context

The owner wants the data barthelona collects to teach a model later with Unsloth (2026-10-18). D-036 designs the capture side (opt-in, redaction, `TrainingSample`, `improves_on_seq` pairs, no holdout) and says the export format is chosen when training starts; D-025 defers fine-tuning. Nothing defines the path from a dataset to a better model in a role chain. Issue #155.

Prior art (checked 2026-10-18):
- Unsloth SFT data is chat `messages` (role/content) JSONL; ShareGPT converts to it ([datasets guide](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/datasets-guide)). Models export to GGUF, which LM Studio and Ollama serve.
- Training needs an NVIDIA GPU; AMD is supported, Intel GPUs only help GGUF inference ([requirements](https://www.unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements)). The owner's main PC has no suitable GPU, so training runs on another PC or a rented one.
- Preference-pair field names for DPO were not verified; `docs-researcher` confirms them before the exporter is written.

## Decision

1. **Export.** `barthelona training export --format sft|pairs` writes deterministic JSONL from the dataset: `sft` is `{"messages":[{role,content},...]}` from accepted attempts; `pairs` is `prompt` / `chosen` / `rejected` from `improves_on_seq` pairs. Code stays in the file envelopes the model produced (invariant 5 applies to model output, so samples keep FILE / SEARCH-REPLACE form). A manifest records the dataset digest, filters and counts.
2. **Split by task**, never by attempt, so one task is never in train and eval. The holdout is never exported (D-036). Only local-model samples are exported by default; cloud-model samples need a per-provider owner opt-in and a licence check on the provider terms.
3. **Training stays outside the product.** No torch, Unsloth or CUDA dependency enters `pyproject.toml` (unused dependencies are defects). The repo ships a documented recipe and a script for a GPU host (`docs/training.md`, later), run by the owner or a `cloud_gpu` job.
4. **Registration.** The result is a GGUF served by LM Studio or Ollama and added to `config/models.yaml` as a new local model (`local_ft_vN`) with base model, dataset digest, training recipe hash, `model_hash` and the base model's licence.
5. **Promotion gate.** A fine-tuned model enters a role chain only if a paired bench comparison against its base model on dev and holdout shows an interval that excludes zero (F-59 method). Otherwise it stays registered and unused. Invariant 1 holds: the bench, an oracle, decides.
6. **Scope.** Start with code-producing roles. Planner, spec and test-author samples follow, labelled by whether the run's task was accepted.

## Rationale

Capture without a defined loop is a hope. Keeping training outside the product respects the dependency rule and the Windows/Intel reality; the paired bench keeps a worse tuned model out of production.

## Alternatives considered

- **Train inside barthelona.** Adds heavy GPU dependencies and ties the product to NVIDIA.
- **Export only when training starts (D-036 as written).** Delays discovering that captured fields are missing, and leaves the format untested.
- **Promote on a lower loss.** Loss is not an oracle.

## Consequences

- Roadmap F-81 (export in Phase 1b; train, eval and registry as Phase 2 track 2c); issue #155.
- `TrainingSample` gets an export test against a golden JSONL as soon as the engine writes samples.
- D-036 is amended: the export formats above replace "chosen when training starts".
