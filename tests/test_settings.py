import unittest

from v2ex_scrapy import settings


class SettingsTest(unittest.TestCase):
    def test_default_request_identity_is_browser_compatible(self):
        self.assertIn("Mozilla/5.0", settings.DEFAULT_USER_AGENT)
        self.assertEqual(
            settings.DEFAULT_REQUEST_HEADERS["From"],
            "taifu@taifua.com",
        )


if __name__ == "__main__":
    unittest.main()
