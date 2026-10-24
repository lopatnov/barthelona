# D-057: Agents get `.env` keys only through the `-LoadEnv` switch of the dev wrappers

- Status: Proposed
- Date: 2026-10-24
- Amends: invariant 10

## Context

Invariant 10 says secrets come only from env vars and agents never read `.env`; a guard hook blocks reading it, sourcing it and dumping env vars. The hackathon work needs agents to run the product's own commands that call Meterless, Zetaris and the other providers. Until now the owner had to `setx` each key and restart the app. On 2026-10-24 the owner asked that agents be able to use the values in `.env`, and chose the smallest change (the switch only; the guard hooks and `settings.json` stay as they are).

## Decision

1. `scripts/dev.ps1 -LoadEnv <command>` and `scripts/dev.sh -LoadEnv <command>` read the repository's `.env` and place each `KEY=VALUE` line, whose name is not already set, in the environment of that one command. The variables are removed when the command ends. Values are never printed, logged or returned; the wrappers only parse the file.
2. The agent still never reads, prints, copies or sources `.env`, and still never dot-sources `activate.*`. The guard hooks are unchanged, so `-LoadEnv cat .env` is blocked by the existing rule on an unquoted `.env` operand.
3. A command run this way can itself print a key (a product bug or a careless command). Product code already treats keys as secrets (invariant 10), and the guard blocks the known dumping paths; this ADR adds no protection against a command that deliberately prints its own environment.
4. No permission is pre-approved: every `-LoadEnv` command asks the owner first, so the owner sees which command receives the keys.

## Alternatives considered

- **Owner runs `setx` per key (status quo):** safest, no repo change, but every new key needs a restart and the owner's time.
- **Let agents read `.env`:** puts every cloud key into the model context and the transcript. Rejected.
- **`-LoadEnv` plus a guard-hook rule and pre-approved zetaris commands:** offered to the owner and not chosen. It can be added later by the owner.

## Consequences

- Inline `# comments` after unquoted values are not stripped, and values with embedded quotes are taken literally; `.env` lines are simple `KEY=VALUE` by convention.
- Keys already set in the process win over `.env`, so a `setx` value is never overridden.
- The PowerShell wrapper has no automated test in CI (no PowerShell with a fake `.env` in the sandbox); the bash twin was tested with fake values.
