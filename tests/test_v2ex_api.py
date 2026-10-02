import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import check_v2ex_api
from v2ex_scrapy.api import APIError, NoAPIRedirect, V2EXAPIClient, read_api_token


class APIResponse(io.BytesIO):
    def __init__(self, payload, status=200, content_type="application/json", **headers):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        super().__init__(raw)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in headers.items():
            self.headers[key] = str(value)


class V2EXAPITest(unittest.TestCase):
    def client(self, *responses):
        opener = Mock()
        opener.open.side_effect = responses
        return V2EXAPIClient("private-token", opener=opener, clock=lambda: 10, sleeper=Mock())

    def test_api_get_uses_bearer_without_cookie(self):
        client = self.client(APIResponse({"success": True, "result": {"id": 123}}))
        self.assertEqual(client.get("topic", topic_id=123), {"id": 123})
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://www.v2ex.com/api/v2/topics/123")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-token")
        self.assertIsNone(request.get_header("Cookie"))

    def test_pagination_and_conservative_delay(self):
        client = self.client(
            APIResponse({"success": True, "result": []}),
            APIResponse({"success": True, "result": []}),
        )
        client.get("latest", page=2)
        client.get("replies", topic_id=123, page=3)
        self.assertEqual(client.opener.open.call_args.args[0].full_url, "https://www.v2ex.com/api/v2/topics/123/replies?p=3")
        client.sleeper.assert_called_once_with(7)

    def test_smaller_advertised_quota_slows_down(self):
        client = self.client(
            APIResponse({"success": True, "result": []}, **{"X-Rate-Limit-Limit": 120}),
            APIResponse({"success": True, "result": []}),
        )
        client.get("latest")
        client.get("latest", page=2)
        client.sleeper.assert_called_once_with(31)

    def test_exhausted_quota_stops_before_another_request(self):
        client = self.client(APIResponse(
            {"success": True, "result": []},
            **{"X-Rate-Limit-Limit": 600, "X-Rate-Limit-Remaining": 0, "X-Rate-Limit-Reset": 123456},
        ))
        client.get("latest")
        with self.assertRaisesRegex(APIError, "quota exhausted"):
            client.get("latest", page=2)
        client.opener.open.assert_called_once()

    def test_429_stops_without_retrying(self):
        client = self.client(APIResponse(b"Too many requests", status=429, content_type="text/plain", **{"Retry-After": 120}))
        with self.assertRaisesRegex(APIError, "HTTP 429"):
            client.get("member")
        self.assertEqual(client.rate_limit["retry_after"], 120)
        with self.assertRaises(APIError):
            client.get("member")
        client.opener.open.assert_called_once()

    def test_html_failures_are_not_missing_topics_or_expired_tokens(self):
        for status in [200, 403, 404, 503]:
            with self.subTest(status=status):
                client = self.client(APIResponse(b"<title>private-token</title>", status=status, content_type="text/html"))
                with self.assertRaisesRegex(APIError, "non-JSON") as result:
                    client.get("topic", topic_id=123)
                self.assertNotIn("private-token", str(result.exception))
                self.assertTrue(client.blocked)

    def test_cloudflare_marker_is_reported_separately_from_api_authentication(self):
        client = self.client(APIResponse(
            b"<title>Just a moment...</title>", status=403,
            content_type="text/html", **{"cf-mitigated": "challenge"},
        ))
        with self.assertRaisesRegex(APIError, "Cloudflare challenge"):
            client.get("member")

    def test_json_auth_error_does_not_echo_token_or_server_message(self):
        client = self.client(APIResponse({"success": False, "message": "private-token expired"}, status=401))
        with self.assertRaisesRegex(APIError, "authorization failed") as result:
            client.get("member")
        self.assertNotIn("private-token", str(result.exception))

    def test_successful_http_can_still_be_an_api_failure(self):
        client = self.client(APIResponse({"success": False, "message": "Token expired"}))
        with self.assertRaisesRegex(APIError, "successful result"):
            client.get("member")

    def test_unexpected_json_is_not_importable_data(self):
        for payload in [{"success": True}, [], b"not-json"]:
            with self.subTest(payload=payload):
                client = self.client(APIResponse(payload))
                with self.assertRaises(APIError):
                    client.get("member")
                self.assertTrue(client.blocked)

    def test_redirect_handler_does_not_forward_authorization(self):
        self.assertIsNone(NoAPIRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))
        client = self.client(urllib.error.HTTPError(
            "https://www.v2ex.com/api/v2/member", 302, "Found",
            {"Location": "https://example.com/?token=private-token", "Content-Type": "text/html"}, io.BytesIO(b""),
        ))
        with self.assertRaisesRegex(APIError, "non-JSON") as result:
            client.get("member")
        self.assertNotIn("private-token", str(result.exception))

    def test_connection_error_is_redacted(self):
        client = self.client(urllib.error.URLError("https://user:private-token@proxy.invalid"))
        with self.assertRaisesRegex(APIError, "connection failed") as result:
            client.get("member")
        self.assertNotIn("private-token", str(result.exception))

    def test_only_official_hosts_and_read_resources_are_allowed(self):
        with self.assertRaises(ValueError):
            V2EXAPIClient("private-token", host="example.com")
        client = self.client()
        for resource in ["tokens", "../token", "https://example.com", "create"]:
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                client.get(resource)
        for topic_id in [None, 0, -1, "123/../tokens", True]:
            with self.subTest(topic_id=topic_id), self.assertRaises(ValueError):
                client.get("topic", topic_id=topic_id)
        client.opener.open.assert_not_called()

    def test_token_file_rejects_bearer_prefix_and_control_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            for value in ["", "Bearer private-token", "one\ntwo", "one\x00two"]:
                with self.subTest(value=value):
                    path.write_text(value)
                    with self.assertRaises(APIError):
                        read_api_token(path)
            path.write_text("private-token\n")
            self.assertEqual(read_api_token(path), "private-token")

    def test_probe_only_prints_shapes_not_account_or_post_content(self):
        client = Mock()
        client.rate_limit = {"remaining": 500}
        client.get.side_effect = [
            {"username": "private-member"},
            {"id": 123, "title": "private-title", "member": {"username": "private-author"}},
            [{"id": 456, "content": "private-reply", "thanks": 2}],
        ]
        with (
            patch("sys.argv", ["probe.py", "--token-file", "/unused", "--topic-id", "123"]),
            patch.object(check_v2ex_api, "read_api_token", return_value="private-token"),
            patch.object(check_v2ex_api, "V2EXAPIClient", return_value=client),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            check_v2ex_api.main()
        self.assertNotIn("private-", output.getvalue())
        self.assertIn('"authenticated": true', output.getvalue())


if __name__ == "__main__":
    unittest.main()
