from __future__ import annotations

import copy
import io
import json
import math
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

from harness.runtime.model_stress_runner import (
    RESOURCE_PATHS,
    RunnerError,
    RunnerExecutionError,
    _changed_paths,
    _load_resource_bundle,
    _parse_events,
    _run_model_lane,
    _run_oracle,
    _sanitized_event_metrics,
    _snapshot,
    _write_initial_repository,
    build_pi_command,
    load_task,
    pi_version,
    run_paired,
    safe_output_path,
    validate_result,
    validate_task,
    validate_trials,
)

ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = ROOT / "harness/model-stress/tasks/identifier-canonicalization-v1.json"


def valid_result() -> dict[str, Any]:
    trial = {
        "returncode": 0,
        "settled": True,
        "timed_out": False,
        "event_limit_ok": True,
        "elapsed_seconds": 1.0,
        "changed_paths": ["identifier.py"],
        "scope_result": {"ok": True, "allowed_paths": ["identifier.py"]},
        "tool_errors": [],
        "usage": {
            "measurement_origin": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
        },
        "trial": 1,
        "test_result": {
            "ok": False,
            "passed": 6,
            "failed_case_ids": ["runs"],
            "elapsed_seconds": 0.1,
            "timed_out": False,
        },
    }
    return {
        "schema_version": "1.0",
        "authority": "supplemental",
        "evidence_level": "smoke",
        "accepted_baseline": False,
        "model_invoked": True,
        "provenance": {
            "model": "model",
            "provider": "provider",
            "pi_version": "1.2.3",
            "serving_runtime": "runtime",
            "serving_recipe": "recipe",
            "endpoint_class": "local-loopback-openai-compatible",
        },
        "task": {
            "id": "identifier-canonicalization-v1",
            "task_digest": "a" * 64,
            "prompt_digest": "b" * 64,
            "tool_set": ["read", "edit"],
            "oracle_case_count": 7,
            "oracle_case_ids": [
                "plain",
                "runs",
                "casefold",
                "unicode",
                "digits",
                "empty",
                "wrong-type",
            ],
            "resource_bundle_digest": "c" * 64,
            "writable_paths": ["identifier.py"],
        },
        "limits": {
            "model_timeout_seconds": 300,
            "oracle_timeout_seconds": 10,
            "maximum_event_bytes": 65536,
            "maximum_changed_files": 1,
            "maximum_output_tokens": 4096,
        },
        "trial_count": 1,
        "lanes": {
            "bare": {
                "passed_trials": 0,
                "total_trials": 1,
                "trials": [copy.deepcopy(trial)],
            },
            "harness": {
                "passed_trials": 0,
                "total_trials": 1,
                "trials": [copy.deepcopy(trial)],
            },
        },
        "comparison": {
            "bare_passed_trials": 0,
            "harness_passed_trials": 0,
            "observed_pass_difference": 0,
            "general_harness_lift_claim": False,
        },
    }


