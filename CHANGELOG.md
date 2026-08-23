# Changelog

All notable changes to the harness are recorded here. The harness version and a derived project's product version are independent release streams.

## [0.5.0] - Unreleased

### Added

- Accepted shared-program versus dedicated-application GitHub Project topology, with
  Project #13 as the canonical field/view copy source.
- Live, non-destructive Project title, saved-view, and repository-link drift auditing.
- Idempotent creation of missing basic saved views through GitHub's typed API.
- Fail-closed validation for every supported write-bearing planning value and explicit
  drift for ambiguous duplicate live identities.
- A reproducible live-model Pi tool-call probe covering strict questionnaire sampling, valid reads,
  unavailable-tool ceilings, zero-tool sessions, and least-authority continuations.
- A layered domain-routing forward scenario and pinned S3NTINEL evaluation that keep repository
  Spark rules local while exercising reusable loop, verifier, release-steward, and Project
  ownership boundaries.
- Six sanitized disposable recovery fixtures covering dirty worktrees, partial loops, stale
  branches, agent crashes, retry exhaustion, and reviewed resumable handoffs.
- Candidate-versus-approved challenge provenance with explicit human-review promotion and two
  minimized dogfood-derived executable candidates.
- A read-only Kortex provenance and governed-learning evaluation that separates evidence tiers,
  keeps learned policy changes proposed pending human review, uses sanitized durable handoffs, and
  replays interrupted-session recovery without application or memory-store mutation.
- Opt-in, content-free per-loop outcome telemetry with explicit measurement provenance, strict
  local schemas, stdout-only defaults, retrospective observation timestamps, and a de-identified
  aggregation boundary that preserves unavailable values and unlike units.

### Changed

- Derived intake now clears the template's live Project identity and prepares a dedicated
  one-time copy bootstrap; adopters may explicitly select a shared Project instead.
- The planning contract now requires `topology` and `canonical_source`. Existing derived
  repositories must review and add these keys before upgrading.
- Existing-repository adoption now copies only upstream-owned harness internals and records
  merge-required, workflow, test, license, changelog, and dependency-lock paths
  for explicit reconciliation instead of silently overwriting application policy.
- Engineering-loop retries now persist the third consecutive failure as `blocked` without creating
  attempt four. A retry-exhausted resume preserves partial work and starts a new evidence revision
  only from a structured `human:IDENTITY` handoff.

### Fixed

- Adopted harness validation now imports the Actions supply-chain implementation from the
  harness-owned `harness.runtime` namespace. An incompatible application-owned
  `tools/check_actions_supply_chain.py` remains byte-for-byte intact, is reported as a
  reconciliation collision, and no longer causes the copied validator to crash during import.
- Adopt-mode dry runs and applies now record an `adopt` lifecycle, exact reconciliation disposition
  counts, `context_readiness`, and separate reconciliation and overall activation states. Project
  activation remains `provisional` until both adoption gaps and essential intake context are
  resolved; harness validation and reported loop completion fail closed until then.
- Harness validation can use a trusted application-owned GitHub planning loader when the
  application intentionally retains its own planning implementation.
- Adoption preflights every target path, rejects symlink traversal and non-directory ancestors
  before copying, preserves existing generated artifacts under non-overwriting proposal names,
  and refuses a second proposal collision.
- Greenfield template copies apply the same lexical target-root preflight before creating any
  project files.
- The Pi adapter requests strict JSON-schema tool sampling when supported and aborts after three
  consecutive unavailable-tool calls before a fourth sibling can be preflighted, while active calls
  reset the counter.
- Existing-repository adoption can explicitly run an application's authoritative quality command
  before and after copying harness files. It records the command, exit codes, compatibility, and
  implicated copied paths; missing, indeterminate, or incompatible evidence keeps activation
  provisional.
- Universal copied Python harness sources now satisfy Procurement Intelligence Lab's locked Ruff
  0.16.3 format and lint discovery without changing its configuration, lock, or ignore rules.

## [0.4.1] - 2026-08-22

### Fixed

- Live GitHub planning audit now works with supported GitHub CLI versions that do not
  provide `gh api --slurp`, while retaining zero-, single-, and multi-page JSON parsing.

## [0.4.0] - 2026-08-22

### Added

- Provider-neutral roles, skills, engineering loop, evidence reports, intake, GitHub planning, and project profiles.
- Codex and experimental Pi adapters.
- Integrity-checked write scopes, independent verifier verdicts, and provenance-locked harness upgrades.
- Configurable product-version, engineering-quality, and GitHub security contracts.
- Dependabot, dependency review, CodeQL, and immutable GitHub Actions validation.

### Security

- Completion fingerprints worktree, index, hidden index flags, submodules, and embedded repositories.
- Third-party GitHub Actions are pinned to reviewed full commit SHAs.
