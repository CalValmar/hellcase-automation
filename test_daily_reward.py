import fcntl
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import daily_reward as d


def reply(nickname, status="success", case_is_opened=True):
    return {
        "status": status,
        "case_is_opened": case_is_opened,
        "casename": "Newbie",
        "last_open_date": "2000-01-01 00:00:00",
        "user": {"id": 7, "nickname": nickname},
        "top_items": [{
            "user": {"id": 7},
            "steam_price_en": 9.5,
            "items": [{"drop_type": "item", "weapon_name": "USP | Test"}],
        }],
    }


class FakeSession:
    def __init__(self, data):
        self.cookies = mock.Mock()
        self.data = data

    def get(self, url, timeout=None):
        assert url == d.API_URL and timeout == 30
        return mock.Mock(json=lambda: self.data)


class DailyRewardTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def run_main(self, data, username=""):
        account = {"username": username, "xsrf": "x", "session": "s"}
        posts = []
        with mock.patch.object(d.requests, "session", return_value=FakeSession(data)), \
             mock.patch.object(d.requests, "post",
                               side_effect=lambda url, json=None, timeout=None: posts.append(json["content"])), \
             mock.patch.object(d.time, "sleep"), \
             mock.patch.object(d, "load_json",
                               side_effect=lambda path, default: (
                                   {"discord_webhook_url": "https://example.invalid/hook", "accounts": [account]}
                                   if path == "config.json" else default)):
            d.main()
        path = pathlib.Path("history.json")
        history = json.loads(path.read_text()) if path.exists() else []
        return history, posts

    def test_success_records_drop_under_configured_username(self):
        history, posts = self.run_main(reply("Alice"), "Alice")
        self.assertEqual(history[0]["account"], "Alice")
        self.assertEqual(history[0]["weapon"], "USP | Test")
        self.assertEqual(history[0]["price"], 9.5)
        self.assertEqual(len(posts), 1)

    def test_history_uses_local_run_time(self):
        clock = mock.Mock()
        clock.now.return_value.strftime.return_value = "2026-11-23 12:00:00"
        with mock.patch.object(d, "datetime", clock):
            history, _ = self.run_main(reply("Alice"))
        self.assertEqual(history[0]["date"], "2026-11-23 12:00:00")

    def test_message_says_when_api_has_no_drop(self):
        data = reply("Alice")
        data["top_items"] = []
        _, posts = self.run_main(data, "Alice")
        self.assertIn("gain non renseigné par l'API", posts[0])

    def test_empty_username_falls_back_to_api_nickname(self):
        history, _ = self.run_main(reply("Alice"))
        self.assertEqual(history[0]["account"], "Alice")

    def test_wrong_nickname_sends_warning(self):
        history, posts = self.run_main(reply("Bob"), "Bobby")
        self.assertEqual(history[0]["account"], "Bobby")
        self.assertEqual(len(posts), 2)
        self.assertIn("pseudo configuré", posts[0])

    def test_error_status_is_not_recorded_as_a_drop(self):
        history, posts = self.run_main(reply("Alice", status="error"), "Alice")
        self.assertEqual(history, [])
        self.assertEqual(len(posts), 1)
        self.assertIn("ouverture échouée", posts[0])

    def test_case_not_opened_is_not_recorded_as_a_drop(self):
        history, posts = self.run_main(reply("Alice", case_is_opened=False), "Alice")
        self.assertEqual(history, [])
        self.assertIn("ouverture échouée", posts[0])

    def test_failed_call_names_configured_user(self):
        account = {"username": "Alice", "xsrf": "x", "session": "s"}
        session = mock.Mock()
        session.get.side_effect = d.requests.RequestException("down")
        posts = []
        with mock.patch.object(d.requests, "session", return_value=session), \
             mock.patch.object(d.requests, "post",
                               side_effect=lambda url, json=None, timeout=None: posts.append(json["content"])), \
             mock.patch.object(d, "load_json", side_effect=lambda path, default: (
                 {"discord_webhook_url": "https://example.invalid/hook", "accounts": [account]}
                 if path == "config.json" else default)):
            d.main()
        self.assertEqual(len(posts), 1)
        self.assertIn("Alice", posts[0])
        self.assertIn("appel échoué", posts[0])

    def test_history_is_saved_after_each_account(self):
        account = {"username": "", "xsrf": "x", "session": "s"}
        with mock.patch.object(d.requests, "session",
                               side_effect=[FakeSession(reply("Alice")), RuntimeError("boom")]), \
             mock.patch.object(d.requests, "post"), \
             mock.patch.object(d.time, "sleep"), \
             mock.patch.object(d, "load_json", side_effect=lambda path, default: (
                 {"discord_webhook_url": "", "accounts": [account, account]}
                 if path == "config.json" else default)):
            with self.assertRaises(RuntimeError):
                d.main()
        history = json.loads(pathlib.Path("history.json").read_text())
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["account"], "Alice")

    def test_lock_skips_second_run(self):
        lock = open("daily-reward.lock", "a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with mock.patch.object(d, "main") as fake_main:
                d.run_locked()
                fake_main.assert_not_called()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def test_extract_drop_filters_by_user_id(self):
        self.assertEqual(d.extract_drop(reply("Alice"), 7), ("USP | Test", 9.5))
        self.assertEqual(d.extract_drop(reply("Alice"), 8), (None, None))


if __name__ == "__main__":
    unittest.main()
