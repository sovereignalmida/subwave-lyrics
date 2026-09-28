import os
import unittest
from unittest.mock import patch

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_derives_public_api_and_stream_urls(self):
        with patch.dict(os.environ, {"SUBWAVE_STATION_URL": "https://radio.example.com/"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.subwave_api_url, "https://radio.example.com/api")
        self.assertEqual(settings.subwave_stream_url, "https://radio.example.com/stream.mp3")

    def test_internal_overrides_win(self):
        env = {
            "SUBWAVE_STATION_URL": "https://radio.example.com",
            "SUBWAVE_API_URL": "http://controller:7701/",
            "SUBWAVE_STREAM_URL": "http://broadcast:7702/stream.mp3",
            "KEEP_STATION_ACTIVE": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.subwave_api_url, "http://controller:7701")
        self.assertEqual(settings.subwave_stream_url, "http://broadcast:7702/stream.mp3")
        self.assertFalse(settings.keep_station_active)

    def test_legacy_subwave_url_still_works(self):
        with patch.dict(os.environ, {"SUBWAVE_URL": "http://controller:7701"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.subwave_api_url, "http://controller:7701")


if __name__ == "__main__":
    unittest.main()
