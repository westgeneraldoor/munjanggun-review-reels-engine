import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from video_engine_v2.privacy_face_blur import (
    FaceBox,
    image_files,
    mask_faces,
    parse_gemini_faces,
    parse_vision_faces,
    sanitize_images,
)


class PrivacyFaceBlurTest(unittest.TestCase):
    def test_parse_vision_faces_prefers_fd_bounding_poly(self):
        response = {
            "faceAnnotations": [
                {
                    "detectionConfidence": 0.98,
                    "boundingPoly": {"vertices": [{"x": 1, "y": 2}, {"x": 10, "y": 2}, {"x": 10, "y": 20}, {"x": 1, "y": 20}]},
                    "fdBoundingPoly": {"vertices": [{"x": 3, "y": 4}, {"x": 8, "y": 4}, {"x": 8, "y": 14}, {"x": 3, "y": 14}]},
                }
            ]
        }

        faces = parse_vision_faces(response)

        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].vertices, ((3, 4), (8, 4), (8, 14), (3, 14)))
        self.assertEqual(faces[0].source, "fdBoundingPoly")
        self.assertEqual(faces[0].detection_confidence, 0.98)

    def test_parse_gemini_faces_converts_normalized_yxyx_boxes(self):
        text = '{"faces":[{"bbox":[100,200,300,400],"reason":"framed photo"}]}'

        faces = parse_gemini_faces(text, width=1000, height=2000)

        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].vertices, ((200, 200), (400, 200), (400, 600), (200, 600)))
        self.assertEqual(faces[0].source, "gemini_visual_bbox")

    def test_mask_faces_only_changes_face_region(self):
        image = Image.new("RGB", (100, 100), (255, 255, 255))
        pixels = image.load()
        for x in range(40, 60):
            for y in range(40, 60):
                pixels[x, y] = (0, 0, 0)

        masked = mask_faces(
            image,
            [FaceBox(vertices=((40, 40), (60, 40), (60, 60), (40, 60)))],
            blur_radius=10,
            padding_ratio=0.1,
        )

        self.assertEqual(masked.getpixel((5, 5)), (255, 255, 255))
        self.assertNotEqual(masked.getpixel((50, 50)), image.getpixel((50, 50)))

    def test_sanitize_images_accepts_precomputed_detections_and_writes_review_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            image_path = input_dir / "sample.jpg"
            Image.new("RGB", (120, 120), (230, 230, 230)).save(image_path)
            detections = {
                "images": [
                    {
                        "file": "sample.jpg",
                        "faces": [
                            {
                                "vertices": [[40, 40], [80, 40], [80, 80], [40, 80]],
                                "detection_confidence": 0.99,
                                "source": "test",
                            }
                        ],
                    }
                ]
            }
            detections_path = root / "detections.json"
            detections_path.write_text(json.dumps(detections), encoding="utf-8")

            report = sanitize_images(input_dir, output_dir, precomputed_detections=detections_path)

            self.assertEqual(report["privacy_scope"], "faces_only")
            self.assertEqual(report["images"][0]["face_count"], 1)
            self.assertTrue((output_dir / "sample.jpg").exists())
            self.assertTrue(Path(report["contact_sheet"]).exists())

    def test_image_files_ignores_non_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.jpg").write_bytes(b"fake")
            (root / "b.txt").write_text("x", encoding="utf-8")

            self.assertEqual([path.name for path in image_files(root)], ["a.jpg"])


if __name__ == "__main__":
    unittest.main()
