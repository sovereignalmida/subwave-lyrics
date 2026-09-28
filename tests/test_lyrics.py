import unittest

from app.lyrics import choose_match, normalize, parse_lrc
from app.models import Track


class LyricsTests(unittest.TestCase):
    def setUp(self):
        self.track = Track(
            artist="Neil Young",
            title="Goin’ Home",
            album="Are You Passionate?",
            duration=529,
            subsonic_id="id",
            started_at=100,
        )

    def test_normalizes_smart_apostrophe(self):
        self.assertEqual(normalize("Goin’ Home"), normalize("Goin' Home"))

    def test_lrc_parser_supports_fractional_timestamps(self):
        lines = parse_lrc("[00:12.40]First\n[01:02.005][01:03.00]Second")
        self.assertEqual([line.time for line in lines], [12.4, 62.005, 63.0])
        self.assertEqual(lines[1].text, "Second")

    def test_prefers_closest_duration(self):
        match = choose_match(self.track, [
            {"id": 1, "artistName": "Neil Young", "trackName": "Goin' Home", "albumName": "Are You Passionate?", "duration": 145, "plainLyrics": "wrong"},
            {"id": 2, "artistName": "Neil Young", "trackName": "Goin' Home", "albumName": "Are You Passionate?", "duration": 528, "plainLyrics": "right"},
        ])
        self.assertEqual(match.item["id"], 2)

    def test_rejects_unrelated_song(self):
        match = choose_match(self.track, [{"artistName": "Someone Else", "trackName": "Home", "duration": 529, "plainLyrics": "wrong"}])
        self.assertIsNone(match)

    def test_accepts_primary_artist_with_guest_credit(self):
        match = choose_match(self.track, [{
            "id": 3,
            "artistName": "Neil Young with Crazy Horse",
            "trackName": "Goin' Home",
            "albumName": "Are You Passionate?",
            "duration": 529,
            "plainLyrics": "lyrics",
        }])
        self.assertEqual(match.item["id"], 3)


if __name__ == "__main__":
    unittest.main()
