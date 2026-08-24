#!/usr/bin/env python3
"""Create integrity-checked engineering-loop records and evidence-backed reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .common import git, load_json, repository_root, utc_now, write_json
except ImportError:  # Direct script execution.
    from common import git, load_json, repository_root, utc_now, write_json


RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CRITERION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
CHECK_STATUSES = ("passed", "failed", "skipped", "not-run")
CHECK_TIERS = ("static", "targeted", "affected", "full", "external")
EVIDENCE_ORIGINS = ("executed", "reused")
VERDICTS = ("approve", "revise", "reject")
REVIEW_OUTCOMES = ("clean", "batch-ready", "emergency-stop")
FINDING_SEVERITIES = ("low", "medium", "high", "critical")
EMERGENCY_BOUNDARIES = (
    "secret-exposure",
    "destructive-effect",
    "uncontrolled-external-effect",
)
RELEASE_IMPACTS = ("none", "patch", "minor", "major")
FINAL_STATES = ("reported", "blocked", "abandoned")
RUN_SCHEMA_VERSION = "1.3"
RESUME_HANDOFF_SCHEMA_VERSION = "1.0"
DEFAULT_MAXIMUM_CONSECUTIVE_FAILURES = 3


def git_text(root: Path, *args: str) -> str:
    result = git(root, *args, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def current_commit(root: Path) -> str:
    return git_text(root, "rev-parse", "HEAD") or "UNBORN"


def make_run_id(root: Path) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    revision = current_commit(root)
    suffix = revision[:8] if revision != "UNBORN" else "unborn"
    base = f"{timestamp}-{suffix}"
    candidate = base
    index = 2
    while (root / ".harness/runs" / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def run_path(root: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"invalid run ID: {run_id}")
    return root / ".harness/runs" / run_id / "run.json"


def load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = run_path(root, run_id)
    return path, load_json(path)


def migrate_run(root: Path, run_id: str) -> dict[str, Any]:
    path, record = load_run(root, run_id)
    source_version = record.get("schema_version")
    if source_version not in {"1.2", RUN_SCHEMA_VERSION}:
        raise ValueError(
            f"no engineering-loop migration from schema {source_version!r} to {RUN_SCHEMA_VERSION}"
        )
    record.setdefault("review_cycles", [])
    for check in record.get("checks", []):
        check.setdefault("tier", "targeted")
        check.setdefault("duration_seconds", 0.0)
        check.setdefault("evidence_origin", "executed")
        check.setdefault("reuse_source", None)
        check.setdefault("artifact_digest", None)
        check.setdefault("applicability", None)
        check.setdefault("candidate", None)
    for verdict in record.get("verdicts", []):
        verdict.setdefault("review_id", None)
    if source_version == "1.2":
        record["schema_version"] = RUN_SCHEMA_VERSION
        record.setdefault("telemetry", {}).setdefault("schema_migrations", []).append(
            {
                "from": source_version,
                "to": RUN_SCHEMA_VERSION,
                "recorded_at": utc_now(),
                "preserved_baseline": True,
            }
        )
    write_json(path, record)
    return record


def normalize_repository_path(value: str, *, kind: str) -> str:
    raw = value.strip().replace("\\", "/")
    while raw.endswith("/"):
        raw = raw[:-1]
    path = Path(raw)
    if not raw or raw == "." or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid declared {kind}: {value}")
    normalized = path.as_posix()
    if normalized == ".git" or normalized.startswith(".git/"):
        raise ValueError("declared write scope cannot include .git")
    return normalized


def make_write_set(exact_paths: Iterable[str], prefixes: Iterable[str]) -> list[dict[str, str]]:
    entries = [
        {"mode": "exact", "path": normalize_repository_path(path, kind="path")}
        for path in exact_paths
    ]
    entries.extend(
        {"mode": "prefix", "path": normalize_repository_path(path, kind="prefix")}
        for path in prefixes
    )
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry["mode"], entry["path"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def parse_criteria(values: Iterable[str]) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        identifier, separator, text = value.partition("=")
        identifier = identifier.strip()
        text = text.strip()
        if not separator or not CRITERION_ID.fullmatch(identifier) or not text:
            raise ValueError(f"criterion must be ID=TEXT with a valid ID: {value}")
        if identifier in seen:
            raise ValueError(f"duplicate acceptance criterion: {identifier}")
        seen.add(identifier)
        criteria.append({"id": identifier, "text": text, "waiver": None})
    if not criteria:
        raise ValueError("at least one acceptance criterion is required")
    return criteria


def path_fingerprint(path: Path) -> tuple[str, str | None]:
    try:
        stat_result = path.lstat()
    except FileNotFoundError:
        return "absent", None
    if path.is_symlink():
        target = os.readlink(path)
        return "symlink", hashlib.sha256(target.encode("utf-8", "surrogateescape")).hexdigest()
    if path.is_file():
        digest = hashlib.sha256()
        digest.update(f"mode:{stat_result.st_mode & 0o7777}\0".encode("ascii"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "file", digest.hexdigest()
    if path.is_dir():
        return "directory", None
    metadata = f"{stat_result.st_mode}:{stat_result.st_size}:{stat_result.st_mtime_ns}"
    return "other", hashlib.sha256(metadata.encode("ascii")).hexdigest()


def index_fingerprint(root: Path, relative: str) -> list[dict[str, str]]:
    result = git(root, "ls-files", "--stage", "-z", "--", relative, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"could not inspect index entry for {relative}")
    entries: list[dict[str, str]] = []
    for token in result.stdout.split("\0"):
        if not token:
            continue
        metadata, separator, path = token.partition("\t")
        parts = metadata.split()
        if not separator or len(parts) != 3:
            raise ValueError(f"unexpected Git index entry: {token!r}")
        mode, object_id, stage = parts
        entries.append({"mode": mode, "object_id": object_id, "stage": stage, "path": path})
    return entries


def nested_repository_digest(root: Path) -> str:
    head = git_text(root, "rev-parse", "HEAD")
    if not head:
        raise RuntimeError(f"dirty gitlink is not an inspectable repository: {root}")
    full_index = git(root, "ls-files", "--stage", "-z", check=False)
    if full_index.returncode != 0:
        raise RuntimeError(full_index.stderr.strip() or f"could not inspect nested index: {root}")
    payload = {
        "head": head,
        "index": full_index.stdout,
        "dirty": capture_worktree_snapshot(root),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def is_repository_root(path: Path) -> bool:
    result = git(path, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == path.resolve()
    except OSError:
        return False


def hidden_index_paths(root: Path) -> dict[str, list[str]]:
    flags: dict[str, set[str]] = {}
    for option, label, predicate in (
        ("-v", "assume-unchanged", lambda tag: tag.islower()),
        ("-t", "skip-worktree", lambda tag: tag == "S"),
    ):
        result = git(root, "ls-files", option, "-z", check=False)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or f"could not inspect index flags with {option}"
            )
        for token in result.stdout.split("\0"):
            if not token:
                continue
            tag, separator, path = token.partition(" ")
            if not separator or len(tag) != 1:
                raise ValueError(f"unexpected Git index flag entry: {token!r}")
            if predicate(tag):
                flags.setdefault(path, set()).add(label)
    return {path: sorted(values) for path, values in flags.items()}


def snapshot_entry(
    root: Path,
    relative: str,
    status: str,
    *,
    index_flags: Iterable[str] = (),
) -> dict[str, Any]:
    index = index_fingerprint(root, relative)
    target = root / relative
    if any(item["mode"] == "160000" for item in index):
        kind, digest = "gitlink", nested_repository_digest(target)
    elif target.is_symlink():
        kind, digest = path_fingerprint(target)
    elif target.is_dir():
        if not is_repository_root(target):
            raise RuntimeError(f"directory status entry cannot be fingerprinted safely: {relative}")
        kind, digest = "nested-repository", nested_repository_digest(target)
    else:
        kind, digest = path_fingerprint(target)
    return {
        "path": relative,
        "status": status,
        "kind": kind,
        "digest": digest,
        "index": index,
        "index_flags": sorted(index_flags),
    }


def _excluded_from_snapshot(path: str, run_id: str | None) -> bool:
    if not run_id:
        return False
    internal = f".harness/runs/{run_id}"
    return path == internal or path.startswith(f"{internal}/")


def capture_worktree_snapshot(root: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    result = git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not capture Git working-tree status")
    tokens = result.stdout.split("\0")
    entries: list[dict[str, Any]] = []
    flags_by_path = hidden_index_paths(root)
    seen_paths: set[str] = set()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if len(token) < 4 or token[2] != " ":
            raise ValueError(f"unexpected Git porcelain entry: {token!r}")
        status = token[:2]
        path = token[3:].rstrip("/")
        paths = [(path, status)]
        if "R" in status or "C" in status:
            if index >= len(tokens) or not tokens[index]:
                raise ValueError("incomplete Git rename/copy status entry")
            paths.append((tokens[index].rstrip("/"), f"{status}:source"))
            index += 1
        for relative, path_status in paths:
            if _excluded_from_snapshot(relative, run_id):
                continue
            entries.append(
                snapshot_entry(
                    root,
                    relative,
                    path_status,
                    index_flags=flags_by_path.get(relative, []),
                )
            )
            seen_paths.add(relative)
    for relative, index_flags in flags_by_path.items():
        if relative in seen_paths or _excluded_from_snapshot(relative, run_id):
            continue
        entries.append(snapshot_entry(root, relative, "index-hidden", index_flags=index_flags))
    return sorted(entries, key=lambda item: (item["path"], item["status"]))


def snapshot_map(entries: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["path"]: entry for entry in entries}


def worktree_delta(record: dict[str, Any], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = snapshot_map(record.get("baseline", {}).get("entries", []))
    now = snapshot_map(current)
    delta: list[dict[str, Any]] = []
    for path in sorted(set(baseline) | set(now)):
        before = baseline.get(path)
        after = now.get(path)
        if before != after:
            delta.append({"path": path, "before": before, "after": after})
    return delta


def committed_paths_since_start(root: Path, start_commit: str) -> list[str]:
    end_commit = current_commit(root)
    if end_commit == start_commit or end_commit == "UNBORN":
        return []
    if start_commit == "UNBORN":
        result = git(root, "ls-files", "-z", check=False)
    else:
        result = git(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            start_commit,
            end_commit,
            check=False,
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or "could not inspect committed paths"
        raise RuntimeError(detail)
    return sorted({path for path in result.stdout.split("\0") if path})


def path_is_declared(path: str, write_set: Iterable[dict[str, str]]) -> bool:
    for entry in write_set:
        declared = entry["path"]
        if entry["mode"] == "exact" and path == declared:
            return True
        if entry["mode"] == "prefix" and (path == declared or path.startswith(f"{declared}/")):
            return True
    return False


def scope_evidence(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    current = capture_worktree_snapshot(root, record["run_id"])
    delta = worktree_delta(record, current)
    delta_by_path = {item["path"]: item for item in delta}
    baseline = snapshot_map(record.get("baseline", {}).get("entries", []))
    for path in committed_paths_since_start(root, record["start_commit"]):
        if _excluded_from_snapshot(path, record["run_id"]):
            continue
        if path in delta_by_path:
            delta_by_path[path]["committed_since_start"] = True
            continue
        after = snapshot_entry(root, path, "committed")
        item = {
            "path": path,
            "before": baseline.get(path),
            "after": after,
            "committed_since_start": True,
        }
        delta.append(item)
        delta_by_path[path] = item
    delta.sort(key=lambda item: item["path"])
    violations = [
        item["path"]
        for item in delta
        if not path_is_declared(item["path"], record.get("declared_write_set", []))
    ]
    return {
        "baseline": record.get("baseline", {}).get("entries", []),
        "current": current,
        "delta": delta,
        "violations": violations,
    }


def candidate_identity(root: Path, record: dict[str, Any]) -> dict[str, str]:
    scope = scope_evidence(root, record)
    payload = {
        "run_id": record["run_id"],
        "revision": record["revision"],
        "attempt_id": record["attempt_id"],
        "commit": current_commit(root),
        "delta": scope["delta"],
        "release_impact": record.get("release_impact"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    impact = json.dumps(payload["release_impact"], sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return {
        "commit": payload["commit"],
        "tree_digest": f"sha256:{hashlib.sha256(serialized).hexdigest()}",
        "release_impact_digest": f"sha256:{hashlib.sha256(impact).hexdigest()}",
    }


def start_run(
    root: Path,
    objective: str,
    issue: str | None,
    run_id: str | None = None,
    *,
    acceptance_criteria: list[dict[str, Any]] | None = None,
    declared_write_set: list[dict[str, str]] | None = None,
    implementers: list[str] | None = None,
) -> dict[str, Any]:
    if not objective.strip():
        raise ValueError("objective is required")
    identifier = run_id or make_run_id(root)
    path = run_path(root, identifier)
    if path.exists():
        raise ValueError(f"run already exists: {identifier}")
    criteria = acceptance_criteria or []
    if not criteria:
        raise ValueError("at least one acceptance criterion is required")
    ids = [item.get("id") for item in criteria]
    if len(ids) != len(set(ids)) or any(
        not isinstance(item, str) or not CRITERION_ID.fullmatch(item) for item in ids
    ):
        raise ValueError("acceptance criteria require unique, valid IDs")
    authors = [item.strip() for item in (implementers or []) if item.strip()]
    if not authors:
        raise ValueError("at least one implementer identity is required")
    if len(authors) != len(set(authors)):
        raise ValueError("implementer identities must be unique")
    branch = git_text(root, "branch", "--show-current") or "DETACHED_OR_UNBORN"
    record: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": identifier,
        "revision": 1,
        "attempt_id": 1,
        "objective_seed": objective,
        "objective": objective,
        "issue": issue,
        "acceptance_criteria": criteria,
        "declared_write_set": declared_write_set or [],
        "implementers": authors,
        "baseline": {
            "captured_at": utc_now(),
            "entries": capture_worktree_snapshot(root, identifier),
        },
        "started_at": utc_now(),
        "finished_at": None,
        "start_commit": current_commit(root),
        "end_commit": None,
        "branch": branch,
        "state": "intake",
        "checks": [],
        "review_cycles": [],
        "verdicts": [],
        "release_impact": None,
        "revision_history": [],
        "attempt_history": [],
        "retry_policy": {
            "maximum_consecutive_failures": configured_retry_limit(root),
            "on_exhaustion": "stop-and-escalate",
        },
        "agent_handoffs": [],
        "decisions": [],
        "risks": [],
        "telemetry": {},
    }
    write_json(path, record)
    return record


def criterion_ids(record: dict[str, Any]) -> set[str]:
    return {item["id"] for item in record.get("acceptance_criteria", [])}


def active_criterion_ids(record: dict[str, Any]) -> set[str]:
    return {
        item["id"]
        for item in record.get("acceptance_criteria", [])
        if not item.get("waiver") or item["waiver"].get("revision") != record.get("revision")
    }


def current_passed_criteria(
    record: dict[str, Any], candidate: dict[str, str] | None = None
) -> set[str]:
    passed: set[str] = set()
    for check in record.get("checks", []):
        if (
            check.get("status") == "passed"
            and check.get("revision") == record.get("revision")
            and check.get("attempt_id") == record.get("attempt_id")
            and (candidate is None or check.get("candidate") == candidate)
        ):
            passed.update(check.get("criterion_ids", []))
    return passed


def record_check(
    root: Path,
    run_id: str,
    *,
    name: str,
    command: str,
    status: str,
    evidence: str,
    criteria: Iterable[str] = (),
    tier: str = "targeted",
    duration_seconds: float = 0.0,
    evidence_origin: str = "executed",
    reuse_source: str | None = None,
    artifact_digest: str | None = None,
    applicability: str | None = None,
) -> dict[str, Any]:
    if status not in CHECK_STATUSES:
        raise ValueError(f"invalid check status: {status}")
    if not name.strip() or not command.strip() or not evidence.strip():
        raise ValueError("check name, command, and evidence are required")
    if tier not in CHECK_TIERS:
        raise ValueError(f"invalid check tier: {tier}")
    if (
        not isinstance(duration_seconds, (int, float))
        or isinstance(duration_seconds, bool)
        or not math.isfinite(duration_seconds)
        or duration_seconds < 0
    ):
        raise ValueError("check duration must be a finite non-negative number")
    if evidence_origin not in EVIDENCE_ORIGINS:
        raise ValueError(f"invalid evidence origin: {evidence_origin}")
    if evidence_origin == "reused":
        if not reuse_source or not reuse_source.strip():
            raise ValueError("reused evidence requires a source")
        if not artifact_digest or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest):
            raise ValueError("reused evidence requires an immutable sha256 artifact digest")
        if not applicability or not applicability.strip():
            raise ValueError("reused evidence requires an applicability rationale")
        if tier == "full":
            raise ValueError("the final full gate must be executed, not reused")
    elif reuse_source or artifact_digest or applicability:
        raise ValueError("reuse metadata is valid only when evidence origin is reused")
    path, record = load_run(root, run_id)
    linked = list(dict.fromkeys(criteria))
    unknown = sorted(set(linked) - criterion_ids(record))
    if unknown:
        raise ValueError(f"check references unknown criteria: {', '.join(unknown)}")
    check_candidate = candidate_identity(root, record)
    record["checks"].append(
        {
            "check_id": f"check-{len(record['checks']) + 1:03d}",
            "revision": record.get("revision", 0),
            "attempt_id": record.get("attempt_id", 0),
            "criterion_ids": linked,
            "name": name,
            "command": command,
            "status": status,
            "evidence": evidence,
            "tier": tier,
            "duration_seconds": float(duration_seconds),
            "evidence_origin": evidence_origin,
            "reuse_source": reuse_source,
            "artifact_digest": artifact_digest,
            "applicability": applicability,
            "candidate": check_candidate,
            "recorded_at": utc_now(),
        }
    )
    write_json(path, record)
    return record


def open_review_cycle(record: dict[str, Any]) -> dict[str, Any] | None:
    for cycle in reversed(record.get("review_cycles", [])):
        if cycle.get("status") == "open":
            return cycle
    return None


def current_closed_reviews(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        cycle
        for cycle in record.get("review_cycles", [])
        if cycle.get("revision") == record.get("revision")
        and cycle.get("attempt_id") == record.get("attempt_id")
        and cycle.get("status") == "closed"
    ]


def current_finding_reviews(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        cycle
        for cycle in current_closed_reviews(record)
        if cycle.get("outcome") in {"batch-ready", "emergency-stop"}
    ]


def require_finding_repair_transition(root: Path, record: dict[str, Any]) -> None:
    finding_reviews = current_finding_reviews(record)
    if not finding_reviews:
        return
    finding_review = finding_reviews[-1]
    repair_verdicts = [
        verdict
        for verdict in record.get("verdicts", [])
        if verdict.get("revision") == record.get("revision")
        and verdict.get("attempt_id") == record.get("attempt_id")
        and verdict.get("review_id") == finding_review.get("review_id")
        and verdict.get("decision") in {"revise", "reject"}
    ]
    if not repair_verdicts:
        raise ValueError("a finding batch requires a matching revise or reject verdict before repair")
    if finding_review.get("closing_candidate") != candidate_identity(root, record):
        raise ValueError("the finding-batch candidate changed before the repair attempt was recorded")


def start_review(root: Path, run_id: str, *, reviewer: str) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer identity is required")
    path, record = load_run(root, run_id)
    if reviewer in record.get("implementers", []):
        raise ValueError(f"reviewer {reviewer!r} is recorded as an implementer")
    if open_review_cycle(record):
        raise ValueError("an independent review cycle is already open")
    if current_finding_reviews(record):
        raise ValueError(
            "the current finding batch requires a repair attempt before another review"
        )
    cycle = {
        "review_id": f"review-{len(record.get('review_cycles', [])) + 1:03d}",
        "revision": record["revision"],
        "attempt_id": record["attempt_id"],
        "reviewer": reviewer,
        "candidate": candidate_identity(root, record),
        "started_at": utc_now(),
        "closed_at": None,
        "duration_seconds": None,
        "status": "open",
        "outcome": None,
        "summary": None,
        "findings": [],
    }
    record.setdefault("review_cycles", []).append(cycle)
    write_json(path, record)
    return cycle


def record_finding(
    root: Path,
    run_id: str,
    *,
    review_id: str,
    severity: str,
    title: str,
    criterion: str,
    reproduction: str,
    minimum_repair: str,
    emergency_boundary: str | None = None,
) -> dict[str, Any]:
    if severity not in FINDING_SEVERITIES:
        raise ValueError(f"invalid finding severity: {severity}")
    if emergency_boundary is not None and emergency_boundary not in EMERGENCY_BOUNDARIES:
        raise ValueError(f"invalid emergency boundary: {emergency_boundary}")
    if emergency_boundary and severity != "critical":
        raise ValueError("emergency findings must have critical severity")
    values = (title, reproduction, minimum_repair)
    if not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError("finding title, reproduction, and minimum repair are required")
    path, record = load_run(root, run_id)
    if criterion not in criterion_ids(record):
        raise ValueError(f"finding references unknown criterion: {criterion}")
    cycle = open_review_cycle(record)
    if not cycle or cycle.get("review_id") != review_id:
        raise ValueError(f"review cycle is not open: {review_id}")
    current = candidate_identity(root, record)
    if current != cycle.get("candidate") and not emergency_boundary:
        raise ValueError("review candidate changed before finding collection closed")
    fingerprint_payload = {
        "severity": severity,
        "title": title.strip(),
        "criterion": criterion,
        "reproduction": reproduction.strip(),
        "minimum_repair": minimum_repair.strip(),
        "emergency_boundary": emergency_boundary,
    }
    fingerprint = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    if any(item.get("fingerprint") == fingerprint for item in cycle["findings"]):
        raise ValueError("duplicate review finding")
    cycle["findings"].append(
        {
            "finding_id": f"{review_id}-finding-{len(cycle['findings']) + 1:03d}",
            **fingerprint_payload,
            "fingerprint": fingerprint,
            "recorded_at": utc_now(),
        }
    )
    write_json(path, record)
    return cycle


def close_review(
    root: Path,
    run_id: str,
    *,
    review_id: str,
    outcome: str,
    summary: str,
) -> dict[str, Any]:
    if outcome not in REVIEW_OUTCOMES:
        raise ValueError(f"invalid review outcome: {outcome}")
    if not summary.strip():
        raise ValueError("review summary is required")
    path, record = load_run(root, run_id)
    cycle = open_review_cycle(record)
    if not cycle or cycle.get("review_id") != review_id:
        raise ValueError(f"review cycle is not open: {review_id}")
    findings = cycle.get("findings", [])
    if outcome == "clean" and findings:
        raise ValueError("a clean review cannot contain findings")
    if outcome == "batch-ready" and not findings:
        raise ValueError("a batch-ready review requires at least one finding")
    has_emergency = any(
        item.get("severity") == "critical" and item.get("emergency_boundary") for item in findings
    )
    if has_emergency and outcome != "emergency-stop":
        raise ValueError("a critical emergency finding requires an emergency stop")
    if outcome == "emergency-stop" and not has_emergency:
        raise ValueError("emergency stop requires a critical emergency finding")
    closing_candidate = candidate_identity(root, record)
    if outcome != "emergency-stop" and closing_candidate != cycle.get("candidate"):
        raise ValueError("review candidate changed before finding collection closed")
    closed_at = utc_now()
    started = datetime.fromisoformat(cycle["started_at"].replace("Z", "+00:00"))
    closed = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
    cycle.update(
        {
            "closed_at": closed_at,
            "duration_seconds": max(0.0, (closed - started).total_seconds()),
            "status": "closed",
            "outcome": outcome,
            "summary": summary.strip(),
            "closing_candidate": closing_candidate,
            "candidate_changed": closing_candidate != cycle.get("candidate"),
        }
    )
    write_json(path, record)
    return cycle


def record_release_impact(
    root: Path,
    run_id: str,
    *,
    level: str,
    reason: str,
    public_contract_changes: Iterable[str] = (),
) -> dict[str, Any]:
    if level not in RELEASE_IMPACTS:
        raise ValueError(f"invalid release impact: {level}")
    if not reason.strip():
        raise ValueError("release impact reason is required")
    path, record = load_run(root, run_id)
    record["release_impact"] = {
        "revision": record["revision"],
        "attempt_id": record["attempt_id"],
        "level": level,
        "reason": reason,
        "public_contract_changes": list(dict.fromkeys(public_contract_changes)),
        "recorded_at": utc_now(),
    }
    write_json(path, record)
    return record


def record_verdict(
    root: Path,
    run_id: str,
    *,
    reviewer: str,
    verdict: str,
    criteria: Iterable[str],
    evidence: str,
) -> dict[str, Any]:
    if verdict not in VERDICTS:
        raise ValueError(f"invalid verifier verdict: {verdict}")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer identity is required")
    if not evidence.strip():
        raise ValueError("verifier evidence is required")
    path, record = load_run(root, run_id)
    if record.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(
            f"verifier verdicts require a loop run created with schema {RUN_SCHEMA_VERSION}"
        )
    if reviewer in record.get("implementers", []):
        raise ValueError(f"reviewer {reviewer!r} is recorded as an implementer")
    reviews = current_closed_reviews(record)
    if not reviews:
        raise ValueError("verifier verdict requires a closed review cycle for the current attempt")
    latest_review = reviews[-1]
    if latest_review.get("reviewer") != reviewer:
        raise ValueError("verdict reviewer must own the latest closed review cycle")
    if latest_review.get("closing_candidate") != candidate_identity(root, record):
        raise ValueError("closed review cycle is stale for the current candidate")
    expected_outcome = "clean" if verdict == "approve" else None
    if expected_outcome and latest_review.get("outcome") != expected_outcome:
        raise ValueError("approval requires a clean closed review cycle")
    if verdict in {"revise", "reject"} and latest_review.get("outcome") not in {
        "batch-ready",
        "emergency-stop",
    }:
        raise ValueError(f"{verdict} verdict requires a finding batch or emergency stop")
    covered = set(criteria)
    unknown = sorted(covered - criterion_ids(record))
    if unknown:
        raise ValueError(f"verdict references unknown criteria: {', '.join(unknown)}")
    if verdict == "approve":
        if current_finding_reviews(record):
            raise ValueError("approval cannot supersede a finding batch in the current attempt")
        active = active_criterion_ids(record)
        missing_coverage = sorted(active - covered)
        if missing_coverage:
            raise ValueError(f"approval omits active criteria: {', '.join(missing_coverage)}")
        current_candidate = candidate_identity(root, record)
        missing_evidence = sorted(
            active - current_passed_criteria(record, current_candidate)
        )
        if missing_evidence:
            raise ValueError(
                f"approval lacks passed check evidence for criteria: {', '.join(missing_evidence)}"
            )
    record["verdicts"].append(
        {
            "verdict_id": f"verdict-{len(record['verdicts']) + 1:03d}",
            "revision": record["revision"],
            "attempt_id": record["attempt_id"],
            "reviewer": reviewer,
            "review_id": latest_review["review_id"],
            "decision": verdict,
            "criterion_ids": sorted(covered),
            "evidence": evidence,
            "candidate": candidate_identity(root, record),
            "recorded_at": utc_now(),
        }
    )
    write_json(path, record)
    return record


def revise_run(
    root: Path,
    run_id: str,
    *,
    reason: str,
    objective: str | None = None,
    acceptance_criteria: list[dict[str, Any]] | None = None,
    declared_write_set: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("revision reason is required")
    path, record = load_run(root, run_id)
    if open_review_cycle(record):
        raise ValueError("cannot revise the contract while an independent review cycle is open")
    if record.get("state") == "blocked" and consecutive_failures(record) >= retry_limit(
        root, record
    ):
        raise ValueError("retry-exhausted runs must use reviewed resume instead of revise")
    proposed_objective = record["objective"]
    if objective is not None:
        if not objective.strip():
            raise ValueError("objective is required")
        proposed_objective = objective
    proposed_criteria = (
        acceptance_criteria
        if acceptance_criteria is not None
        else [{**criterion, "waiver": None} for criterion in record["acceptance_criteria"]]
    )
    proposed_write_set = (
        declared_write_set
        if declared_write_set is not None
        else record["declared_write_set"]
    )
    if (
        proposed_objective == record["objective"]
        and proposed_criteria == record["acceptance_criteria"]
        and proposed_write_set == record["declared_write_set"]
    ):
        raise ValueError("contract revision must change the objective, criteria, or write scope")
    require_finding_repair_transition(root, record)
    record["revision_history"].append(
        {
            "revision": record["revision"],
            "objective": record["objective"],
            "acceptance_criteria": record["acceptance_criteria"],
            "declared_write_set": record["declared_write_set"],
            "superseded_at": utc_now(),
            "reason": reason,
        }
    )
    record["revision"] += 1
    record["attempt_id"] = 1
    record["objective"] = proposed_objective
    record["acceptance_criteria"] = proposed_criteria
    record["declared_write_set"] = proposed_write_set
    write_json(path, record)
    return record


def configured_retry_limit(root: Path) -> int:
    path = root / "harness/loops/engineering-loop.yaml"
    loop = load_json(path) if path.is_file() else {}
    value = loop.get("retry_policy", {}).get(
        "maximum_consecutive_failures", DEFAULT_MAXIMUM_CONSECUTIVE_FAILURES
    )
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("maximum_consecutive_failures must be a positive integer")
    return value


def retry_limit(root: Path, record: dict[str, Any]) -> int:
    value = record.get("retry_policy", {}).get("maximum_consecutive_failures")
    if value is None:
        value = configured_retry_limit(root)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("recorded maximum_consecutive_failures must be a positive integer")
    return value


def consecutive_failures(record: dict[str, Any]) -> int:
    revision = record.get("revision")
    count = 0
    for attempt in reversed(record.get("attempt_history", [])):
        if attempt.get("revision") != revision or attempt.get("outcome") != "failed":
            break
        count += 1
    return count


def new_attempt(root: Path, run_id: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("attempt reason is required")
    path, record = load_run(root, run_id)
    if open_review_cycle(record):
        raise ValueError("cannot start a new attempt while an independent review cycle is open")
    if record.get("state") in FINAL_STATES:
        raise ValueError(f"cannot retry a terminal run in state {record.get('state')}")
    require_finding_repair_transition(root, record)
    record["attempt_history"].append(
        {
            "revision": record["revision"],
            "attempt_id": record["attempt_id"],
            "ended_at": utc_now(),
            "reason": reason,
            "outcome": "failed",
        }
    )
    failures = consecutive_failures(record)
    limit = retry_limit(root, record)
    if failures >= limit:
        record["state"] = "blocked"
        record.setdefault("telemetry", {})["retry_exhaustion"] = {
            "revision": record["revision"],
            "attempt_id": record["attempt_id"],
            "consecutive_failures": failures,
            "limit": limit,
            "recorded_at": utc_now(),
        }
        write_json(path, record)
        raise RuntimeError(
            f"retry ceiling reached after {failures} consecutive failures; "
            "run is blocked and requires an explicit reviewed handoff"
        )
    record["attempt_id"] += 1
    write_json(path, record)
    return record


def validate_resume_handoff(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["resume handoff must be an object"]
    required = ("schema_version", "summary", "failure_boundary", "preserved_paths", "next_action")
    for key in required:
        if key not in data:
            errors.append(f"resume handoff is missing {key}")
    if data.get("schema_version") != RESUME_HANDOFF_SCHEMA_VERSION:
        errors.append(f"resume handoff schema_version must be {RESUME_HANDOFF_SCHEMA_VERSION}")
    for key in ("summary", "failure_boundary", "next_action"):
        if not isinstance(data.get(key), str) or not data.get(key, "").strip():
            errors.append(f"resume handoff {key} must be a non-empty string")
    preserved = data.get("preserved_paths")
    if not isinstance(preserved, list) or not all(
        isinstance(item, str) and item.strip() for item in preserved
    ):
        errors.append("resume handoff preserved_paths must be a string list")
    else:
        if len(preserved) != len(set(preserved)):
            errors.append("resume handoff preserved_paths must be unique")
        for item in preserved:
            try:
                normalize_repository_path(item, kind="preserved path")
            except ValueError as exc:
                errors.append(str(exc))
    forbidden = {"transcript", "prompt", "hidden_reasoning", "secret", "token"}
    if forbidden.intersection(data):
        errors.append("resume handoff contains a forbidden transcript, reasoning, or secret field")
    unexpected = sorted(set(data) - set(required))
    if unexpected:
        errors.append(f"resume handoff contains unexpected fields: {', '.join(unexpected)}")
    return errors


def resume_run(
    root: Path,
    run_id: str,
    *,
    handoff: dict[str, Any],
    authorized_by: str,
) -> dict[str, Any]:
    authorized_by = authorized_by.strip()
    if not authorized_by.startswith("human:") or not authorized_by.removeprefix("human:").strip():
        raise ValueError("retry-exhausted resume requires --by human:IDENTITY")
    errors = validate_resume_handoff(handoff)
    if errors:
        raise ValueError("; ".join(errors))
    path, record = load_run(root, run_id)
    if record.get("state") != "blocked" or consecutive_failures(record) < retry_limit(root, record):
        raise ValueError("only a retry-exhausted blocked run can be resumed")

    record["revision_history"].append(
        {
            "revision": record["revision"],
            "objective": record["objective"],
            "acceptance_criteria": record["acceptance_criteria"],
            "declared_write_set": record["declared_write_set"],
            "superseded_at": utc_now(),
            "reason": f"human-authorized recovery: {handoff['summary'].strip()}",
        }
    )
    record["revision"] += 1
    record["attempt_id"] = 1
    record["state"] = "understand"
    record["finished_at"] = None
    record["end_commit"] = None
    record["agent_handoffs"].append(
        {
            **handoff,
            "authorized_by": authorized_by,
            "recorded_at": utc_now(),
            "resume_revision": record["revision"],
        }
    )
    write_json(path, record)
    return record


def recovery_status(root: Path, run_id: str, integration_ref: str | None = None) -> dict[str, Any]:
    _, record = load_run(root, run_id)
    current = current_commit(root)
    scope = scope_evidence(root, record)
    status: dict[str, Any] = {
        "run_id": run_id,
        "state": record.get("state"),
        "revision": record.get("revision"),
        "attempt_id": record.get("attempt_id"),
        "consecutive_failures": consecutive_failures(record),
        "retry_limit": retry_limit(root, record),
        "baseline_relative_changes_present": bool(scope["delta"]),
        "changed_paths": [item["path"] for item in scope["delta"]],
        "scope_violations": scope["violations"],
        "integration_ref": integration_ref,
        "integration_ref_commit": None,
        "branch_stale": None,
    }
    if integration_ref:
        ref_commit = git_text(root, "rev-parse", "--verify", integration_ref)
        if not ref_commit:
            raise ValueError(f"integration ref does not exist: {integration_ref}")
        ancestry = git(root, "merge-base", "--is-ancestor", ref_commit, current, check=False)
        if ancestry.returncode not in (0, 1):
            raise RuntimeError(ancestry.stderr.strip() or "could not compare integration ancestry")
        status["integration_ref_commit"] = ref_commit
        status["branch_stale"] = ancestry.returncode == 1
    return status


def waive_criterion(
    root: Path, run_id: str, criterion_id: str, *, waived_by: str, reason: str
) -> dict[str, Any]:
    waived_by = waived_by.strip()
    if not waived_by.startswith("human:") or not waived_by.removeprefix("human:").strip():
        raise ValueError("criterion waivers require --by human:IDENTITY")
    if not reason.strip():
        raise ValueError("criterion waiver reason is required")
    path, record = load_run(root, run_id)
    for criterion in record.get("acceptance_criteria", []):
        if criterion["id"] == criterion_id:
            criterion["waiver"] = {
                "by": waived_by,
                "reason": reason,
                "revision": record["revision"],
                "recorded_at": utc_now(),
            }
            write_json(path, record)
            return record
    raise ValueError(f"unknown acceptance criterion: {criterion_id}")


def add_item(root: Path, run_id: str, collection: str, value: Any) -> dict[str, Any]:
    path, record = load_run(root, run_id)
    record[collection].append(value)
    write_json(path, record)
    return record


def set_state(root: Path, run_id: str, state: str) -> dict[str, Any]:
    loop = load_json(root / "harness/loops/engineering-loop.yaml")
    valid = {item["id"] for item in loop["states"]} | set(loop["terminal_states"])
    if state not in valid:
        raise ValueError(f"unknown loop state: {state}")
    path, record = load_run(root, run_id)
    if record.get("state") in FINAL_STATES and state != record.get("state"):
        raise ValueError(
            f"cannot leave terminal state {record.get('state')} with set-state; use reviewed recovery"
        )
    record["state"] = state
    write_json(path, record)
    return record


def collect_git_evidence(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    end_commit = current_commit(root)
    status = git_text(root, "status", "--short")
    scope = scope_evidence(root, record)
    evidence: dict[str, Any] = {
        "start_commit": record["start_commit"],
        "end_commit": end_commit,
        "branch": git_text(root, "branch", "--show-current") or "DETACHED_OR_UNBORN",
        "working_tree_status": status.splitlines() if status else [],
        "commits": [],
        "diff_stat": "",
        "changed_paths": [item["path"] for item in scope["delta"]],
        "scope": scope,
    }
    if record["start_commit"] != "UNBORN":
        commit_log = git_text(
            root, "log", "--format=%H%x09%s", f"{record['start_commit']}..{end_commit}"
        )
        evidence["commits"] = commit_log.splitlines() if commit_log else []
        evidence["diff_stat"] = git_text(root, "diff", "--stat", record["start_commit"])
    return evidence


def completion_errors(root: Path, record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    project_path = root / "harness/project.yaml"
    if project_path.is_file():
        project = load_json(project_path).get("project", {})
        if project.get("lifecycle") == "adopt" and project.get("status") != "active":
            errors.append(
                "harness project is provisional; resolve adoption gaps and essential intake "
                "context before reported completion"
            )
    criteria = record.get("acceptance_criteria", [])
    if not criteria:
        errors.append("run has no acceptance criteria")
    active = active_criterion_ids(record)
    current_candidate = candidate_identity(root, record)
    missing_checks = sorted(active - current_passed_criteria(record, current_candidate))
    if missing_checks:
        errors.append(f"criteria lack current passed checks: {', '.join(missing_checks)}")
    current_checks = [
        item
        for item in record.get("checks", [])
        if item.get("revision") == record.get("revision")
        and item.get("attempt_id") == record.get("attempt_id")
    ]
    full_checks = [item for item in current_checks if item.get("tier") == "full"]
    if len(full_checks) != 1:
        errors.append("reported completion requires exactly one current-attempt full gate")
    elif (
        full_checks[0].get("status") != "passed"
        or full_checks[0].get("evidence_origin") != "executed"
    ):
        errors.append("the current-attempt full gate must be executed and passed")
    elif full_checks[0].get("candidate") != current_candidate:
        errors.append("the current-attempt full gate is stale for the current candidate")
    if open_review_cycle(record):
        errors.append("an independent review cycle is still open")
    if current_finding_reviews(record):
        errors.append("the current attempt has an unresolved finding batch")
    scope = scope_evidence(root, record)
    if scope["violations"]:
        errors.append(f"writes outside declared scope: {', '.join(scope['violations'])}")
    release_impact = record.get("release_impact")
    if not release_impact:
        errors.append("product release impact is not assessed")
    elif release_impact.get("revision") != record.get("revision") or release_impact.get(
        "attempt_id"
    ) != record.get("attempt_id"):
        errors.append("product release impact is stale for the current revision and attempt")
    current_verdicts = [
        item
        for item in record.get("verdicts", [])
        if item.get("revision") == record.get("revision")
        and item.get("attempt_id") == record.get("attempt_id")
    ]
    if not current_verdicts:
        errors.append("no verifier verdict exists for the current revision and attempt")
    else:
        latest = current_verdicts[-1]
        current_reviews = current_closed_reviews(record)
        latest_review = current_reviews[-1] if current_reviews else None
        if latest.get("decision") != "approve":
            errors.append(f"latest verifier verdict is {latest.get('decision')}, not approve")
        missing_coverage = sorted(active - set(latest.get("criterion_ids", [])))
        if missing_coverage:
            errors.append(f"verifier verdict omits criteria: {', '.join(missing_coverage)}")
        if latest.get("candidate") != current_candidate:
            errors.append("verifier verdict is stale for the current commit or working tree")
        if not latest_review:
            errors.append("no closed independent review exists for the current attempt")
        elif latest_review.get("outcome") != "clean":
            errors.append("latest independent review is not clean")
        elif latest_review.get("closing_candidate") != current_candidate:
            errors.append("latest independent review is stale for the current candidate")
        elif latest.get("review_id") != latest_review.get("review_id"):
            errors.append("verifier approval does not reference the latest independent review")
    return errors


def markdown_report(
    record: dict[str, Any], evidence: dict[str, Any], current_candidate: dict[str, str]
) -> str:
    checks = record.get("checks", [])
    passed = sum(item.get("status") == "passed" for item in checks)
    failed = sum(item.get("status") == "failed" for item in checks)
    changed = evidence.get("changed_paths", [])
    status = evidence.get("working_tree_status", [])
    latest_verdict = record.get("verdicts", [])[-1] if record.get("verdicts") else None
    current_passed = current_passed_criteria(record, current_candidate)

    def list_or_none(values: list[Any], formatter: Callable[[Any], str] = str) -> str:
        if not values:
            return "- None recorded."
        return "\n".join(f"- {formatter(value)}" for value in values)

    check_rows = (
        "\n".join(
            f"| {item.get('check_id', '')} | {item.get('name', '')} | {item.get('tier', 'legacy')} | "
            f"{item.get('duration_seconds', 0):.3f} | {item.get('evidence_origin', 'legacy')} | "
            f"{item.get('status', '')} | "
            f"{', '.join(item.get('criterion_ids', [])) or 'None'} | {item.get('command', '')} | "
            f"{item.get('evidence', '')} |"
            for item in checks
        )
        or "| None | None recorded | legacy | 0.000 | legacy | not-run | None |  | No check boundary recorded |"
    )
    tier_totals = {
        tier: sum(
            float(item.get("duration_seconds", 0)) for item in checks if item.get("tier") == tier
        )
        for tier in CHECK_TIERS
    }
    review_cycles = record.get("review_cycles", [])
    closed_reviews = [item for item in review_cycles if item.get("status") == "closed"]
    review_seconds = sum(float(item.get("duration_seconds") or 0) for item in closed_reviews)
    finding_count = sum(len(item.get("findings", [])) for item in review_cycles)
    reused_checks = sum(item.get("evidence_origin") == "reused" for item in checks)
    repeated_attempts = len(record.get("attempt_history", []))
    review_outcomes = {
        outcome: sum(item.get("outcome") == outcome for item in closed_reviews)
        for outcome in REVIEW_OUTCOMES
    }
    finding_batches = review_outcomes["batch-ready"]
    revision_history = list_or_none(
        record.get("revision_history", []),
        lambda item: f"revision {item.get('revision')}: {item.get('reason', 'reason unavailable')}",
    )
    attempt_history = list_or_none(
        record.get("attempt_history", []),
        lambda item: (
            f"revision {item.get('revision')} attempt {item.get('attempt_id')}: "
            f"{item.get('reason', 'reason unavailable')}"
        ),
    )
    criterion_rows = (
        "\n".join(
            f"| {item['id']} | "
            f"{'waived' if item.get('waiver') and item['waiver'].get('revision') == record.get('revision') else ('check-passed' if item['id'] in current_passed else 'missing')} | "
            f"{item['text']} | "
            f"{item.get('waiver', {}).get('reason', '') if item.get('waiver') else ''} |"
            for item in record.get("acceptance_criteria", [])
        )
        or "| None | missing | No acceptance criteria recorded | |"
    )
    verdict_text = (
        f"{latest_verdict['decision']} by {latest_verdict['reviewer']} "
        f"for revision {latest_verdict['revision']}, attempt {latest_verdict['attempt_id']}, "
        f"candidate `{latest_verdict['candidate']['commit']}` / "
        f"`{latest_verdict['candidate']['tree_digest']}` / "
        f"impact `{latest_verdict['candidate']['release_impact_digest']}`"
        if latest_verdict
        else "None recorded"
    )
    handoffs = list_or_none(
        record.get("agent_handoffs", []),
        lambda item: json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item),
    )
    risks = list_or_none(record.get("risks", []))
    decisions = list_or_none(record.get("decisions", []))
    changed_text = list_or_none(changed)
    dirty_text = list_or_none(status)
    violation_text = list_or_none(evidence.get("scope", {}).get("violations", []))
    declared_scope_text = list_or_none(
        record.get("declared_write_set", []),
        lambda item: f"{item['mode']}: {item['path']}",
    )
    issue = record.get("issue") or "None"
    release_impact = record.get("release_impact")
    release_impact_text = (
        f"{release_impact['level']}: {release_impact['reason']}"
        if release_impact
        else "not assessed"
    )
    contract_changes = list_or_none(
        release_impact.get("public_contract_changes", []) if release_impact else []
    )

    return f"""# Engineering loop report: {record["run_id"]}

