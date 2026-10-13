# D-026: Development-time Claude Code configuration is separate from the product runtime

- Status: Proposed
- Amended by: D-032, D-033
- Date: 2026-10-13

## Decision

CLAUDE.md, .claude/ and .mcp.json configure Claude Code only while it develops this repository.

The product's prompts live in policies/vN/prompts. The product never loads .claude/ or CLAUDE.md. If the Claude Agent SDK is ever embedded, it uses setting_sources=[] and a sandboxed cwd.

The Qdrant MCP server is only an inspection aid for development.

## Rationale

Mixing the two confuses responsibilities. The Agent SDK loads .claude/ and CLAUDE.md by default.

## Alternatives considered

Reuse Claude Code skills as product agents: couples the product to a dev tool and to its Anthropic-only models.