def bubblewrap_available() -> bool:
    if shutil.which("bwrap") is None:
        return False
    result = subprocess.run(
        [
            "bwrap",
            "--unshare-all",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "/usr/bin/true",
        ],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


class ModelStressRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = json.loads(TASK_PATH.read_text(encoding="utf-8"))

    def test_repository_task_is_valid_and_oracle_is_not_an_initial_file(self) -> None:
        task, digest = load_task(TASK_PATH)
        self.assertEqual([], validate_task(task))
        self.assertEqual(64, len(digest))
        visible = {item["path"] for item in task["initial_files"]}
        self.assertNotIn("oracle.json", visible)
        self.assertEqual(["identifier.py"], task["writable_paths"])

    def test_malformed_and_unsafe_tasks_fail_closed(self) -> None:
        mutations = []
        candidate = copy.deepcopy(self.task)
        candidate["unknown"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "../escape"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["writable_paths"] = ["missing.py"]
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["oracle"]["module"] = "pkg.module"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["oracle"]["cases"][0]["args"] = [[]]
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "AGENTS.md"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = ".gitattributes"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "nested/.git/config"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "AGENTS.md/child"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "bad\x00name.py"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["prompt"] = "bad\x00prompt"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["oracle"]["cases"][0]["expected"] = math.nan
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["initial_files"][0]["path"] = "a" * 158 + ".py"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.task)
        candidate["oracle"]["cases"][0]["id"] = "a" * 81
        mutations.append(candidate)
        for value in mutations:
            with self.subTest(value=value):
                self.assertTrue(validate_task(value))

    def test_duplicate_task_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "task.json"
            path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "duplicate JSON object key"):
                load_task(path)

    def test_task_loader_rejects_symlink_root_ancestor_and_outside_path(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            root = base / "root"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            task = outside / "task.json"
            shutil.copy2(TASK_PATH, task)

            root_link = base / "root-link"
            root_link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(RunnerError, "task root"):
                load_task(root_link / "task.json", root=root_link)

            (root / "nested").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RunnerError, "symlink|invalid path"):
                load_task(root / "nested/task.json", root=root)

            with self.assertRaisesRegex(RunnerError, "beneath the repository root"):
                load_task(task, root=root)

    def test_trial_levels_reject_ambiguous_two_trial_evidence(self) -> None:
        self.assertEqual("smoke", validate_trials(1))
        self.assertEqual("acceptance-candidate", validate_trials(3))
        for value in (0, 2, 11):
            with self.assertRaises(RunnerError):
                validate_trials(value)

    def test_output_is_confined_and_rejects_symlink_ancestors(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = safe_output_path(root, Path(".harness/model-stress/result.json"))
            self.assertEqual(root / ".harness/model-stress/result.json", path)
            with self.assertRaises((RunnerError, ValueError)):
                safe_output_path(root, Path("outside.json"))
            (root / ".harness").mkdir()
            outside = root / "outside"
            outside.mkdir()
            (root / ".harness/model-stress").symlink_to(outside)
            with self.assertRaises(RunnerError):
                safe_output_path(root, Path(".harness/model-stress/result.json"))

    def test_lane_commands_are_identical_except_harness_resources(self) -> None:
        common = {
            "repo": Path("/tmp/repo"),
            "config_home": Path("/tmp/home"),
            "pi_root": Path("/tmp/pi"),
            "provider": "local-vllm",
            "model": "model",
            "prompt": self.task["prompt"],
        }
        bare = build_pi_command(lane="bare", **common)
        harness = build_pi_command(lane="harness", **common)
        for command in (bare, harness):
            self.assertIn("read,edit", command)
            self.assertNotIn("bash", command)
            self.assertNotIn("write", command)
            self.assertIn("--no-session", command)
            self.assertIn("--offline", command)
            self.assertEqual(self.task["prompt"], command[-1])
        self.assertIn("--no-context-files", bare)
        self.assertNotIn("--no-context-files", harness)
        self.assertIn("--skill", harness)
        self.assertIn("--extension", harness)
        self.assertNotIn("--skill", bare)
        agent_mount = bare.index("/home/canary/.pi/agent")
        self.assertEqual("--ro-bind", bare[agent_mount - 2])

    def test_sanitized_metrics_never_retain_transcript_or_error_text(self) -> None:
        events = [
            {
                "type": "message_end",
                "message": {
                    "content": [{"type": "text", "text": "RAW_PRIVATE_TEXT"}],
                    "usage": {"input": 12, "output": 4, "cacheRead": 2, "cacheWrite": 1},
                },
            },
            {
                "type": "tool_execution_end",
                "toolName": "edit",
                "isError": True,
                "result": {"content": [{"type": "text", "text": "SECRET_ERROR_DETAIL"}]},
            },
            {"type": "agent_settled"},
        ]
        errors, usage, settled = _sanitized_event_metrics(events)
        rendered = json.dumps({"errors": errors, "usage": usage})
        self.assertNotIn("RAW_PRIVATE_TEXT", rendered)
        self.assertNotIn("SECRET_ERROR_DETAIL", rendered)
        self.assertEqual(
            [{"tool": "edit", "category": "tool-execution-error", "count": 1}],
            errors,
        )
        self.assertEqual(12, usage["input_tokens"])
        self.assertEqual("provider-reported", usage["measurement_origin"])
        self.assertTrue(settled)

        secret_name = "private-provider-tool-name"
        secret_errors, _, _ = _sanitized_event_metrics(
            [
                {
                    "type": "tool_execution_end",
                    "toolName": secret_name,
                    "isError": True,
                }
            ]
        )
        self.assertEqual(
            [{"tool": "unavailable", "category": "tool-execution-error", "count": 1}],
            secret_errors,
        )
        self.assertNotIn(secret_name, json.dumps(secret_errors))

        _, unavailable, _ = _sanitized_event_metrics([{"type": "agent_settled"}])
        self.assertEqual("unavailable", unavailable["measurement_origin"])
        self.assertIsNone(unavailable["input_tokens"])

    def test_result_validator_rejects_raw_content_and_self_approval(self) -> None:
        payload = valid_result()
        self.assertEqual([], validate_result(payload))
        payload["accepted_baseline"] = True
        self.assertTrue(validate_result(payload))
        payload = valid_result()
        payload["raw"] = {"transcript": "private"}
        self.assertTrue(validate_result(payload))

    def test_result_validator_rejects_inconsistent_shapes_and_relationships(self) -> None:
        mutations = []
        payload = valid_result()
        payload["provenance"]["endpoint_class"] = "local"
        mutations.append(payload)
        payload = valid_result()
        payload["task"]["task_digest"] = "not-a-digest"
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["settled"] = 1
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["scope_result"]["ok"] = False
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["tool_errors"] = [
            {"tool": "secret-tool", "category": "tool-execution-error", "count": 1}
        ]
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["usage"]["input_tokens"] = 0
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["test_result"]["passed"] = 7
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["test_result"]["failed_case_ids"] = ["invented-case"]
        mutations.append(payload)
        payload = valid_result()
        payload["lanes"]["bare"]["trials"][0]["scope_result"]["allowed_paths"] = ["other.py"]
        mutations.append(payload)
        payload = valid_result()
        payload["comparison"]["observed_pass_difference"] = 1
        mutations.append(payload)
        for value in mutations:
            with self.subTest(value=value):
                self.assertTrue(validate_result(value))

    def test_deep_event_json_is_discarded_without_recursion_failure(self) -> None:
        output = ('{"nested":' + "[" * 10000 + "0" + "]" * 10000 + "}\n").encode()
        events, within_limit = _parse_events(output, 65536)
        self.assertFalse(events)
        self.assertTrue(within_limit)
        duplicate_events, duplicate_within_limit = _parse_events(
            b'{"type":"agent_settled","type":"message_end"}\n', 65536
        )
        self.assertFalse(duplicate_events)
        self.assertTrue(duplicate_within_limit)

    def test_model_event_stream_is_bounded_while_subprocess_runs(self) -> None:
        task = copy.deepcopy(self.task)
        task["limits"]["maximum_event_bytes"] = 65536
        with tempfile.TemporaryDirectory() as name:
            repo = Path(name) / "repo"
            repo.mkdir()

            def fake_run(command, **kwargs):
                self.assertIs(subprocess.DEVNULL, kwargs["stderr"])
                self.assertIn("preexec_fn", kwargs)
                kwargs["stdout"].write(b"x" * 65536)
                return subprocess.CompletedProcess(command, -signal.SIGXFSZ)

            with patch("harness.runtime.model_stress_runner.subprocess.run", side_effect=fake_run):
                result = _run_model_lane(
                    lane="bare",
                    task=task,
                    repo=repo,
                    config_home=Path(name) / "home",
                    pi_root=Path(name) / "pi",
                    provider="provider",
                    model="model",
                )
        self.assertFalse(result["event_limit_ok"])
        self.assertEqual(-signal.SIGXFSZ, result["returncode"])

    def test_direct_snapshot_detects_scope_changes_without_git_filters(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "identifier.py").write_text("before", encoding="utf-8")
            (root / "TASK.md").write_text("task", encoding="utf-8")
            before = _snapshot(root)
            (root / "identifier.py").write_text("after", encoding="utf-8")
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git/config").write_text("changed metadata", encoding="utf-8")
            self.assertEqual(
                [".git/config", "extra.txt", "identifier.py"],
                _changed_paths(before, _snapshot(root)),
            )

    def test_frozen_resource_bundle_builds_identical_seed_clones(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source"
            for relative in RESOURCE_PATHS:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            resources, digest = _load_resource_bundle(source)
            seed = root / "seed"
            _write_initial_repository(self.task, seed, resources)
            seed_snapshot = _snapshot(seed)

            changed_resource = source / RESOURCE_PATHS[0]
            changed_resource.write_bytes(
                changed_resource.read_bytes() + b"\nchanged after freeze\n"
            )
            _, changed_digest = _load_resource_bundle(source)
            self.assertNotEqual(digest, changed_digest)

            for lane in ("bare", "harness"):
                clone = root / lane
                shutil.copytree(seed, clone, symlinks=True)
                self.assertEqual(seed_snapshot, _snapshot(clone))

    def test_resource_bundle_rejects_symlink_root_and_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            source = base / "source"
            outside = base / "outside"
            for relative in RESOURCE_PATHS:
                parent = outside if relative.startswith(".agents/") else source
                target = parent / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            (source / ".agents").symlink_to(outside / ".agents", target_is_directory=True)

            with self.assertRaisesRegex(RunnerError, "symlink|invalid path"):
                _load_resource_bundle(source)

            source_link = base / "source-link"
            source_link.symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(RunnerError, "resource root"):
                _load_resource_bundle(source_link)

    def test_run_paired_reuses_frozen_seed_after_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source"
            for relative in RESOURCE_PATHS:
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            _, original_digest = _load_resource_bundle(source)
            observed_snapshots: list[dict[str, str]] = []
            changed_resource = source / RESOURCE_PATHS[0]

            def fake_lane(**kwargs):
                observed_snapshots.append(_snapshot(kwargs["repo"]))
                if len(observed_snapshots) == 1:
                    changed_resource.write_bytes(
                        changed_resource.read_bytes() + b"\nchanged after first lane\n"
                    )
                return {
                    "returncode": 0,
                    "settled": True,
                    "timed_out": False,
                    "event_limit_ok": True,
                    "elapsed_seconds": 0.01,
                    "changed_paths": [],
                    "scope_result": {"ok": True, "allowed_paths": ["identifier.py"]},
                    "tool_errors": [],
                    "usage": {
                        "measurement_origin": "unavailable",
                        "input_tokens": None,
                        "output_tokens": None,
                        "cache_read_tokens": None,
                        "cache_write_tokens": None,
                    },
                }

            oracle = {
                "ok": False,
                "passed": 0,
                "failed_case_ids": [
                    record["id"]
                    for record in self.task["oracle"]["cases"] + self.task["oracle"]["raises"]
                ],
                "elapsed_seconds": 0.01,
                "timed_out": False,
            }
            with (
                patch("harness.runtime.model_stress_runner.shutil.which", return_value="bwrap"),
                patch("harness.runtime.model_stress_runner._pi_root", return_value=root / "pi"),
                patch("harness.runtime.model_stress_runner.pi_version", return_value="0.84.1"),
                patch(
                    "harness.runtime.model_stress_runner._run_model_lane",
                    side_effect=fake_lane,
                ),
                patch("harness.runtime.model_stress_runner._run_oracle", return_value=oracle),
            ):
                result = run_paired(
                    source_root=source,
                    task=self.task,
                    task_digest="a" * 64,
                    executable=root / "pi/bin/pi",
                    provider="local-vllm",
                    model="model",
                    base_url="http://127.0.0.1:8000/v1",
                    serving_runtime="runtime",
                    serving_recipe="recipe",
                    trials=3,
                )

            self.assertEqual(6, len(observed_snapshots))
            self.assertTrue(
                all(snapshot == observed_snapshots[0] for snapshot in observed_snapshots)
            )
            self.assertEqual(original_digest, result["task"]["resource_bundle_digest"])
            _, changed_digest = _load_resource_bundle(source)
            self.assertNotEqual(original_digest, changed_digest)

    def test_snapshot_rejects_oversized_model_output_without_loading_it(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            oversized = root / "oversized.py"
            with oversized.open("wb") as handle:
                handle.truncate(1024 * 1024 + 1)
            with self.assertRaises(RunnerError):
                _snapshot(root)

    @unittest.skipUnless(
        bubblewrap_available(), "unprivileged Bubblewrap unavailable in this test boundary"
    )
    def test_oracle_runs_in_networkless_bubblewrap(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            repo = Path(name) / "repo"
            resources, _ = _load_resource_bundle(ROOT)
            _write_initial_repository(self.task, repo, resources)
            bad = _run_oracle(self.task, repo)
            self.assertFalse(bad["ok"])
            (repo / "identifier.py").write_text(
                """def canonical_identifier(value):
    if not isinstance(value, str):
        raise TypeError
    result = []
    separator = False
    for character in value.casefold():
        if character.isalnum():
            if separator and result:
                result.append('-')
            result.append(character)
            separator = False
        else:
            separator = True
    if not result:
        raise ValueError
    return ''.join(result)
""",
                encoding="utf-8",
            )
            good = _run_oracle(self.task, repo)
            self.assertTrue(good["ok"], good)
            self.assertEqual(7, good["passed"])
            self.assertFalse(good["timed_out"])

    @unittest.skipUnless(
        bubblewrap_available(), "unprivileged Bubblewrap unavailable in this test boundary"
    )
    def test_oracle_does_not_expose_hidden_expectations_to_generated_code(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            repo = Path(name) / "repo"
            resources, _ = _load_resource_bundle(ROOT)
            _write_initial_repository(self.task, repo, resources)
            (repo / "identifier.py").write_text(
                """import os


def canonical_identifier(value):
    if 'HARNESS_ORACLE' in os.environ:
        return 'would-game-hidden-expectations'
    raise RuntimeError('hidden expectations unavailable')
""",
                encoding="utf-8",
            )
            result = _run_oracle(self.task, repo)
            self.assertFalse(result["ok"])
            self.assertEqual(0, result["passed"])
            self.assertEqual(7, len(result["failed_case_ids"]))

    def test_cli_check_never_invokes_a_model(self) -> None:
        result = subprocess.run(
            ["python3", "tools/model_stress_runner.py", "check"],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["model_invoked"])

    def test_cli_check_rejects_symlink_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            actual = base / "actual"
            task = actual / "harness/model-stress/tasks/identifier-canonicalization-v1.json"
            task.parent.mkdir(parents=True)
            shutil.copy2(TASK_PATH, task)
            linked = base / "linked"
            linked.symlink_to(actual, target_is_directory=True)
            result = subprocess.run(
                [
                    "python3",
                    "tools/model_stress_runner.py",
                    "check",
                    "--root",
                    str(linked),
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["model_invoked"])

    def test_pi_version_uses_networkless_read_only_self_contained_installation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            binary = Path(name) / "bin"
            binary.mkdir()
            node = binary / "node"
            node.write_text("#!/bin/sh\n", encoding="utf-8")
            node.chmod(0o755)
            pi = binary / "pi"
            pi.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            pi.chmod(0o755)
            completed = subprocess.CompletedProcess([], 0)

            def fake_run(*args, **kwargs):
                kwargs["stdout"].write(b"pi 9.8.7\n")
                return completed

            with patch(
                "harness.runtime.model_stress_runner.subprocess.run",
                side_effect=fake_run,
            ) as run:
                self.assertEqual("9.8.7", pi_version(pi))
            command = run.call_args.args[0]
            self.assertIn("--unshare-all", command)
            mount = command.index("/opt/pi-node")
            self.assertEqual("--ro-bind", command[mount - 2])
            self.assertEqual(str(Path(name)), command[mount - 1])

    def test_cli_rejects_output_before_model_invocation(self) -> None:
        from tools import model_stress_runner as cli

        argv = self._run_argv() + ["--output", "outside.json"]
        stream = io.StringIO()
        with (
            patch.object(sys, "argv", argv),
            patch.object(cli, "run_paired") as run,
            redirect_stdout(stream),
        ):
            self.assertEqual(2, cli.main())
        run.assert_not_called()
        self.assertFalse(json.loads(stream.getvalue())["model_invoked"])

    def test_cli_preserves_invocation_state_on_execution_failure(self) -> None:
        from tools import model_stress_runner as cli

        stream = io.StringIO()
        with (
            patch.object(sys, "argv", self._run_argv()),
            patch.object(
                cli,
                "run_paired",
                side_effect=RunnerExecutionError("after invocation", model_invoked=True),
            ),
            redirect_stdout(stream),
        ):
            self.assertEqual(2, cli.main())
        self.assertTrue(json.loads(stream.getvalue())["model_invoked"])

    @staticmethod
    def _run_argv() -> list[str]:
        return [
            "model_stress_runner.py",
            "run",
            "--root",
            str(ROOT),
            "--task",
            str(TASK_PATH),
            "--pi",
            "/tmp/pi/bin/pi",
            "--provider",
            "provider",
            "--model",
            "model",
            "--serving-runtime",
            "runtime",
            "--serving-recipe",
            "recipe",
        ]


if __name__ == "__main__":
    unittest.main()
