import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiValidationTest(unittest.TestCase):
    def test_ci_uses_one_canonical_repository_validation_command(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")

        self.assertEqual(workflow.count("run: npm run validate"), 1)
        self.assertNotIn("python -m unittest discover -s tests", workflow)


if __name__ == "__main__":
    unittest.main()