## Outcome and why it matters

- VERIFIED: Collected repository evidence from `{evidence["start_commit"]}` to `{evidence["end_commit"]}`.
- REPORTED: Objective was: {record["objective"]}
- VERIFIED: {len(changed)} baseline-relative changed paths, {passed} passed checks, and {failed} failed checks were recorded.

## Planned versus completed

- REPORTED: Governing Issue: {issue}.
- VERIFIED: Final loop state: {record["state"]}.
- VERIFIED: Run revision {record.get("revision", "legacy")}, attempt {record.get("attempt_id", "legacy")}.
- INFERRED: Completion is limited to the repository and check boundaries listed below.

## Acceptance evidence matrix

| Criterion | Status | Accepted boundary | Waiver reason |
|---|---|---|---|
{criterion_rows}

## User-visible and semantic changes

No user-visible claim is generated automatically. Add one only after inspecting the changed behavior and acceptance evidence.

- VERIFIED: Recommended product release impact: {release_impact_text}

Declared public-contract changes:

{contract_changes}

## Architecture, schema, dependency, data, and interface changes

Review the exact baseline-relative changed paths below; no architecture impact is inferred from filenames alone.

{changed_text}

## Verification evidence

Latest verifier verdict: {verdict_text}.

Efficiency telemetry: {len(review_cycles)} review cycle(s), {review_seconds:.3f}s closed-review time, {finding_batches} finding batch(es), {finding_count} finding(s), {repeated_attempts} superseded attempt(s), and {reused_checks} reused check(s).

