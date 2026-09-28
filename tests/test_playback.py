import unittest

from app.models import LyricLine
from app.playback import adjusted_elapsed, current_line_index


class PlaybackTests(unittest.TestCase):
    def test_positive_offset_delays_lyrics(self):
        self.assertEqual(adjusted_elapsed(150, 100, 22), 28)

    def test_elapsed_is_clamped(self):
        self.assertEqual(adjusted_elapsed(110, 100, 22), 0)
        self.assertEqual(adjusted_elapsed(1000, 100, 22, duration=120), 120)

    def test_current_line(self):
        lines = (LyricLine(10, "a"), LyricLine(20, "b"))
        self.assertEqual(current_line_index(lines, 9), -1)
        self.assertEqual(current_line_index(lines, 20), 1)


if __name__ == "__main__":
    unittest.main()
