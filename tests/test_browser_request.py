import importlib
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_incremental_crawl import authenticated_probe_client, credential_environment
from v2ex_scrapy.api import APIError, V2EXAPIClient
from v2ex_scrapy.browser_request import BrowserRequestError, load_browser_request


EXPORT = (
    "curl 'https://www.v2ex.com/api/v2/member' \\\n"
    "  -H 'user-agent: test-browser/154' \\\n"
    "  -H 'sec-ch-ua-platform: Windows' \\\n"
    "  -H 'authorization: Bearer private-export-token' \\\n"
    "  -H 'accept: */*' \\\n"
    "  -b 'A2=private-cookie; PB3_SESSION=session'"
)


class BrowserRequestTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "request"
        self.path.write_text(EXPORT)

    def test_reads_browser_headers_without_reusing_exported_token(self):
        profile = load_browser_request(self.path)
        self.assertEqual(profile.host, "www.v2ex.com")
        self.assertEqual(profile.headers["user-agent"], "test-browser/154")
        self.assertEqual(profile.cookie, "A2=private-cookie; PB3_SESSION=session")
        self.assertNotIn("authorization", profile.headers)
        self.assertNotIn("cookie", profile.request_headers())
        self.assertIn("cookie", profile.request_headers(include_cookie=True))
        self.assertNotIn("private-", repr(profile))

    def test_rejects_other_hosts_methods_shell_commands_and_file_options(self):
        for raw in [
            EXPORT.replace("www.v2ex.com", "example.com"),
            EXPORT.replace("www.v2ex.com", "www.v2ex.com@example.com"),
            EXPORT.replace("https://", "http://"),
            EXPORT.replace("https://www.v2ex.com", "https://www.v2ex.com:8080"),
            EXPORT + " --data-raw 'private-body'",
            EXPORT + " -X POST",
            EXPORT + " ; touch /tmp/do-not-execute",
            EXPORT + " --config /tmp/private-file",
            EXPORT.replace("A2=private-cookie; PB3_SESSION=session", "@/tmp/private-file"),
        ]:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(BrowserRequestError) as result:
                    load_browser_request(self.path)
                self.assertNotIn("private-", str(result.exception))

    def test_never_expands_shell_substitution_inside_a_header(self):
        marker = Path(self.directory.name) / "must-not-exist"
        self.path.write_text(EXPORT.replace("test-browser/154", f"$(touch {marker})"))
        profile = load_browser_request(self.path)
        self.assertFalse(marker.exists())
        self.assertIn("$(touch", profile.headers["user-agent"])

    def test_rejects_duplicate_and_injected_headers(self):
        for suffix in [" -H 'cookie: other=private'", " -H 'user-agent: private'", " -H 'accept: ok\r\nInjected: private'"]:
            with self.subTest(suffix=suffix):
                self.path.write_text(EXPORT + suffix)
                with self.assertRaises(BrowserRequestError):
                    load_browser_request(self.path)

    def test_explicit_get_and_compression_are_safe_export_options(self):
        self.path.write_text(EXPORT + " --request GET --compressed")
        self.assertEqual(load_browser_request(self.path).host, "www.v2ex.com")

    def test_html_preflight_uses_profile_cookie_and_never_api_authorization(self):
        args = SimpleNamespace(request_file=self.path, cookie_file=None, proxy=None, probe_delay=1, probe_timeout=20)
        with patch("scripts.run_incremental_crawl.V2EXProbeClient.verify_login"):
            client = authenticated_probe_client(args)
        self.assertEqual(client.cookie, "A2=private-cookie; PB3_SESSION=session")
        self.assertEqual(client.headers["user-agent"], "test-browser/154")
        self.assertNotIn("authorization", client.headers)
        self.assertEqual(credential_environment(args), {"V2EX_BROWSER_REQUEST_FILE": str(self.path)})

    def test_api_always_uses_separate_token_file_value(self):
        client = V2EXAPIClient("private-current-token", request_file=self.path)
        self.assertEqual(client.token, "private-current-token")
        self.assertNotIn("authorization", client.headers)
        self.assertEqual(client.headers["user-agent"], "test-browser/154")
        self.assertIn("cookie", client.headers)
        with self.assertRaises(APIError):
            V2EXAPIClient("private-current-token", request_file=self.path, host="edge.v2ex.com")

    def test_scrapy_settings_use_same_profile_without_credential_headers(self):
        from v2ex_scrapy import settings
        try:
            with patch.dict(os.environ, {"V2EX_BROWSER_REQUEST_FILE": str(self.path)}):
                importlib.reload(settings)
                self.assertEqual(settings.USER_AGENT, "test-browser/154")
                self.assertEqual(settings.COOKIES, "A2=private-cookie; PB3_SESSION=session")
                self.assertEqual(settings.DEFAULT_REQUEST_HEADERS["sec-ch-ua-platform"], "Windows")
                self.assertNotIn("authorization", settings.DEFAULT_REQUEST_HEADERS)
                self.assertNotIn("cookie", settings.DEFAULT_REQUEST_HEADERS)
        finally:
            importlib.reload(settings)


if __name__ == "__main__":
    unittest.main()