Review outcomes: {json.dumps(review_outcomes, sort_keys=True)}

Contract revision history:

{revision_history}

Implementation attempt history:

{attempt_history}

Check-tier time: {json.dumps(tier_totals, sort_keys=True)}

| Check ID | Check | Tier | Seconds | Evidence origin | Result | Criteria | Exact command | Boundary proven |
|---|---|---|---:|---|---|---|---|---|
{check_rows}

## GitHub and release state

- REPORTED: Governing Issue: {issue}.
- INFERRED: No live GitHub, deployment, or release state is claimed unless separately recorded in a handoff.

## Risks, limitations, and unverified claims

{risks}

Writes outside the declared scope:

{violation_text}

Working-tree state at report time:

{dirty_text}

## Decisions and authorization needed

{decisions}

## Recommended next loop

Review failed or missing criteria, stale or absent verification, scope violations, residual risks, and the governing Issue before selecting the next bounded slice.

## Exact revision and scope

- Start commit: `{evidence["start_commit"]}`
- End commit: `{evidence["end_commit"]}`
- Branch: `{evidence["branch"]}`
- Dirty-baseline entries: {len(evidence.get("scope", {}).get("baseline", []))}

Declared write set:

{declared_scope_text}

```text
{evidence.get("diff_stat") or "No tracked diff statistics available."}
```

