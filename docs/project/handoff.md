# Project handoff

This is a concise orientation index for a fresh human or agent. It is not a transcript, decision log, or second roadmap.

## Read first

1. `AGENTS.md`.
2. `harness/project.yaml`.
3. The active GitHub Issue and Project item.
4. Linked files in `docs/adr/`.
5. The relevant repository-local skill.

## Current state

- Harness version: 0.5.0.
- Project status: template; project intake not yet accepted.
- Active engineering loop: Issue #23, Pi tool-call hardening for local OpenAI-compatible models.
- Release state: not applicable.
- Publication target: public GitHub template `stauntonjr/agentic-project-template`.

## Implemented control plane

- Machine-readable project, role, loop, schema, profile, and planning contracts.
- Repository-local skills for intake, existing-solution research, execution, reporting, GitHub planning, ADRs, and release readiness.
- Codex role adapters with separated planner, explorer, implementer, verifier, and release-steward authority.
- Experimental Pi adapter with native skill discovery, workflow prompts, ignored session state, structured context questions, and explicit delegation/sandbox limitations.
- Dependency-free validators, intake rendering, loop evidence, reporting, and GitHub audit/dry-run tools.
- Criterion-linked completion gates with revision-bound verifier verdicts and content-aware baseline/write-scope enforcement.
- Provenance-locked, ownership-aware three-way upgrade plans with explicit apply resolutions, receipts, and rollback.
- Eight isolated forward-test scenarios covering routing, context gaps, evidence, and safety behavior.
- CI for the harness itself.
- Separate harness and product version contracts with current-revision release-impact reporting.
- Profile-driven quality capabilities, concrete Python defaults, repository hygiene files, and a shared local/CI command boundary.
- Dependabot, dependency review, CodeQL, least-privilege workflows, and deterministic full-SHA Action validation.
- Accepted shared-program versus dedicated-application Project topology, with Project #13 as the canonical source and additive field/view/link reconciliation.

## Open decisions

- Macro Technical Pulse's owner selected MIT on 2026-08-23. The decision is recorded here, but the
  application repository has not yet been mutated or relicensed by this template loop.
- Whether Pi should omit an empty `tools` array for OpenAI-compatible continuations remains an
  upstream/provider concern. The adapter documents a tested least-authority continuation pattern.
- Which live GitHub security settings should be reconciled automatically after the first dogfood audit.

## Active dogfood evidence

- Macro Technical Pulse Issue #6 at `b41e3bc` is the isolated application snapshot.
- Adoption preserved tracked application bytes, passed all 44 original tests, and emitted explicit
  reconciliation gaps instead of copying merge-required policy.
- Pi 0.84.1 ran intake-to-report through local SparkRun Qwen with no external spend or GitHub
  writes; research accuracy, invalid tool calls, and empty-tools compatibility gaps are recorded in
  `docs/reports/issue-3-macro-technical-pulse-dogfood.md`.
- Issue #23 adds strict questionnaire sampling, a three-call unavailable-tool ceiling, and a
  reproducible live-model probe before another application dogfood begins.

## Refresh protocol

Update this index only when current state, settled decisions, active work, or the recommended next loop changes materially. Link to authoritative evidence instead of duplicating it.
