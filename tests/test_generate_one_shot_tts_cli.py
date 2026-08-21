import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_one_shot_tts as cli


class OneShotTTSCLIAuthoringGateTests(unittest.TestCase):
    def test_invalid_authoring_stops_before_the_tts_writer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            planning = package / "planning.json"
            edit = package / "edit.json"
            script = package / "fixture_script.md"
            planning.write_text(json.dumps({"workflow_contract": {}}), encoding="utf-8")
            edit.write_text(json.dumps({"beats": []}), encoding="utf-8")
            script.write_text("fixture", encoding="utf-8")

            with patch("scripts.generate_one_shot_tts.generate_one_shot_tts") as writer:
                return_code = cli.main(
                    [
                        "--package",
                        str(package),
                        "--planning",
                        str(planning),
                        "--edit",
                        str(edit),
                        "--script",
                        str(script),
                    ]
                )

            self.assertEqual(return_code, 2)
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