## Agent handoffs

{handoffs}
"""


def finish_run(root: Path, run_id: str, state: str) -> tuple[Path, Path, dict[str, Any]]:
    path, record = load_run(root, run_id)
    if state == "reported":
        errors = completion_errors(root, record)
        if errors:
            raise ValueError("completion gate failed: " + "; ".join(errors))
    evidence = collect_git_evidence(root, record)
    record["state"] = state
    record["finished_at"] = utc_now()
    record["end_commit"] = evidence["end_commit"]
    write_json(path, record)
    run_dir = path.parent
    evidence_path = run_dir / "evidence.json"
    report_path = run_dir / "report.md"
    write_json(
        evidence_path,
        {
            "schema_version": record.get("schema_version", RUN_SCHEMA_VERSION),
            "run_id": run_id,
            "revision": record.get("revision"),
            "attempt_id": record.get("attempt_id"),
            "boundary": evidence,
            "acceptance_criteria": record.get("acceptance_criteria", []),
            "claims": [
                {
                    "status": "verified",
                    "claim": "Repository boundary collected",
                    "evidence": str(evidence_path),
                }
            ],
            "checks": record["checks"],
            "review_cycles": record.get("review_cycles", []),
            "verdicts": record.get("verdicts", []),
            "release_impact": record.get("release_impact"),
            "risks": record["risks"],
        },
    )
    report_path.write_text(
        markdown_report(record, evidence, candidate_identity(root, record)), encoding="utf-8"
    )
    return report_path, evidence_path, record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    subparsers = parser.add_subparsers(dest="action", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--objective", required=True)
    start.add_argument("--issue")
    start.add_argument("--run-id")
    start.add_argument("--criterion", action="append", required=True, metavar="ID=TEXT")
    start.add_argument("--write-path", action="append", default=[])
    start.add_argument("--write-prefix", action="append", default=[])
    start.add_argument("--implementer", action="append", required=True)

    migrate = subparsers.add_parser("migrate-run")
    migrate.add_argument("--run", required=True)

    check = subparsers.add_parser("record-check")
    check.add_argument("--run", required=True)
    check.add_argument("--name", required=True)
    check.add_argument("--command", dest="command_text", required=True)
    check.add_argument("--status", choices=CHECK_STATUSES, required=True)
    check.add_argument("--evidence", required=True)
    check.add_argument("--criterion", action="append", default=[])
    check.add_argument("--tier", choices=CHECK_TIERS, default="targeted")
    check.add_argument("--duration-seconds", type=float, default=0.0)
    check.add_argument("--evidence-origin", choices=EVIDENCE_ORIGINS, default="executed")
    check.add_argument("--reuse-source")
    check.add_argument("--artifact-digest")
    check.add_argument("--applicability")

    review_start = subparsers.add_parser("start-review")
    review_start.add_argument("--run", required=True)
    review_start.add_argument("--reviewer", required=True)

    finding = subparsers.add_parser("record-finding")
    finding.add_argument("--run", required=True)
    finding.add_argument("--review", required=True)
    finding.add_argument("--severity", choices=FINDING_SEVERITIES, required=True)
    finding.add_argument("--title", required=True)
    finding.add_argument("--criterion", required=True)
    finding.add_argument("--reproduction", required=True)
    finding.add_argument("--minimum-repair", required=True)
    finding.add_argument("--emergency-boundary", choices=EMERGENCY_BOUNDARIES)

    review_close = subparsers.add_parser("close-review")
    review_close.add_argument("--run", required=True)
    review_close.add_argument("--review", required=True)
    review_close.add_argument("--outcome", choices=REVIEW_OUTCOMES, required=True)
    review_close.add_argument("--summary", required=True)

    release_impact = subparsers.add_parser("record-release-impact")
    release_impact.add_argument("--run", required=True)
    release_impact.add_argument("--level", choices=RELEASE_IMPACTS, required=True)
    release_impact.add_argument("--reason", required=True)
    release_impact.add_argument("--public-contract-change", action="append", default=[])

    verdict = subparsers.add_parser("record-verdict")
    verdict.add_argument("--run", required=True)
    verdict.add_argument("--reviewer", required=True)
    verdict.add_argument("--verdict", choices=VERDICTS, required=True)
    verdict.add_argument("--criterion", action="append", default=[])
    verdict.add_argument("--evidence", required=True)

    revise = subparsers.add_parser("revise")
    revise.add_argument("--run", required=True)
    revise.add_argument("--reason", required=True)
    revise.add_argument("--objective")
    revise.add_argument("--criterion", action="append")
    revise.add_argument("--write-path", action="append")
    revise.add_argument("--write-prefix", action="append")

    attempt = subparsers.add_parser("new-attempt")
    attempt.add_argument("--run", required=True)
    attempt.add_argument("--reason", required=True)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--run", required=True)
    resume.add_argument("--handoff", type=Path, required=True)
    resume.add_argument("--by", required=True)

    recovery = subparsers.add_parser("recovery-status")
    recovery.add_argument("--run", required=True)
    recovery.add_argument("--integration-ref")

    waiver = subparsers.add_parser("waive-criterion")
    waiver.add_argument("--run", required=True)
    waiver.add_argument("--criterion", required=True)
    waiver.add_argument("--by", required=True)
    waiver.add_argument("--reason", required=True)

    handoff = subparsers.add_parser("record-handoff")
    handoff.add_argument("--run", required=True)
    handoff.add_argument("--file", type=Path, required=True)

    for name in ("record-risk", "record-decision"):
        item = subparsers.add_parser(name)
        item.add_argument("--run", required=True)
        item.add_argument("--text", required=True)

    state_parser = subparsers.add_parser("set-state")
    state_parser.add_argument("--run", required=True)
    state_parser.add_argument("--state", required=True)

    finish = subparsers.add_parser("finish")
    finish.add_argument("--run", required=True)
    finish.add_argument("--state", choices=FINAL_STATES, default="reported")

    args = parser.parse_args()
    root = args.root.resolve() if args.root else repository_root(Path(__file__).parent)
    try:
        if args.action == "start":
            record = start_run(
                root,
                args.objective,
                args.issue,
                args.run_id,
                acceptance_criteria=parse_criteria(args.criterion),
                declared_write_set=make_write_set(args.write_path, args.write_prefix),
                implementers=args.implementer,
            )
            print(record["run_id"])
        elif args.action == "migrate-run":
            record = migrate_run(root, args.run)
            print(f"migrated {args.run} to schema {record['schema_version']}")
        elif args.action == "record-check":
            record_check(
                root,
                args.run,
                name=args.name,
                command=args.command_text,
                status=args.status,
                evidence=args.evidence,
                criteria=args.criterion,
                tier=args.tier,
                duration_seconds=args.duration_seconds,
                evidence_origin=args.evidence_origin,
                reuse_source=args.reuse_source,
                artifact_digest=args.artifact_digest,
                applicability=args.applicability,
            )
            print(f"recorded check for {args.run}")
        elif args.action == "start-review":
            cycle = start_review(root, args.run, reviewer=args.reviewer)
            print(cycle["review_id"])
        elif args.action == "record-finding":
            record_finding(
                root,
                args.run,
                review_id=args.review,
                severity=args.severity,
                title=args.title,
                criterion=args.criterion,
                reproduction=args.reproduction,
                minimum_repair=args.minimum_repair,
                emergency_boundary=args.emergency_boundary,
            )
            print(f"recorded finding for {args.review}")
        elif args.action == "close-review":
            close_review(
                root,
                args.run,
                review_id=args.review,
                outcome=args.outcome,
                summary=args.summary,
            )
            print(f"closed {args.review} as {args.outcome}")
        elif args.action == "record-release-impact":
            record_release_impact(
                root,
                args.run,
                level=args.level,
                reason=args.reason,
                public_contract_changes=args.public_contract_change,
            )
            print(f"recorded release impact for {args.run}")
        elif args.action == "record-verdict":
            record_verdict(
                root,
                args.run,
                reviewer=args.reviewer,
                verdict=args.verdict,
                criteria=args.criterion,
                evidence=args.evidence,
            )
            print(f"recorded verifier verdict for {args.run}")
        elif args.action == "revise":
            criteria = parse_criteria(args.criterion) if args.criterion is not None else None
            write_set = None
            if args.write_path is not None or args.write_prefix is not None:
                write_set = make_write_set(args.write_path or [], args.write_prefix or [])
            record = revise_run(
                root,
                args.run,
                reason=args.reason,
                objective=args.objective,
                acceptance_criteria=criteria,
                declared_write_set=write_set,
            )
            print(f"revised {args.run} to revision {record['revision']}")
        elif args.action == "new-attempt":
            record = new_attempt(root, args.run, args.reason)
            print(f"started attempt {record['attempt_id']} for {args.run}")
        elif args.action == "resume":
            record = resume_run(
                root,
                args.run,
                handoff=load_json(args.handoff),
                authorized_by=args.by,
            )
            print(f"resumed {args.run} at revision {record['revision']}")
        elif args.action == "recovery-status":
            print(json.dumps(recovery_status(root, args.run, args.integration_ref), indent=2))
        elif args.action == "waive-criterion":
            waive_criterion(
                root,
                args.run,
                args.criterion,
                waived_by=args.by,
                reason=args.reason,
            )
            print(f"waived {args.criterion} for {args.run}")
        elif args.action == "record-handoff":
            add_item(root, args.run, "agent_handoffs", load_json(args.file))
            print(f"recorded handoff for {args.run}")
        elif args.action == "record-risk":
            add_item(root, args.run, "risks", args.text)
            print(f"recorded risk for {args.run}")
        elif args.action == "record-decision":
            add_item(root, args.run, "decisions", args.text)
            print(f"recorded decision for {args.run}")
        elif args.action == "set-state":
            set_state(root, args.run, args.state)
            print(f"set {args.run} to {args.state}")
        elif args.action == "finish":
            report, evidence, _ = finish_run(root, args.run, args.state)
            print(f"report: {report}")
            print(f"evidence: {evidence}")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
