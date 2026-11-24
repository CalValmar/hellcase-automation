import fcntl
import json
import os
import pathlib
import stat
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


def state_reply(bought=True, weapons=None, status="success"):
    return {
        "status": status,
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
    def __init__(self, nickname="Alice", claim=None, state=None, fail=None, fail_once=None):
        self.cookies = mock.Mock()
        self.headers = None
        self.fail = fail
        self.fail_once = fail_once
        self.get_calls = []
        self.data = {
            d.API_URL: case_info(nickname),
            CLAIM_URL: claim or claim_reply(),
            STATE_URL: state or state_reply(),
        }

    def get(self, url, timeout=None):
        assert timeout == 30
        self.get_calls.append(url)
        if url == self.fail_once:
            self.fail_once = None
            raise d.requests.RequestException("down")
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
                 fail=None, accounts=None, sessions=None, history_seed=None,
                 sleep_calls=None):
        if accounts is None:
            accounts = [{"username": username, "xsrf": "xsrf-token", "session": "s"}]
        if sessions is None:
            sessions = FakeSession(nickname, claim, state, fail)
        if isinstance(sessions, list):
            session = sessions[0]
            session_patch = mock.patch.object(d.requests, "session", side_effect=sessions)
        else:
            session = sessions
            session_patch = mock.patch.object(d.requests, "session", return_value=session)
        posts = []
        sleep_calls = [] if sleep_calls is None else sleep_calls

        def fake_load(path, default):
            if path == "config.json":
                return {"discord_webhook_url": "https://example.invalid/hook", "accounts": accounts}
            if path == "history.json" and history_seed is not None:
                return history_seed
            return default

        with session_patch, \
             mock.patch.object(d.requests, "post",
                               side_effect=lambda url, json=None, timeout=None: posts.append(json["content"])), \
             mock.patch.object(d.time, "sleep", side_effect=sleep_calls.append), \
             mock.patch.object(d, "load_json", side_effect=fake_load):
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

    def test_configured_username_is_used_instead_of_api_nickname(self):
        history, posts, _ = self.run_main(nickname="API-Nick", username="Bobby")
        self.assertIn("Bobby", posts[0])
        self.assertNotIn("API-Nick", posts[0])
        self.assertEqual(history[0]["account"], "Bobby")

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
        self.assertIn("raison inconnue", posts[0])
        self.assertNotIn("vérifie le token", posts[0])

    def test_unknown_api_error_is_shown_verbatim(self):
        _, posts, _ = self.run_main(claim=claim_reply(
            status="error", error_message="user_level.not_allowed"))
        self.assertIn("user_level.not_allowed", posts[0])
        self.assertNotIn("vérifie le token", posts[0])

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
        self.assertIn("réseau ou réponse inattendue", posts[0])
        self.assertNotIn("vérifie le token", posts[0])

    def test_history_is_saved_after_each_account(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Alice"), FakeSession("Bob", claim=claim_reply(status="error"))]
        history, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["account"], "Alice")
        self.assertEqual(len(posts), 2)

    def test_history_file_is_private(self):
        self.run_main()
        mode = stat.S_IMODE(pathlib.Path("history.json").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_existing_history_is_preserved(self):
        old = [{"account": "Old", "weapon": "AK", "price": 1.0}]
        history, _, _ = self.run_main(history_seed=old)
        self.assertEqual(history[0], old[0])
        self.assertEqual(len(history), 2)

    def test_zero_steam_price_is_not_replaced_by_fallback(self):
        weapon_data = weapon()
        weapon_data["steam_price_en"] = 0
        drop = d.extract_drop({"weapons": [weapon_data]})
        self.assertEqual(drop["price"], 0)

    def test_network_error_on_info_is_retried_once(self):
        session = FakeSession(fail_once=d.API_URL)
        history, posts, _ = self.run_main(sessions=session)
        self.assertEqual(len(history), 1)
        self.assertEqual(session.get_calls.count(d.API_URL), 2)
        self.assertEqual(len(posts), 1)

    def test_delay_applies_after_failed_account(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Alice", claim=claim_reply(status="error")), FakeSession("Bob")]
        sleep_calls = []
        history, posts, _ = self.run_main(accounts=accounts, sessions=sessions,
                                          sleep_calls=sleep_calls)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(posts), 2)
        self.assertEqual(len(sleep_calls), 1)

    def test_malformed_account_does_not_stop_later_accounts(self):
        accounts = [
            {"username": "Broken"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Broken"), FakeSession("Bob")]
        history, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(len(posts), 2)
        self.assertIn("Broken", posts[0])
        self.assertEqual(history[0]["account"], "Bob")

    def test_non_dict_api_response_does_not_stop_later_accounts(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        first = FakeSession("Alice")
        first.data[d.API_URL] = []
        history, posts, _ = self.run_main(accounts=accounts,
                                          sessions=[first, FakeSession("Bob")])
        self.assertEqual(len(posts), 2)
        self.assertIn("appel échoué", posts[0])
        self.assertEqual(history[0]["account"], "Bob")

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
