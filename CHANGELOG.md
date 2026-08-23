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

### Changed

- Derived intake now clears the template's live Project identity and prepares a dedicated
  one-time copy bootstrap; adopters may explicitly select a shared Project instead.
- The planning contract now requires `topology` and `canonical_source`. Existing derived
  repositories must review and add these keys before upgrading.
- Existing-repository adoption now copies only upstream-owned harness internals and records
  merge-required, workflow, test, license, changelog, and dependency-lock paths
  for explicit reconciliation instead of silently overwriting application policy.

### Fixed

- Harness validation can use a trusted application-owned GitHub planning loader when the
  application intentionally retains its own planning implementation.
- Adoption preflights every target path, rejects symlink traversal and non-directory ancestors
  before copying, preserves existing generated artifacts under non-overwriting proposal names,
  and refuses a second proposal collision.
- Greenfield template copies apply the same lexical target-root preflight before creating any
  project files.

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
