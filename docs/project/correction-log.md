# Failure correction log

This log retains sanitized, reusable corrections for agent or tooling mistakes that are likely to
recur. It is not a transcript, retry counter, incident archive, or substitute for a regression
test. Never record tokens, secrets, private prompts, hidden reasoning, or unnecessary user data.

## Recording contract

Record a correction when a failed approach is repeatable or when another agent could plausibly
choose it again. Include:

- a stable ID, date, affected workflow, and public or synthetic provenance;
- the attempted approach and a short sanitized error signature;
- whether any local or external mutation occurred and how that was verified;
- the corrected command or decision path, including authorization boundaries;
- the exact verification that proved the correction; and
- the durable prevention surface: skill instruction, test, challenge candidate, or tool guard.

Do not rewrite a failure as success. If the correction is not verified, label it proposed. If the
failure exposes an escaped defect with a deterministic oracle, create a candidate under
`harness/challenges/`; do not store a live network call as a replay fixture.

## GH-PLANNING-001: Classic Project shortcut used for a Projects v2 item

- Date: 2026-08-24.
- Workflow: create GitHub Issues and add them to the configured Project v2 roadmap.
- Provenance: Agentic Application Assessor greenfield publication, sanitized operator-visible CLI
  evidence.
- Failed approach: passed `--project` to `gh issue create`.
- Error signature: the CLI attempted the deprecated Projects (classic) lookup and returned a
  Projects-classic deprecation error.
- Mutation check: the command created no Issue; a subsequent complete Issue-list read returned an
  empty list.
- Classification: client-command routing error, not Project drift, authentication failure, or a
  GraphQL API limitation.
- Corrected path:
  1. Create the Issue without `--project` and retain its exact URL.
  2. Preview `python3 tools/github_planning.py add-item --url ISSUE_URL`.
  3. After authorization, run the same command with `--yes`.
  4. Re-read Project items and the Issue's `projectItems` membership.
- Verification: seven Issues were created, added to Projects v2 Project #16, and re-read with exact
  membership; the final live planning audit reported no managed drift.
- Prevention: the GitHub-planning skill forbids the classic shortcut; the idempotent `add-item`
  command pre-reads membership, rejects duplicates, uses `gh project item-add` only when absent,
  and verifies post-write membership; unit tests assert each boundary.

## GH-PLANNING-006: successful Project item write was immediately invisible

- Date: 2026-08-24.
- Workflow: add pull request #43 to the configured Projects v2 roadmap during publication.
- Provenance: sanitized live GitHub CLI evidence from the agentic-project-template repository.
- Failed approach: treated the first complete item-list response after `gh project item-add` as
  immediately consistent.
- Error signature: `Project v2 membership verification found 0 items ... expected 1`.
- Mutation check: no retry of `item-add` occurred. Independent complete re-reads found exactly one
  matching Project item, `PVTI_lAHOAiy8Ic4BhKnPzg30Ghk`, and the pull request's `projectItems`
  field named the expected roadmap.
- Classification: post-mutation read visibility lag, not a failed write, duplicate membership,
  invalid authentication, or Projects-classic routing.
- Corrected path:
  1. Perform the complete pre-read and one authorized `item-add` exactly as before.
  2. If the first complete post-write read has no exact match, retry only the complete read with
     bounded delays.
  3. Stop immediately on one match; fail closed on duplicates, truncation, malformed data, or
     persistent absence.
  4. Never repeat the mutation automatically; re-read live state before any operator retry.
- Verification: unit regressions prove delayed visibility succeeds after one mutation and bounded
  reads, while exhausted visibility fails after one mutation; live state contains exactly one pull
  request #43 membership.
- Prevention: the `add-item` implementation now separates its single mutation from bounded
  post-write reads, and the GitHub-planning guide documents the eventual-consistency boundary.

## GH-PR-METADATA-007: `gh pr edit` queried deprecated Project cards

- Date: 2026-08-24.
- Workflow: update pull request #43's body after pushing verified correction evidence.
- Provenance: sanitized live GitHub CLI evidence from the agentic-project-template repository.
- Failed approach: ran `gh pr edit NUMBER --body-file FILE` with GitHub CLI 2.45.0.
- Error signature: `GraphQL: Projects (classic) is being deprecated ... (projectCards)`.
- Mutation check: an exact pull-request re-read showed that neither correction-loop evidence nor
  the current test count was present; the head commit and existing Project membership were
  unchanged.
- Classification: installed-client GraphQL query incompatibility, not an invalid body file,
  authentication failure, Projects v2 membership error, or pull-request write rejection.
