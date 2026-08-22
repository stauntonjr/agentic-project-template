from pathlib import Path
import json
import unittest

from tools.harness_check import check


ROOT = Path(__file__).resolve().parents[1]


class HarnessCheckTests(unittest.TestCase):
    def test_template_is_valid(self) -> None:
        result = check(ROOT)
        self.assertTrue(result.ok, result.errors)
        self.assertIn("7 skills", result.checked)
        self.assertIn("2 provider adapters", result.checked)
        self.assertIn("Pi adapter", result.checked)

    def test_pi_adapter_remains_thin_and_provider_neutral(self) -> None:
        settings = json.loads((ROOT / ".pi/settings.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "harness/adapters/pi.json").read_text(encoding="utf-8"))

        self.assertNotIn("packages", settings)
        self.assertNotIn("defaultModel", settings)
        self.assertEqual(["extensions/context-readiness.ts"], settings["extensions"])
        self.assertEqual("experimental", manifest["status"])
        self.assertEqual("not supplied by Pi core adapter", manifest["capabilities"]["role_delegation"])
        self.assertEqual(
            ".agents/skills",
            next(item for item in manifest["mappings"] if item["contract"] == "skills")["canonical"],
        )


if __name__ == "__main__":
    unittest.main()
