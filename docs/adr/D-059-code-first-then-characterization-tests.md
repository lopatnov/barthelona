# D-059: Code first, then characterization tests, then a reference check

- Status: Proposed
- Date: 2026-10-25
- Amends: D-009

## Context

The create flow (§6.1) writes the acceptance tests **before any program exists**: `test_author` invents
golden I/O from the requirements, gate G1 freezes it, and `codegen` must satisfy it. The tests are the codegen
oracle, so they have to come first — but a model that has never seen a running program is guessing expected
values.

That guess is the most frequent failure we have recorded, and it does not degrade gracefully:

- `#259` — three of eight golden tests carried wrong expected results and reached G1 unchallenged.
- `#329` — the author emitted a suite no program can satisfy (two tests demand different output for identical
  input), so every repair round paraphrased the same stub for the whole budget.
- `#334` — the author was served a code model and answered with assembly; the run stopped with nothing to show.

The owner's reading, 2026-10-25: "testing before writing the application is doomed to fail; test after it is
written." The evidence above supports it. What must not be lost is invariant 1: an oracle decides, not a model.

Prior art:

- `docs/architecture.md` §6.2: the **edit flow already characterizes** an imported project before changing it;
  `TestOrigin.CHARACTERIZATION` already exists in the domain (§4). The create flow reuses that machinery.
- M. Feathers, _Working Effectively with Legacy Code_ (2004): characterization tests pin observed behavior, and
  their purpose is to catch change, not to prove correctness.
- Golden-master / approval testing (ApprovalTests-style snapshots) is the same idea applied to program output.
- Differential testing against an executable reference (the practice SQLite and CompCert are built on) is what
  turns an observed behavior into a _checked_ one; it is already roadmap item F-114.

## Decision

The create flow becomes code → characterize → reference-check → freeze → repair:

```
intake -> [G0] -> refine_backlog (spec and requirements only)
       -> [G1 specification approved]
       -> architect -> validate_contracts -> header_gen -> skeleton_build -> [G2]
       -> FIRST PASS: sprint loop until the project assembles and runs (behavior not yet judged)
       -> characterize: run the produced program in the emulator or the sandbox and record its real I/O
       -> reference_check: execute the Python reference model of the specification and compare
       -> validate_spec -> [G1b tests approved and frozen]
       -> REPAIR SPRINT LOOP: the frozen tests are the oracle
       -> final_integration -> [G4] -> finalize
```

Rules this decision makes binding:

1. **No model writes an expected value.** A test case is a recording of an executed program or of the reference
   model. The author names the case (input, which requirement it exercises, what it means); the engine fills
   in `expect` from the capture. A test whose expectation has no capture behind it fails validation.
2. **The reference model is mandatory, not optional** (this makes F-114 blocking). It is deterministic Python
   derived from the requirements, it runs in the emulator child or the sandbox with no network, and it is the
   only thing that can say the produced behavior is _right_ rather than merely _stable_. A divergence between
   the capture, the reference model and the requirement stops the run instead of freezing a wrong behavior.
3. **Freezing moves from G1 to G1b.** D-009 keeps its force: from G1b the tests are locked with hashes, and
   changing one is a separate, gated story (`contract_change`). Before G1b nothing is frozen, because nothing
   exists yet.
4. **Two human gates replace one.** `G1` now approves the **specification** (requirements, modules, constraints);
   the new `G1b` approves the **captured tests**. G1 keeps its id and its existing `GateKind`; `G1b` gains a new
   kind (`G1B_TESTS`) and gate id `<run>-G1b`.
5. **The first pass is bounded like any sprint.** If it cannot produce a program that assembles and runs, the run
   stops with its normal stop reason and no tests are frozen; there is nothing to characterize.
6. **Coverage is still checked.** Every requirement needs at least one case whose input exercises it
   (`validate_spec`, unchanged); the reference check then decides whether the captured expectation satisfies it.

## Rationale

- Expected values become observations. The class of bug in `#259` and `#329` cannot exist, because the number in
  the test came out of a program that ran.
- The oracle hierarchy does not weaken: assembler, emulator, reference model and diff decide. The model only
  proposes code and case inputs, which is what invariant 1 asks for.
- Characterization is already implemented for the edit flow, so the create flow reuses `characterize` instead of
  inventing a parallel mechanism.
- The bad outcomes get cheaper: a wrong program now fails at the reference check (a deterministic diff with a
  readable report) instead of burning a repair budget against an impossible suite.

## Alternatives considered

- **Keep tests first, generate expectations from the reference model before G1.** Least disruption, and it fixes
  `#259`, but it still asks the author to describe behavior of a program that does not exist; `#329` (an
  unsatisfiable suite) stays possible, and the failure mode stays silent until codegen.
- **Both, split by requirement kind** (reference-generated tests for exact output, characterization for free
  text). Honest, but two flows to maintain in Phase 1a, and the split is a judgement call per requirement.
- **Status quo plus a stricter prompt and length guard.** Already shipped and insufficient: `#259` happened with
  the guard in place.

## Consequences

- **Roadmap:** Phase 1a is reordered (spec gate, first pass, characterize, test author, G1b, repair loop);
  F-114 (#259) becomes a blocking item for the phase, and this ADR is its rationale.
- **Domain and engine work:** a `characterize` node; a `G1B_TESTS` gate kind; `TestOrigin.CHARACTERIZATION` as
  the default for create-mode cases; a stop reason for a reference divergence (a new `StopReason` value, not
  `max_attempts`); `test_author` loses the job of computing expectations and gains the job of naming cases.
- **Prompts and policies:** the test-author prompt shrinks (no arithmetic); the reference-model prompt is new.
  Both live in `policies/vN/prompts/` when that schema lands.
- **Risk, stated plainly:** a characterization test can bless a wrong program. The mitigations are the reference
  check (mandatory), the human at `G1b`, the requirement-coverage check and the ABI mutation corpus, which must
  stay 100% detected. If the reference check cannot run, the gate does not pass (invariant 1, "a gate that
  errors does not pass").
- **Invariant 4 is unchanged in text** ("tests and contracts are frozen while coding"): coding against an
  unfrozen test now means the first pass, and the repair loop still cannot touch the frozen suite.
- **`docs/architecture.md`:** §5.2 (gate table), §6 (pipeline), §6.1 (create-flow steps) updated with this
  record. Code comments that cite "§6.1 step 4" for the test author need the new step numbers when the nodes
  change.
