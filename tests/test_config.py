import os
import unittest
from unittest.mock import patch

from v2ex_scrapy.config import get_bool_env, get_float_env, get_int_env, get_proxies


class ConfigTest(unittest.TestCase):
    def test_get_proxies_from_comma_separated_env(self):
        with patch.dict(os.environ, {"V2EX_PROXIES": "http://a, http://b"}, clear=False):
            self.assertEqual(get_proxies(), ["http://a", "http://b"])

    def test_get_proxies_from_json_env(self):
        with patch.dict(os.environ, {"V2EX_PROXIES": '["http://a", "http://b"]'}, clear=False):
            self.assertEqual(get_proxies(), ["http://a", "http://b"])

    def test_env_fallbacks(self):
        with patch.dict(
            os.environ,
            {"BAD_INT": "abc", "BAD_FLOAT": "abc", "FEATURE_ON": "yes"},
            clear=False,
        ):
            self.assertEqual(get_int_env("BAD_INT", 3), 3)
            self.assertEqual(get_float_env("BAD_FLOAT", 1.5), 1.5)
            self.assertTrue(get_bool_env("FEATURE_ON"))

    def test_float_env(self):
        with patch.dict(os.environ, {"DELAY": "1.25"}, clear=False):
            self.assertEqual(get_float_env("DELAY", 2.0), 1.25)


if __name__ == "__main__":
    unittest.main()