- Corrected path:
  1. Stop after the first failed `gh pr edit`; do not retry the same client route.
  2. Send the reviewed body file to the exact REST pull-request endpoint with
     `gh api --method PATCH repos/OWNER/REPOSITORY/pulls/NUMBER -F body=@FILE`.
  3. Re-read that pull request and require both the expected head SHA and distinguishing body
     content before reporting success.
- Verification: the REST mutation returned pull request #43; a subsequent REST read returned head
  `7cdca280d2ecd5d937126ba155a70c74995827ee` and both the correction-evidence marker and current
  206-test marker.
- Prevention: the GitHub-planning safety reference preserves the REST/body-file fallback and
  mandatory re-read; a repository test requires that packaged guidance and this ledger entry
  remain present.

## GH-AUTH-002: Sandboxed network failure reported as an invalid token

- Date: 2026-08-24.
- Workflow: validate GitHub CLI authentication before a read-only planning audit.
- Provenance: sanitized local CLI evidence from the agentic-project-template workspace.
- Failed approach: treated `gh auth status` inside a network-restricted sandbox as proof that the
  stored credential was invalid.
- Error signature: `Failed to log in` and `token ... is invalid`, followed by `gh api user`
  reporting that it could not connect to `api.github.com`.
- Mutation check: no local credential, GitHub object, or repository state was changed.
- Classification: unavailable network validation misclassified as credential rejection.
- Corrected path:
  1. Check for environment-token overrides without printing values.
  2. Retry the read-only check through the approved network-permission path.
  3. Call `gh api user` and require an authenticated HTTP success before declaring the token valid.
  4. Treat an unreachable API as indeterminate; rotate or reauthenticate only after an actual
     authentication rejection.
- Verification: the network-enabled API returned HTTP 200 for `stauntonjr`; `gh auth status`
  confirmed the keyring credential and expected scopes; the live Projects v2 audit passed.
- Prevention: the GitHub-planning safety reference requires sandbox-blocked network operations to
  use the approved permission path instead of being reported as GitHub or credential limitations.

## LOCAL-RUNTIME-003: Sandboxed loopback failure reported as an offline model

- Date: 2026-08-24.
- Workflow: determine whether the local SparkRun Qwen endpoint was available before a model-diversity
  canary run.
- Provenance: sanitized host Docker, SparkRun, listener, and OpenAI-compatible API evidence from the
  DGX workspace.
- Failed approach: called `http://127.0.0.1:8000/v1/models` only from a restricted sandbox and
  treated its connection failure as proof that the model was offline.
- Error signature: a sandbox-local connection failure to port 8000 even though the host service was
  already running.
- Mutation check: the corrective commands were read-only; they did not start, stop, restart, or
  reconfigure a container, model, listener, or repository.
- Classification: restricted loopback visibility misclassified as a host-runtime outage.
- Corrected path:
  1. Treat a failed network or loopback probe from a restricted runtime as indeterminate.
  2. Use the approved host-permission path to inspect the workload supervisor, such as
     `sparkrun status`.
  3. Inspect the candidate container and its start/restart state with `docker inspect`.
  4. Confirm the host listener with `ss`, then call the expected health or discovery endpoint, such
     as `/v1/models`, from the host boundary.
  5. If host verification is unavailable, report availability as unverified rather than offline.
  6. Never start a replacement workload before checking for an existing instance, especially when
     it can reserve GPU memory or collide on a host port.
- Verification: SparkRun reported job `8337765ded59` running the official
  `qwen3-coder-next-int4-autoround-vllm` recipe; Docker reported its host-network container running
  since `2026-08-24T02:12:31Z` with no restart or OOM state; the host listened on port 8000; and
  `/v1/models` returned `Intel/Qwen3-Coder-Next-int4-AutoRound`. The container start preceded the
  sandbox-only probe.
- Prevention: the engineering-loop skill requires host supervisor/container/listener/API evidence
  before classifying a local service unavailable and forbids starting a duplicate workload first;
  repository tests preserve the correction and reject the superseded availability claim.

## LOCAL-RUNNER-004: Pi shebang lost its adjacent Node runtime

- Date: 2026-08-24.
- Workflow: begin the first bounded paired Qwen canary through the repository model-stress runner.
- Provenance: sanitized local runner preflight in the agentic-project-template workspace.
- Failed approach: invoked the explicitly supplied `bin/pi` with an allowlisted environment whose
  `PATH` contained only system directories. Pi uses `#!/usr/bin/env node`, while its matching Node
  binary is adjacent to Pi in the self-contained installation.
- Error signature: `could not determine Pi version`.
- Mutation check: the runner stopped in its version preflight with `model_invoked: false`; it did
  not call the model, change the existing SparkRun workload, write GitHub state, or retain a model
  transcript.
