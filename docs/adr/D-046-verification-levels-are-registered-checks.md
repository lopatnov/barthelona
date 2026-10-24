# D-046: Verification levels are registered checks selected by target family

- Status: Proposed
- Date: 2026-10-17
- Amends: D-007
- Amended by: D-056

## Context

`src/barthelona/verification/ladder.py` hard-codes `_LEVEL_ORDER = [V0, V1, V2]` and one `run_vN` function per level; callers pick them by name (issue #66). V5 and V6 are about to be added (issue #47). The roadmap needs the same level to mean different things per target: WebAssembly replaces V3 with an import/export signature check and V4 with wasmtime (issue #58); a boot sector has its own Definition of Done (§13.2); Win64 adds wine at V5. `TargetProfile.dod` and `LevelResult.status = unsupported` already exist, but nothing selects an implementation per target or says what an unsupported required level means.

## Decision

1. Level ids V0 to V8 stay the stable names used by the DoD table, the UI and training data. Their implementations become **registered checks**:
   - `LevelCheck` protocol: `level`, `supports(ctx) -> Unsupported(reason) | None` (the context carries the target settings; `None` means supported), `async run(ctx) -> LevelResult`.
   - The registry is keyed by target family (for example `native-asm`, later `wasm`). A family may register a different check for the same level.
2. `run_ladder(ctx, up_to)` walks the registry in level order. A level the family does not support yields `LevelResult(status="unsupported")` with the reason as a note diagnostic, never a silent skip. A failed level makes the later levels `skipped`, except checks registered `always_run`; an `always_run` check never turns an earlier failure into a pass.
3. **Required levels** are all levels up to the story kind's bound in `TargetProfile.dod`, with the family's substitutions. **A required level that is not `pass` means the work is not done.** DoD evaluation is "required levels are a subset of the passed levels". An oracle that cannot run does not pass (AGENTS.md goal order).
4. A check receives the whole module list in its context and may batch its commands (one executor call per level, not per file; each call costs about 150 ms, §3).
5. Parsing diagnostics belongs to the dialect or tool adapter, not to the check. The check gets argv and a parser from the adapter.
6. Adding a check needs good and bad entries in the ABI mutation corpus where it is an ABI check (existing invariant), and a `FakeExecutor` unit test.

## Rationale

Today the ladder is three functions. V3 to V6 plus per-target variants as more branches in one module would turn it into the project's god module, and the first WebAssembly target would have to edit it. A registry keeps each level in its own small unit (Clean Code), makes "unsupported" explicit, and puts the extension point where the owner's later targets will land. Doing it before V5 and V6 means two levels move, not six.

## Alternatives considered

- **Keep functions and add `if target.arch == ...`.** Cheapest now, most expensive at the first new target.
- **Per-target ladder classes.** Duplicates the shared V0 to V2 logic across families.
- **Declare levels in YAML.** The checks are code with typed inputs; data would only pick among registered checks, which the registry already does.

## Consequences

- Port V0 to V2 to the registry with unchanged behaviour and tests (issue #66); `barthelona verify` and the `ladder` node call `run_ladder`.
- `docs/architecture.md` §13.1 and §12 are updated in the same change.
- Depends on the session API of D-043 for the context object; the two changes can land in either order if the context hides the executor behind a small interface.
