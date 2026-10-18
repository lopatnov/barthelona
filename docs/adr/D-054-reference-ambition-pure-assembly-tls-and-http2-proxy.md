# D-054: The reference ambition is a pure-assembly TLS 1.3 and HTTP/2 reverse proxy

- Status: Proposed
- Date: 2026-10-18
- Amends: D-050

## Context

The owner asked (2026-10-18) whether Barthelona could build his own reverse proxy for files and API requests with HTTP/2. Told that D-050 reaches a proxy only as a C application with a linked TLS library, he set the bar higher: TLS must also be written in assembly, with no linked TLS or crypto library, so that both sides share one picture of how complex the final systems are. The network demo repo is the natural home, and by the demo rule (AGENTS.md) Barthelona builds all of it.

This is far beyond the current plan. Phase 6 targets a JSON-configured proxy in C. The ladder has no crypto, constant-time, interop or protocol-fuzz oracles, there is no spec-traceability step, and sprints are sized for small tasks (#180 to #186).

Prior art:
- Project Wycheproof: edge-case test vectors for crypto libraries, Apache-2.0 ([repo](https://github.com/google/wycheproof)).
- RFC 8448 gives full TLS 1.3 handshake traces with every key, usable as frozen tests ([RFC](https://www.rfc-editor.org/rfc/rfc8448)).
- h2spec (HTTP/2 conformance) and tlsfuzzer / TLS-Anvil (TLS conformance) are existing interop oracles ([h2spec](https://github.com/summerwind/h2spec), [tlsfuzzer](https://github.com/tlsfuzzer/tlsfuzzer), [TLS-Anvil](https://github.com/tls-attacker/TLS-Anvil)).
- dudect and ctgrind show how to test constant-time behavior empirically ([dudect](https://github.com/oreparaz/dudect), [ctgrind](https://www.imperialviolet.org/2010/04/01/ctgrind.html)).

## Decision

1. **Reference bar.** A pure-assembly reverse proxy (TLS 1.3, HTTP/2 with HPACK, file serving, API forwarding, no linked TLS or crypto library) is the reference complexity for architecture reviews. It is a direction, not a phase-gating promise: it lives in a new roadmap Phase 7, after Phase 6, and does not change the order "assembler first".
2. **Oracle classes it needs.** Each is registered as a check or tool (D-046, D-053), not a special case:
   - crypto known-answer and differential tests (#183);
   - constant-time / secret-flow checks (#184);
   - protocol conformance and interop tools in a loopback-only sandbox profile (#185);
   - fuzzing and memory-safety checks for assembly (#186);
   - spec ingestion with requirement-to-test traceability (#182).

   Not an oracle but required: long-horizon module-DAG decomposition (#181). Disassembly policy is D-055 (#180).
3. **Independent test sources.** Vectors and conformance tests come from pinned, hashed external corpora and tools, never from the model that writes the code (invariants 1 and 4).
4. **Honesty rule.** Passing these oracles does not make the result production-grade crypto. The demo README states that it is an experiment, unaudited, and not for protecting real data.
5. **Local models first.** Whether local models can write a module at all is measured per PC (D-052); a module that only a cloud model can produce is recorded as a finding, not hidden.

## Rationale

The ladder's principle (invariant 1) is that oracles accept work. For crypto and protocols the oracles that matter are different from ABI checks, so naming them now keeps Phase 1b registries (D-053) from freezing a vocabulary without them.

## Alternatives considered

- **Keep TLS as a linked library (D-050 as is).** Simpler and safer, but contradicts the owner's stated goal.
- **Hand-write the crypto and have the system only glue it.** Violates the demo rule.
- **Treat it as out of scope.** Leaves the architecture unprepared for the stated bar.

## Consequences

- `docs/roadmap.md` gets Phase 7 and follow-ups F-87 to F-94; the umbrella is #179.
- Phase 1b registries (D-053) must be able to hold new check families and tools without enum edits.
- No code changes now.
