---
name: project-intake
description: Interview a user and reconcile repository evidence into durable project requirements. Use for a new project, adoption of an existing repository, refresh of stale assumptions, or a gap-only requirements pass; do not use for a single already-specified code change.
---

# Project intake

Build the project contract from evidence and short, progressive dialogue. Do not ask the user for facts available in the repository or live GitHub state.

## Select a mode

- `new`: initialize a greenfield project.
- `adopt`: reverse-engineer current behavior and identify governance gaps.
- `refresh`: revisit time-sensitive or provisional answers.
- `gap-only`: ask only unanswered, contradictory, or low-confidence questions.

Read `references/question-bank.md` before interviewing. Read the chosen profile in `harness/profiles/` and `harness/schemas/intake.schema.json`.

## Procedure

1. Inspect `AGENTS.md`, `harness/project.yaml`, handoff, ADRs, source tree, build files, tests, Git remotes/status, and GitHub state when authorized.
2. Create an evidence map of observed facts, existing decisions, contradictions, and gaps.
3. Assess context readiness: intent, acceptance, constraints, authority, evidence, and current state. Ask focused follow-ups only for gaps that cannot be safely discovered or resolved with a recorded low-risk assumption.
4. Ask one small question batch at a time. Offer a recommended default with its consequence. Do not overwhelm the user with the full questionnaire.
5. Record each important answer with value, status, source, and recorded date. Status is `confirmed`, `provisional`, `assumed`, `TBD`, or `not-applicable`.
6. Surface contradictions explicitly. Do not choose between conflicting authoritative sources without the user's decision.
7. Summarize each completed phase and allow corrections.
8. Save the intake record, then render with:

   ```bash
   python3 tools/project_intake.py --answers PATH --mode MODE --apply
   ```

9. Run `make smoke` and inspect the diff.
10. Present the charter, scope, nonfunctional requirements, autonomy boundary, open decisions, GitHub plan, assumptions, and generated files for explicit acceptance.

## Required outputs

- `harness/intake.json` with status, source, and date for each answer.
- Updated `harness/project.yaml`.
- `docs/project/charter.md` and `docs/project/working-agreements.md`.
- Updated `docs/project/handoff.md`.
- Reconciled `.github/planning.json` without live writes unless separately authorized.

Do not store private preferences in public project policy. Put user-local preferences in the ignored `.harness/preferences.local.json` unless the user deliberately promotes them.
