# Verification efficiency contract

## Review collection

Independent review is one bounded pass over one stable candidate. The reviewer should inspect all
accepted criteria and proportionate adjacent risks before returning an ordinary finding batch.
Each finding needs a severity, criterion, bounded reproduction, and smallest credible repair.
Deduplicate findings that share the same failure boundary and repair.

Do not invalidate the candidate or restart implementation after each ordinary finding. Close the
review as `batch-ready`, record one repair decision, then start one new attempt. Close as `clean`
only with zero findings. Interrupt immediately only for a critical active secret exposure,
destructive effect, or uncontrolled external effect; record the specific emergency boundary.

## Verification ladder

| Tier | Use | Normal cadence |
|---|---|---|
| `static` | format, lint, schema, compilation, content checks | while editing |
| `targeted` | tests for the touched behavior and reproductions | while editing |
| `affected` | all contracts plausibly affected by the closed repair batch | once per repair attempt |
| `external` | model, network, service, or other expensive evidence | only when due or invalidated |
| `full` | complete repository gate | exactly once on the final current attempt |

A failing complete gate ends the attempt; repair under a new attempt rather than repeatedly running
the full gate against a moving candidate.

## Documentation-only impact classifier

Classify a candidate as documentation-only only when every changed path is non-executable prose
and the diff changes no behavior, authority, acceptance boundary, command, schema, generated
artifact, dependency, provenance record, or machine-consumed instruction. Eligible examples are
spelling, grammar, navigation, and factual clarification in ordinary README or `docs/` prose.

Treat these as behavior-affecting even when their filename is Markdown: `AGENTS.md`, skills,
prompts, ADR decisions, security or release policy, command examples that define an operative
contract, generated reports used as evidence, and documentation consumed by tests or tooling.
Configuration, schemas, manifests, locks, workflows, source, tests, and executable files are also
behavior-affecting. Ambiguous changes are behavior-affecting and use affected-contract checks.

Record the classification, changed paths, and rationale. A documentation-only classification may
replace unrelated affected-contract checks with targeted link, rendering, spelling, or factual
consistency checks. The final full gate remains mandatory on the exact reviewed candidate, as do
fresh candidate identity, independent review, scope enforcement, and release-impact assessment.

## Expensive-evidence reuse

Reuse is acceptable only when the retained artifact is immutable and the record includes its
source, SHA-256 digest, and a specific applicability rationale. Compare candidate changes against
the evidence inputs: prompts, model/provider, tools, runtime, resource bundle, task corpus, oracle,
limits, and behavior under evaluation. If any applicable boundary changed or cannot be proven
unchanged, rerun. Reuse is supplemental and never satisfies the final full gate.

## Revision and attempt semantics

- Increment `revision` only when objective, acceptance criteria, or declared write scope changes.
- Increment `attempt_id` when repairing implementation under the same contract.
- A finding does not automatically change the contract.
- Before either transition can supersede a finding batch, record its matching revise or reject
  verdict while the reviewed candidate is still unchanged. A reason-only revision is invalid.
- Count criterion evidence in approvals, reports, and telemetry only when it is bound to the exact
  current candidate; legacy or stale evidence remains history rather than current acceptance.
- Record review and check duration so the report can expose repeated work and future optimization
  can be evidence-based.
- An in-flight schema-1.2 run uses the explicit `migrate-run` command to add schema-1.3 review and
  check metadata while preserving the original baseline; it is not restarted after implementation.
