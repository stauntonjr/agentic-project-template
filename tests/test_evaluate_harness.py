from pathlib import Path
import unittest

from tools.common import load_json
from tools.evaluate_harness import forward_prompts, validate_scenarios


ROOT = Path(__file__).resolve().parents[1]


class EvaluateHarnessTests(unittest.TestCase):
    def test_scenarios_route_to_existing_skills(self) -> None:
        payload = load_json(ROOT / "harness/evals/scenarios.json")
        self.assertEqual([], validate_scenarios(ROOT, payload))
        prompts = forward_prompts(ROOT, payload)
        self.assertEqual(len(payload["scenarios"]), len(prompts))
        context_gap = next(prompt for prompt in prompts if prompt["id"] == "E008-context-gap")
        self.assertIsNone(context_gap["skill_path"])

    def test_layered_domain_routing_keeps_target_rules_local(self) -> None:
        payload = load_json(ROOT / "harness/evals/scenarios.json")
        scenario = next(
            item for item in payload["scenarios"] if item["id"] == "E009-layered-domain-routing"
        )

        self.assertEqual("execute-engineering-loop", scenario["expected_primary_skill"])
        self.assertIn(
            "read the target repository AGENTS.md before planning commands",
            scenario["required_behaviors"],
        )
        self.assertIn(
            "promote S3NTINEL Spark rules into universal policy",
            scenario["forbidden_behaviors"],
        )
        self.assertNotIn("sentinel-spark35", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))

    def test_s3ntinel_fixture_separates_projects_roles_and_local_policy(self) -> None:
        fixture = load_json(ROOT / "harness/fixtures/s3ntinel-routing-evaluation.json")
        issue_sets = [set(project["issues"]) for project in fixture["github_projects"]]

        for index, issues in enumerate(issue_sets):
            for other in issue_sets[index + 1 :]:
                self.assertTrue(issues.isdisjoint(other))
        self.assertEqual("PASS", fixture["routing_probe"]["result"])
        self.assertEqual(3, fixture["routing_probe"]["read_calls"])
        self.assertEqual(231, fixture["pi_failure_probe"]["unavailable_tool_attempts"])
        self.assertEqual(0, fixture["pi_failure_probe"]["executed_unavailable_tools"])
        self.assertEqual(
            "APPROVE_CONTENT_ONLY",
            fixture["role_exercises"]["verifier"]["result"],
        )
        self.assertEqual("NOT_READY", fixture["role_exercises"]["release_steward"]["result"])
        self.assertTrue(all(item["scope"] == "repository-local" for item in fixture["local_rules"]))
