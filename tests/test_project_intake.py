import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.common import load_json
from tools.project_intake import normalize_answer, render


ROOT = Path(__file__).resolve().parents[1]


class ProjectIntakeTests(unittest.TestCase):
    def test_fixture_resolves_essential_context(self) -> None:
        raw = load_json(ROOT / "harness/fixtures/intake.answers.json")
        answers = {
            key: normalize_answer(value, source="test", recorded_at="2026-08-21T00:00:00Z")
            for key, value in raw.items()
        }
        project, planning, missing = render(
            load_json(ROOT / "harness/project.yaml"),
            load_json(ROOT / ".github/planning.json"),
            answers,
            profile_root=ROOT / "harness/profiles",
        )
        self.assertEqual([], missing)
        self.assertFalse(project["template_mode"])
        self.assertEqual("Example Agent Project", project["project"]["name"])
        self.assertEqual("example/example-agent-project", planning["repository"])
        self.assertEqual("example", planning["project"]["owner"])

    def test_cli_creates_a_valid_derived_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "derived"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/project_intake.py"),
                    "--answers",
                    str(ROOT / "harness/fixtures/intake.answers.json"),
                    "--target",
                    str(target),
                    "--apply",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            result = subprocess.run(
                [sys.executable, str(target / "tools/harness_check.py"), "--json"],
                cwd=target,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue((target / "harness/intake.json").is_file())
            self.assertTrue((target / ".pi/settings.json").is_file())
            self.assertTrue((target / "harness/adapters/pi.json").is_file())

    def test_adopt_preserves_existing_files_and_reports_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "existing"
            target.mkdir()
            (target / "README.md").write_text("existing readme\n", encoding="utf-8")
            (target / "AGENTS.md").write_text("# Existing rules\n", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/project_intake.py"),
                    "--answers",
                    str(ROOT / "harness/fixtures/intake.answers.json"),
                    "--target",
                    str(target),
                    "--mode",
                    "adopt",
                    "--apply",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual("existing readme\n", (target / "README.md").read_text())
            self.assertEqual("# Existing rules\n", (target / "AGENTS.md").read_text())
            self.assertTrue((target / "harness/project.yaml").is_file())
            self.assertTrue((target / ".pi/extensions/context-readiness.ts").is_file())
            gaps = (target / "docs/project/adoption-gaps.md").read_text()
            self.assertIn("README.md", gaps)
            self.assertIn("AGENTS.md", gaps)


if __name__ == "__main__":
    unittest.main()
