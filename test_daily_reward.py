import fcntl
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import daily_reward as d

CLAIM_URL = "https://api.hellcase.com/user_level/claim_free_case/newbie"
STATE_URL = "https://api.hellcase.com/open/newbie/state"


def case_info(nickname):
    return {
        "status": "success",
        "case_is_opened": True,
        "casename": "Newbie",
        "last_open_date": "2000-01-01 00:00:00",
        "user": {"id": 7, "nickname": nickname},
        "top_items": [],
    }


def claim_reply(status="success", error_message=None):
    return {
        "name": "newbie",
        "open_id": 123,
        "url": "https://hellcase.com/open/newbie",
        "status": status,
        "error_message": error_message,
    }


def weapon():
    return {
        "id": 123,
        "item_price": 0.03,
        "inventory_state": 0,
        "item_id": 4703,
        "case_id": 3527,
        "item_name": "MP7 | Forest DDPAT",
        "steam_market_hash_name": "MP7 | Forest DDPAT (Field-Tested)",
        "steam_url_title_name": "mp7-forest-ddpat",
        "steam_exterior": "Field-Tested",
        "steam_short_exterior": "FT",
        "skin_itemtype": "SMG",
        "is_stattrak": False,
        "weapon_name": "MP7",
        "skin_name": "Forest DDPAT",
        "rarity": "consumer",
        "steam_price_en": 0.03,
        "short_name": "MP7 | Forest DDPAT",
        "game": "csgo",
        "time_created": "2026-11-24T07:16:00.000000Z",
    }


def state_reply(bought=True, weapons=None):
    return {
        "status": "success",
        "bought": bought,
        "user_id": 7,
        "case_name": "newbie",
        "case_type": "user_level_free",
        "balance": 0.04,
        "balance_after_sell": 0.04,
        "user_wallet": {"coin": {"user_id": 7, "amount": 0.04}},
        "crypto_wallet": [],
        "shards": [],
        "event_tokens": [],
        "event_tokens_status": {},
        "weapons": [weapon()] if weapons is None else weapons,
    }


class FakeSession:
    def __init__(self, nickname="Alice", claim=None, state=None, fail=None):
        self.cookies = mock.Mock()
        self.headers = None
        self.fail = fail
        self.data = {
            d.API_URL: case_info(nickname),
            CLAIM_URL: claim or claim_reply(),
            STATE_URL: state or state_reply(),
        }

    def get(self, url, timeout=None):
        assert timeout == 30
        if url == self.fail:
            raise d.requests.RequestException("down")
        return mock.Mock(json=lambda: self.data[url])

    def post(self, url, json=None, timeout=None, headers=None):
        assert timeout == 30
        if url == self.fail:
            raise d.requests.RequestException("down")
        self.headers = headers
        return mock.Mock(json=lambda: self.data[url])


class DailyRewardTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def run_main(self, nickname="Alice", username="", claim=None, state=None,
                 fail=None, accounts=None):
        if accounts is None:
            accounts = [{"username": username, "xsrf": "xsrf-token", "session": "s"}]
        session = FakeSession(nickname, claim, state, fail)
        posts = []
        with mock.patch.object(d.requests, "session", return_value=session), \
             mock.patch.object(d.requests, "post",
                               side_effect=lambda url, json=None, timeout=None: posts.append(json["content"])), \
             mock.patch.object(d.time, "sleep"), \
             mock.patch.object(d, "load_json", side_effect=lambda path, default: (
                 {"discord_webhook_url": "https://example.invalid/hook", "accounts": accounts}
                 if path == "config.json" else default)):
            d.main()
        path = pathlib.Path("history.json")
        history = json.loads(path.read_text()) if path.exists() else []
        return history, posts, session

    def test_claim_then_state_records_skin_and_price(self):
        history, posts, session = self.run_main(username="Valmar")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["account"], "Valmar")
        self.assertEqual(history[0]["weapon"], "MP7 | Forest DDPAT")
        self.assertEqual(history[0]["skin"], "Forest DDPAT")
        self.assertEqual(history[0]["price"], 0.03)
        self.assertEqual(history[0]["rarity"], "consumer")
        self.assertEqual(history[0]["exterior"], "Field-Tested")
        self.assertEqual(history[0]["open_id"], 123)
        self.assertIn("MP7 | Forest DDPAT", posts[0])
        self.assertIn("0.03", posts[0])
        self.assertEqual(session.headers, {"X-CSRF-Token": "xsrf-token"})

    def test_configured_username_does_not_emit_nickname_warning(self):
        _, posts, _ = self.run_main(nickname="Bob", username="Bobby")
        self.assertEqual(len(posts), 1)
        self.assertNotIn("pseudo configuré", posts[0])
        self.assertIn("Bobby", posts[0])

    def test_empty_username_falls_back_to_api_nickname(self):
        history, _, _ = self.run_main(nickname="Alice")
        self.assertEqual(history[0]["account"], "Alice")

    def test_history_uses_local_run_time(self):
        clock = mock.Mock()
        clock.now.return_value.strftime.return_value = "2026-11-23 12:00:00"
        with mock.patch.object(d, "datetime", clock):
            history, _, _ = self.run_main()
        self.assertEqual(history[0]["date"], "2026-11-23 12:00:00")

    def test_failed_claim_is_not_recorded(self):
        history, posts, _ = self.run_main(claim=claim_reply(status="error"))
        self.assertEqual(history, [])
        self.assertEqual(len(posts), 1)
        self.assertIn("ouverture échouée", posts[0])

    def test_already_claimed_says_so_instead_of_blaming_token(self):
        claim = claim_reply(status="error", error_message="user_level.reward.already_claim")
        history, posts, _ = self.run_main(claim=claim)
        self.assertEqual(history, [])
        self.assertIn("déjà réclamée aujourd'hui", posts[0])
        self.assertNotIn("vérifie le token", posts[0])

    def test_state_without_weapon_is_not_recorded(self):
        history, posts, _ = self.run_main(state=state_reply(bought=False, weapons=[]))
        self.assertEqual(history, [])
        self.assertIn("gain non renseigné par l'API", posts[0])

    def test_failed_call_names_configured_user(self):
        _, posts, _ = self.run_main(username="Alice", fail=d.API_URL)
        self.assertEqual(len(posts), 1)
        self.assertIn("Alice", posts[0])
        self.assertIn("appel échoué", posts[0])

    def test_history_is_saved_after_each_account(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        with mock.patch.object(d.requests, "session",
                               side_effect=[FakeSession("Alice"), RuntimeError("boom")]), \
             mock.patch.object(d.requests, "post"), \
             mock.patch.object(d.time, "sleep"), \
             mock.patch.object(d, "load_json", side_effect=lambda path, default: (
                 {"discord_webhook_url": "", "accounts": accounts}
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

    def test_extract_drop_reads_state_weapon(self):
        drop = d.extract_drop(state_reply())
        self.assertEqual(drop["weapon"], "MP7 | Forest DDPAT")
        self.assertEqual(drop["price"], 0.03)
        self.assertEqual(drop["skin"], "Forest DDPAT")


if __name__ == "__main__":
    unittest.main()
