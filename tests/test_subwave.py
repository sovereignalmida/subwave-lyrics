import unittest

from app.subwave import parse_now_playing


class ParseNowPlayingTests(unittest.TestCase):
    def test_full_payload(self):
        track, online, buffer_seconds = parse_now_playing({
            "streamOnline": True,
            "stream": {"bufferSeconds": 22},
            "nowPlaying": {
                "artist": "Neil Young",
                "title": "Goin’ Home",
                "album": "Are You Passionate?",
                "subsonic_id": "abc",
                "timestamp": 1790596454,
                "duration": 529,
                "year": 2002,
                "genres": ["Rock", "Folk Rock"],
            },
        })
        self.assertTrue(online)
        self.assertEqual(buffer_seconds, 22)
        self.assertEqual(track.duration, 529)
        self.assertEqual(track.genres, ("Rock", "Folk Rock"))

    def test_optional_fields_are_optional(self):
        track, online, _ = parse_now_playing({
            "streamOnline": True,
            "nowPlaying": {"artist": "Bauhaus", "title": "Dancing", "timestamp": 1790595614},
        })
        self.assertTrue(online)
        self.assertIsNone(track.duration)
        self.assertIsNone(track.album)

    def test_offline_ignores_stale_track(self):
        track, online, _ = parse_now_playing({
            "streamOnline": False,
            "nowPlaying": {"artist": "Old", "title": "Track", "timestamp": 1},
        })
        self.assertFalse(online)
        self.assertIsNone(track)

    def test_timestamp_distinguishes_repeat_plays(self):
        base = {"streamOnline": True, "nowPlaying": {"artist": "A", "title": "T", "subsonic_id": "id", "timestamp": 100}}
        first, _, _ = parse_now_playing(base)
        base["nowPlaying"]["timestamp"] = 200
        second, _, _ = parse_now_playing(base)
        self.assertNotEqual(first.play_identity, second.play_identity)


if __name__ == "__main__":
    unittest.main()
