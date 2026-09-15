import unittest

from PIL import Image

from reference_combiner.composer import ComposeSettings, compose_image


class ComposerTests(unittest.TestCase):
    def make_images(self):
        return [
            Image.new("RGB", (736, 1104), "red"),
            Image.new("RGB", (1000, 1500), "green"),
            Image.new("RGB", (1200, 800), "blue"),
        ]

    def test_auto_layout_composes_non_empty_image(self):
        img = compose_image(self.make_images(), ComposeSettings(layout="auto"))
        self.assertGreater(img.width, 0)
        self.assertGreater(img.height, 0)

    def test_grid_respects_fixed_width_mode(self):
        img = compose_image(
            self.make_images(),
            ComposeSettings(layout="3x1", output_width_mode="1920", gap=8, margin=8),
        )
        self.assertEqual(img.width, 1920)

    def test_no_upscale_in_auto_width(self):
        source = [Image.new("RGB", (120, 120), "white")]
        img = compose_image(source, ComposeSettings(layout="horizontal", output_width_mode="auto", margin=0, gap=0))
        self.assertEqual(img.width, 120)
        self.assertEqual(img.height, 120)


if __name__ == "__main__":
    unittest.main()
