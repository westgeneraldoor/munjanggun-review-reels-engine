import sys
import unittest

from scripts import produce_review_v2


class ProduceReviewV2SubprocessTest(unittest.TestCase):
    def test_utf8_child_runner_preserves_korean_output_paths(self):
        runner = getattr(produce_review_v2, "run_utf8_capture", None)
        self.assertIsNotNone(runner, "official HTML orchestration needs a UTF-8 child-process boundary")
        if runner is None:
            return

        expected = "C:/작업/문장군/118_견적/index.html"
        result = runner([sys.executable, "-c", f"print({expected!r})"], cwd=produce_review_v2.ROOT)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
