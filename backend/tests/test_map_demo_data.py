import unittest
from pathlib import Path

from PIL import Image


DEMO_IMAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "public"
    / "data"
    / "philsa_flood_20250706_reference.png"
)


class HistoricalFloodReferenceTests(unittest.TestCase):
    def test_display_asset_covers_full_source_extent_and_is_attributed(self):
        with Image.open(DEMO_IMAGE_PATH) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.size, (2600, 7842))
            self.assertIn("61774 source polygon features rendered", image.info["Processing"])
            self.assertIn("15705 invalid source geometries repaired", image.info["Processing"])
            self.assertEqual(image.info["License"], "CC BY 4.0")
            self.assertIn("Philippine Space Agency", image.info["Source"])
            self.assertIn(
                "has not been validated against ground truth",
                image.info["Caveat"],
            )
            self.assertEqual(image.getchannel("A").getextrema(), (0, 107))
            flooded_pixel_count = sum(image.getchannel("A").histogram()[1:])
            self.assertGreater(flooded_pixel_count, 0)
            self.assertLess(flooded_pixel_count, image.width * image.height // 5)


if __name__ == "__main__":
    unittest.main()
