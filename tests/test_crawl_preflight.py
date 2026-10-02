import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import run_incremental_crawl as incremental
from scripts import run_monthly_close as monthly


class CrawlPreflightTest(unittest.TestCase):
    def client_with_page(self, status, html):
        client = incremental.V2EXProbeClient("session=private", delay=0)
        client._request = Mock(return_value=(status, html.encode()))
        return client

    def test_settings_with_signout_verifies_login(self):
        for href in ["/signout?once=private", "javascript:location.href='/signout?once=private'"]:
            with self.subTest(href=href):
                client = self.client_with_page(200, f'<a href="{href}">Sign out</a>')
                client.verify_login()
                client._request.assert_called_once_with("https://www.v2ex.com/settings")

    def test_public_success_does_not_prove_login(self):
        client = self.client_with_page(200, '<a href="/signin">Sign in</a>')
        with self.assertRaisesRegex(incremental.CrawlAccessError, "login is unconfirmed"):
            client.verify_login()

    def test_current_logout_control_uses_onclick_instead_of_href(self):
        client = self.client_with_page(
            200, '<a href="#;" onclick="location.href=\'/signout?once=private\'">Sign out</a>'
        )
        client.verify_login()

    def test_challenges_are_not_reported_as_expired_cookies(self):
        for status in [200, 403, 503]:
            with self.subTest(status=status):
                client = self.client_with_page(status, "<title>Just a moment...</title>")
                with self.assertRaisesRegex(incremental.CrawlAccessError, "login status is unknown"):
                    client.verify_login()

    def test_challenge_form_is_detected_without_a_title(self):
        client = self.client_with_page(200, '<form id="challenge-form"></form>')
        with self.assertRaisesRegex(incremental.CrawlAccessError, "Cloudflare"):
            client.verify_login()

    def test_redirect_is_not_followed_or_logged(self):
        client = incremental.V2EXProbeClient("session=private", delay=0)
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError(
            "https://www.v2ex.com/settings", 302, "Found",
            {"Location": "https://example.com/signin?token=private"},
            io.BytesIO(b""),
        )
        with self.assertRaisesRegex(incremental.CrawlAccessError, "requires sign-in") as result:
            client.verify_login()
        self.assertNotIn("private", str(result.exception))
        client.opener.open.assert_called_once()
        handler = incremental.NoProbeRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_access_failures_stop_topic_boundary_scanning_immediately(self):
        for status in [403, 429, 500, 503]:
            with self.subTest(status=status):
                client = self.client_with_page(status, "unavailable")
                with self.assertRaises(incremental.CrawlAccessError):
                    incremental.nearest_valid_probe(client.fetch_topic, 100, 1, 200)
                client._request.assert_called_once()
                self.assertEqual(client.cache, {})

    def test_404_topic_remains_an_inaccessible_id(self):
        client = self.client_with_page(404, "Not found")
        self.assertEqual(client.fetch_topic(100), incremental.TopicProbe(100, 404))

    def test_network_error_does_not_echo_proxy_credentials(self):
        client = incremental.V2EXProbeClient("session=private", delay=0)
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.URLError("http://user:private@proxy.invalid")
        with self.assertRaisesRegex(incremental.CrawlAccessError, "URLError") as result:
            client.verify_login()
        self.assertNotIn("private", str(result.exception))

    def test_missing_or_malformed_cookie_stops_before_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie"
            args = SimpleNamespace(cookie_file=path, proxy=None, probe_delay=1, probe_timeout=10)
            for raw in [None, "", "not-a-cookie", "one=1\ntwo=2"]:
                with self.subTest(raw=raw), patch.object(incremental.V2EXProbeClient, "verify_login") as verify:
                    if raw is not None:
                        path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(incremental.CrawlAccessError):
                        incremental.authenticated_probe_client(args)
                    verify.assert_not_called()

    def test_check_action_needs_no_date_or_database(self):
        with (
            patch("sys.argv", ["run_incremental_crawl.py", "check"]),
            patch.object(incremental, "authenticated_probe_client") as check,
            patch.object(incremental, "database_snapshot") as snapshot,
            patch.object(incremental.subprocess, "run") as launch,
        ):
            incremental.main()
            check.assert_called_once()
            snapshot.assert_not_called()
            launch.assert_not_called()

    def test_new_incremental_plan_stops_before_database_or_job_on_failed_login(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("sys.argv", ["run_incremental_crawl.py", "--through", "2026-09-26", "--state-root", directory]),
                patch.object(incremental, "authenticated_probe_client", side_effect=incremental.CrawlAccessError("blocked")),
                patch.object(incremental, "database_snapshot") as snapshot,
                patch.object(incremental.subprocess, "run") as launch,
            ):
                with self.assertRaisesRegex(incremental.CrawlAccessError, "blocked"):
                    incremental.main()
                snapshot.assert_not_called()
                launch.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_resumed_jobs_also_check_login_before_launch(self):
        for module, state_name, arguments, plan in [
            (incremental, "through-2026-09-26", ["--through", "2026-09-26"], {"start_id": 10, "end_id": 20}),
            (monthly, "month-close-2026-08-last-7-days", ["--month", "2026-08", "--last-days", "7"], {}),
        ]:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / state_name
                state.mkdir()
                path = state / "plan.json"
                original = json.dumps({"schema": 1, "unit": "test-unit", **plan})
                path.write_text(original, encoding="utf-8")
                with (
                    patch("sys.argv", ["runner.py", *arguments, "--state-root", directory]),
                    patch.object(module, "unit_status", return_value="inactive"),
                    patch.object(module, "authenticated_probe_client", side_effect=incremental.CrawlAccessError("blocked")) as check,
                    patch.object(module.subprocess, "run") as launch,
                ):
                    with self.assertRaisesRegex(incremental.CrawlAccessError, "blocked"):
                        module.main()
                    check.assert_called_once()
                    launch.assert_not_called()
                    self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_monthly_dry_run_is_offline_and_uses_a_separate_tail_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            window = monthly.parse_month("2026-08")
            source = monthly.MonthSource([100, 101], 100, 101, 2, 2, window.end_timestamp + 1)
            with (
                patch("sys.argv", ["runner.py", "--month", "2026-08", "--last-days", "7", "--dry-run", "--state-root", directory]),
                patch.object(monthly.time, "time", return_value=window.end_timestamp + 86400 * 10),
                patch.object(monthly, "load_month_source", return_value=source) as load,
                patch.object(monthly, "database_snapshot", return_value={}),
                patch.object(monthly, "month_snapshot", return_value={}),
                patch.object(monthly, "authenticated_probe_client") as check,
                patch.object(monthly.subprocess, "run") as launch,
            ):
                monthly.main()
                check.assert_not_called()
                launch.assert_not_called()
                self.assertEqual(load.call_args.args[1].start_timestamp, window.end_timestamp - 86400 * 7)
            plan = json.loads((Path(directory) / "month-close-2026-08-last-7-days" / "plan.json").read_text())
            self.assertEqual(plan["last_days"], 7)
            self.assertEqual(plan["crawl_purpose"], "month-close-2026-08-last-7-days")

    def test_new_monthly_job_stops_without_saving_a_plan_on_failed_login(self):
        with tempfile.TemporaryDirectory() as directory:
            window = monthly.parse_month("2026-08")
            source = monthly.MonthSource([100, 101], 100, 101, 2, 2, window.end_timestamp + 1)
            with (
                patch("sys.argv", ["runner.py", "--month", "2026-08", "--last-days", "7", "--state-root", directory]),
                patch.object(monthly.time, "time", return_value=window.end_timestamp + 86400 * 10),
                patch.object(monthly, "load_month_source", return_value=source),
                patch.object(monthly, "database_snapshot") as snapshot,
                patch.object(monthly, "authenticated_probe_client", side_effect=incremental.CrawlAccessError("blocked")),
                patch.object(monthly.subprocess, "run") as launch,
            ):
                with self.assertRaisesRegex(incremental.CrawlAccessError, "blocked"):
                    monthly.main()
                snapshot.assert_not_called()
                launch.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
