# Project handoff

This is the short orientation index for a fresh human or agent. It is not a transcript or a second
roadmap.

## Read first

1. `AGENTS.md`.
2. `harness/project.yaml`.
3. `harness/capabilities.json`.
4. The active Issue and its acceptance criteria.
5. The relevant repository-local skill.

## Current template state

- Harness version: 0.5.0.
- License: MIT.
- Greenfield profile: `greenfield-core` in `harness/generation.json`.
- Current generation proof: 90 copied files plus one generated intake record, 91 total.
- Generated smoke status: passing with dependency-free harness validation and Python compilation.
- Adoption behavior: separate and ownership-driven; existing application files remain authoritative.
- Publication: local branch only; no remote planning or repository state was changed.

## Product priority

The first application proof is the separate local `scifact-rag` repository. It provides a working
CLI path over the SciFact corpus using PostgreSQL/pgvector, MiniLM embeddings, and a DGX-hosted
NVFP4 answer model. Building and evaluating useful applications takes priority over expanding the
harness or creating a model-effectiveness evaluation framework.

## Capability boundary

The catalog contains 13 inactive skeletons derived from S3NTINEL, Kortex, Procurement Intelligence
Lab, and Macro Technical Pulse. An inactive capability owns its responsibility but contributes no
implementation, dependency, or CI check. Agents must use the catalog before planning and may not
create a duplicate implementation. Initial activation or supersession requires explicit human
approval.

The SciFact proof activates only:

- application composition root;
- CLI interface.

API, MCP, web UI, durable memory, governed reflection, semantic evidence, validation challenges,
AST/LOC analysis, complexity analysis, point-in-time provenance, and role-separated analysis remain
visible but inactive.

## Runtime boundary

The repository contains both Codex and Pi adapters. They are optional project-local instructions,
not globally active skills. The Pi adapter remains available, while weaker-model effectiveness
work is deferred until the template succeeds on real applications.

## Next useful work

1. Use the lean generated core for the next bounded application slice.
2. Evaluate whether each retained artifact helped that slice; remove or defer anything that did not.
3. Activate an existing catalog skeleton only when the application supplies a concrete need and a
   human approves it.
4. Keep verification proportional: focused product checks first, broader harness maintenance only
   when the changed boundary requires it.

## Refresh rule

Update this file only when the current product priority, active capability set, verified generation
result, or recommended next step changes materially. Link to durable evidence instead of adding
historical narrative.
