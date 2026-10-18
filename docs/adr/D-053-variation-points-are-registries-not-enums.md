# D-053: Variation points are registries of self-describing entries, not enums and factory chains

- Status: Proposed
- Date: 2026-10-18
- Amends: D-045, D-046, D-047

## Context

The owner wants to add an agent, a dialect, a provider or a tool without touching core code (issue #176, from #172 to #175). Today every variation point is closed:

- `Role` is a six-value enum used by `NodeSpec.role` (`domain/enums.py`, `domain/topology.py`), although the catalog and gateway already take roles as strings.
- `Dialect`, `Arch`, `OS`, `ABI` and `ObjFormat` are enums, and `cli/__init__.py` and `scaffold/ci.py` pick behavior with if/elif chains and per-dialect tables. `DialectAdapter` is a protocol, but nothing registers implementations.
- `ProviderConfig.kind` is a `Literal` and has one `base_url` (D-047 `endpoints[]` is not implemented).
- There is no tool concept for ComfyUI, vtracer, linters or fuzzers (F-80, #151), and `Level` is an enum although D-046 calls levels registered checks.

The engine and `policies/` do not exist yet, so this is the cheapest moment to change the shape.

## Decision

1. **One pattern.** A variation point is a *registry*: a mapping from a string id to an entry that declares its own metadata and behavior. Core code looks entries up by id and never branches on a concrete id.
2. **Entry kinds.** Each kind has a small protocol next to its consumer (D-045: ports belong to the consumer):
   - *role*: id, highest model tier, chain key, prompt template. Declared as policy data (`policies/vN/roles.yaml`), so a new agent role is data plus, at most, one node.
   - *dialect / target*: id, file extension, adapter factory, CI snippet. Replaces the extension map, `_make_adapter` and the CI table.
   - *provider backend*: kind id to client class; `endpoints[]` as in D-047.
   - *tool*: id, detect command, optional install action, config schema, diagnostics parser (F-80). Checks (D-046) may reference tools by id.
   - *check / level*: as D-046, keyed by id.
3. **Ids are validated strings.** Pydantic models accept a string checked against the registry at load time (unknown id is a load error naming the valid ids). JSON schemas for AI-composed graphs are generated from the registry (as the `add-node-type` skill already assumes), so the closed vocabulary the validator needs (T1 to T10) is kept.
4. **Registration happens at the composition root** (`engine/wiring.py`, `cli` for headless tools). Entries are plain Python modules or policy files; there is no import-time side-effect discovery and no third-party plugin loading in this phase.
5. **Released `policies/vN/` stay immutable** (invariant 7): a new role or tool becomes available in `vN+1`.
6. **Proof.** Each registry gets a test that registers a fake entry and exercises it end to end with no edit to an enum or factory chain. This is the exit test for #172 to #175.

## Rationale

Open/Closed and the dependency rule (Martin) say new behavior should arrive as new code, not edits to a central switch; Fluent Python and Effective Python prefer small protocols and dispatch tables over type-checking chains. The cost is one lookup table per kind, paid before consumers multiply. Validation at load time keeps the safety the enums gave (typos fail early) and keeps oracles in charge: a registry entry can propose, but acceptance still comes from the gates (invariant 1).

## Alternatives considered

- **Keep enums, add values per feature.** Cheap now, but every new target family (D-050) edits core types and the schema.
- **Setuptools entry points / dynamic plugin discovery.** Powerful, but import-time side effects and third-party code loading conflict with the sandbox and supply-chain rules; revisit after Phase 2.
- **Everything in YAML.** Fine for roles and chains; adapters and checks have typed behavior, so they stay code, selected by id.

## Consequences

- `docs/architecture.md` §4 (enums), §9 and §10 (node registry), §12 (toolchain layer) and §16.2 are updated when the first registry lands; F-86 tracks the work in Phase 1b.
- Issues #172 (roles), #173 (dialects), #174 (providers), #175 (tools and checks) implement the entries; #176 is the umbrella.
- If a registry turns out to need discovery, that is an amendment of this ADR.