- Classification: runner executable-resolution defect, not a model, provider, container, or
  endpoint outage.
- Corrected path: run the supplied self-contained Pi installation inside a networkless Bubblewrap
  version preflight, mount the complete installation read-only, and select its adjacent Node through
  the sandbox `PATH`.
- Verification: a registration-free regression inspects the version command's networkless,
  read-only installation mount and recognizes the fixture's semantic version; the repaired live
  runner preflight reports Pi 0.84.1 before model execution.
- Prevention: `test_pi_version_uses_networkless_read_only_self_contained_installation` preserves
  the self-contained runtime contract, and the live command continues to require an explicit
  `--pi` path.

## LOCAL-RUNNER-005: first canary overstated prompt and oracle provenance

- Date: 2026-08-24.
- Workflow: independently verify the first paired Qwen canary and its durable smoke report.
- Provenance: exact local runner source and ignored result digest recorded in the Issue #21 report.
- Failed approach: hashed `task.prompt` into the result while sending a different hard-coded prompt;
  passed every hidden oracle case and expectation through `HARNESS_ORACLE`; buffered model output
  before checking its size; retained arbitrary tool names; and initialized some post-invocation
  error output as `model_invoked: false`.
- Error signature: recorded prompt digest did not identify the prompt Pi received, and generated
  code could read the hidden expected answers from its own environment.
- Mutation check: no additional model invocation, SparkRun/container mutation, GitHub write, or
  retained transcript occurred during correction. The original run remains only diagnostic history.
- Classification: runner provenance, isolation, resource-bound, sanitization, and reporting defect;
  not evidence of a Qwen, Pi, vLLM, Docker, or endpoint failure.
- Corrected path: pass the exact contract prompt; run each oracle case in a separate networkless
  child containing no expectation; bound stdout during execution and discard stderr; mount Pi
  configuration read-only; sanitize tool identities; validate cross-field relationships; freeze
  one resource bundle and seed repository for every lane/trial; and carry invocation state through
  every failure path. The historical report now labels the old `.git`-excluding scope observation
  and post-hoc event-length check precisely instead of treating either as a verified bound. Task
  and resource paths are opened component by component without following a symlinked root or nested
  ancestor, preventing a dirty checkout from redirecting model-visible input outside the root.
- Verification: focused regressions cover prompt equality, answer-free oracle environments,
  operative event-size limits, deep JSON, stable tool categories, strict result relationships,
  schema/custom length parity, frozen-seed identity after source mutation, root/ancestor symlink
  rejection, pre-invocation output validation, and truthful post-invocation failure output.
- Prevention: acceptance-candidate evidence must come from the repaired runner and independent
  review; the first smoke cannot be promoted or used as the accepted baseline.

## LOCAL-RUNNER-006: read-only Pi config triggered a credential-lock startup failure

- Date: 2026-08-24.
- Workflow: begin the three-task, three-trial paired Qwen acceptance-candidate run.
- Provenance: sanitized runner result, host vLLM access log, and disposable zero-tool Pi probes.
- Failed approach: relied only on the synthetic `apiKey` in generated `models.json` while mounting
  the generated Pi configuration read-only. Pi 0.84.1 still consulted its credential store and
  attempted to create `auth.json.lock`, then exited before contacting the provider.
- Error signature: all six initial diagnostic lanes returned exit 1 in under one second, produced
  no edits, usage, settled event, or stable tool error, and generated no request in the vLLM log.
- Mutation check: the invalidated runs changed no candidate file, container, model service, GitHub
  object, or external repository; their sanitized ignored result is diagnostic only.
- Classification: Pi startup/configuration incompatibility, not model quality or endpoint failure.
- Corrected path:
  1. Confirm the existing SparkRun job, container, listener, and `/v1/models` response from the host.
  2. Reproduce the failure in a disposable zero-tool Bubblewrap session using the same read-only
     generated configuration.
  3. Pass Pi the explicit synthetic `--api-key not-needed` argument so it need not consult a
     credential store; never substitute or expose a real credential.
  4. Require a zero-tool Bubblewrap probe to settle and reach the loopback provider before rerunning
     any scored task.
  5. Invalidate every trial produced by the failed startup path rather than counting it as model
     evidence or retrying it as though the model had answered.
- Verification: the direct provider probe and the matching read-only-config Bubblewrap probe both
  settled against `Intel/Qwen3-Coder-Next-int4-AutoRound`; the latter succeeded only after the
  explicit synthetic API-key argument was supplied.
- Prevention: the lane-command regression requires the synthetic argument while retaining the
  read-only config mount; future reports must distinguish a Pi process start from a provider-backed,
  settled model response.
