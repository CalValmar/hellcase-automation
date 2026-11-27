import contextlib
import fcntl
import io
import json
import os
import pathlib
import re
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
        self.post_calls = []
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
        self.post_calls.append(url)
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
                 state_seed=None, sleep_calls=None, data_dir=None, save_json=None):
        if data_dir is None:
            data_dir = pathlib.Path(".")
        paths = {
            "config": str(data_dir / "config.json"),
            "history": str(data_dir / "history.json"),
            "state": str(data_dir / "state.json"),
            "lock": str(data_dir / "daily-reward.lock"),
        }
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
        real_load = d.load_json
        real_save = d.save_json

        def fake_load(path, default):
            if path == paths["config"]:
                return {"discord_webhook_url": "https://example.invalid/hook", "accounts": accounts}
            if path == paths["history"]:
                return history_seed if history_seed is not None else real_load(path, default)
            if path == paths["state"]:
                return state_seed if state_seed is not None else real_load(path, default)
            return default

        output = io.StringIO()
        with session_patch, \
             mock.patch.object(d.requests, "post",
                               side_effect=lambda url, json=None, timeout=None: posts.append(json["content"])), \
             mock.patch.object(d.time, "sleep", side_effect=sleep_calls.append), \
             mock.patch.object(d.random, "shuffle", side_effect=lambda items: None), \
             mock.patch.object(d, "load_json", side_effect=fake_load), \
             mock.patch.object(d, "save_json",
                               side_effect=save_json if save_json is not None else real_save,
                               create=True), \
             mock.patch.object(d, "CONFIG_PATH", paths["config"], create=True), \
             mock.patch.object(d, "HISTORY_PATH", paths["history"], create=True), \
             mock.patch.object(d, "STATE_PATH", paths["state"], create=True), \
             mock.patch.object(d, "LOCK_PATH", paths["lock"], create=True), \
             contextlib.redirect_stdout(output):
            d.main()
        self.console = output.getvalue().splitlines()
        path = pathlib.Path(paths["history"])
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
        clock.fromtimestamp.return_value.strftime.return_value = "2026-11-23"
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

    def test_already_claimed_is_silent_without_history(self):
        claim = claim_reply(status="error", error_message="user_level.reward.already_claim")
        history, posts, _ = self.run_main(claim=claim)
        self.assertEqual(history, [])
        self.assertEqual(posts, [])

    def test_already_claimed_does_not_stop_later_accounts(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        already = claim_reply(status="error", error_message="user_level.reward.already_claim")
        sessions = [FakeSession("Alice", claim=already), FakeSession("Bob")]
        history, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["account"], "Bob")
        self.assertEqual(len(posts), 1)
        self.assertIn("Bob", posts[0])
        self.assertNotIn(d.STATE_URL, sessions[0].get_calls)

    def test_state_without_weapon_is_not_recorded(self):
        history, posts, _ = self.run_main(state=state_reply(bought=False, weapons=[]))
        self.assertEqual(history, [])
        self.assertIn("gain non renseigné par l'API", posts[0])

    def test_missing_drop_alert_shows_open_id(self):
        _, posts, _ = self.run_main(state=state_reply(bought=False, weapons=[]))
        self.assertIn("open_id 123", posts[0])

    def test_state_failure_alert_shows_open_id(self):
        _, posts, _ = self.run_main(fail=d.STATE_URL)
        self.assertIn("appel échoué", posts[0])
        self.assertIn("open_id 123", posts[0])

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

    def test_history_write_failure_alerts_and_continues(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Alice"), FakeSession("Bob")]
        real_open = open

        def failing_open(path, *args, **kwargs):
            if path == "history.json.tmp":
                raise OSError("disk full")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=failing_open):
            history, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(history, [])
        self.assertEqual(len(posts), 2)
        self.assertIn("Alice", posts[0])
        self.assertIn("Bob", posts[1])
        self.assertIn("historique non écrit", posts[0])
        self.assertIn("open_id 123", posts[0])

    def test_state_write_failure_alert_shows_open_id(self):
        real_open = open

        def failing_open(path, *args, **kwargs):
            if path == "state.json.tmp":
                raise OSError("disk full")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=failing_open):
            _, posts, _ = self.run_main()
        self.assertIn("état local non écrit", posts[0])
        self.assertIn("open_id 123", posts[0])

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

    def test_non_dict_case_info_does_not_post_claim(self):
        accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
        session = FakeSession("Alice")
        session.data[d.API_URL] = []
        history, posts, session = self.run_main(accounts=accounts, sessions=session)
        self.assertEqual(session.post_calls.count(CLAIM_URL), 0)
        self.assertEqual(history, [])
        self.assertIn("appel échoué", posts[0])

    def test_network_error_on_state_is_retried_once(self):
        session = FakeSession(fail_once=STATE_URL)
        history, posts, session = self.run_main(sessions=session)
        self.assertEqual(len(history), 1)
        self.assertEqual(session.get_calls.count(STATE_URL), 2)
        self.assertFalse(any("appel échoué" in post for post in posts))

    def test_missing_config_fails_loudly(self):
        with mock.patch.object(d, "CONFIG_PATH", "missing-config.json", create=True):
            with self.assertRaises(SystemExit):
                d.main()

    def test_invalid_accounts_container_fails_loudly(self):
        path = pathlib.Path("config.json")
        path.write_text(json.dumps({"discord_webhook_url": "", "accounts": None}))
        with mock.patch.object(d, "CONFIG_PATH", str(path), create=True):
            with self.assertRaises(SystemExit):
                d.main()

    def test_lock_skips_second_run(self):
        lock = open("daily-reward.lock", "a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with mock.patch.object(d, "LOCK_PATH", "daily-reward.lock", create=True), \
                 mock.patch.object(d, "main") as fake_main:
                d.run_locked()
                fake_main.assert_not_called()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def test_default_paths_stay_outside_the_checkout(self):
        home = os.path.expanduser("~")
        config_dir = os.path.join(home, ".config", "hellcase-automation")
        state_dir = os.path.join(home, ".local", "state", "hellcase-automation")
        self.assertEqual(d.CONFIG_PATH, os.path.join(config_dir, "config.json"))
        self.assertEqual(d.STATE_PATH, os.path.join(state_dir, "state.json"))
        self.assertEqual(d.HISTORY_PATH, os.path.join(state_dir, "history.json"))
        self.assertEqual(d.LOCK_PATH, os.path.join(state_dir, "daily-reward.lock"))

    def test_lock_uses_configured_path_outside_cwd(self):
        data_dir = pathlib.Path(self.tmp.name) / "data"
        data_dir.mkdir()
        lock_path = data_dir / "daily-reward.lock"
        lock = open(lock_path, "a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with mock.patch.object(d, "LOCK_PATH", str(lock_path), create=True), \
                 mock.patch.object(d, "main") as fake_main:
                d.run_locked()
                fake_main.assert_not_called()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def test_config_state_and_history_use_configured_paths_outside_cwd(self):
        data_dir = pathlib.Path(self.tmp.name) / "data"
        data_dir.mkdir()
        history, _, _ = self.run_main(data_dir=data_dir)
        self.assertEqual(len(history), 1)
        self.assertTrue((data_dir / "state.json").exists())
        self.assertTrue((data_dir / "history.json").exists())
        self.assertFalse(pathlib.Path("state.json").exists())
        self.assertFalse(pathlib.Path("history.json").exists())

    def test_extract_drop_reads_state_weapon(self):
        drop = d.extract_drop(state_reply())
        self.assertEqual(drop["weapon"], "MP7 | Forest DDPAT")
        self.assertEqual(drop["price"], 0.03)
        self.assertEqual(drop["skin"], "Forest DDPAT")

    def test_state_file_is_private_and_records_last_claim(self):
        self.run_main()
        path = pathlib.Path("state.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        state = json.loads(path.read_text())
        self.assertIn("1", state)
        self.assertIsInstance(state["1"]["last_claim"], (int, float))

    def test_already_claim_records_last_claim_without_alert(self):
        claim = claim_reply(status="error", error_message="user_level.reward.already_claim")
        _, posts, _ = self.run_main(claim=claim)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(posts, [])
        self.assertIsInstance(state["1"]["last_claim"], (int, float))

    def test_recent_claim_is_not_due(self):
        accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
        state = {"1": {"last_claim": d.time.time() - 3600}}
        self.assertEqual(d.due_accounts(accounts, state, d.time.time()), [])

    def test_due_accounts_are_shuffled_and_limited_to_two(self):
        accounts = [{"username": str(i), "xsrf": "x", "session": "s"} for i in range(1, 6)]
        with mock.patch.object(d.random, "shuffle", side_effect=lambda items: items.reverse()):
            picked = d.due_accounts(accounts, {}, d.time.time())
        self.assertEqual([index for index, _, _ in picked], [5, 4])

    def test_run_claims_at_most_two_accounts(self):
        accounts = [{"username": str(i), "xsrf": "x", "session": "s"} for i in range(1, 6)]
        sessions = [FakeSession(str(i)) for i in range(1, 6)]
        sleep_calls = []
        history, posts, _ = self.run_main(accounts=accounts, sessions=sessions,
                                          sleep_calls=sleep_calls)
        self.assertEqual(len(history), 2)
        self.assertEqual(len(posts), 2)
        self.assertEqual(len(sleep_calls), 1)
        self.assertEqual(sleep_calls[0], 300)

    def test_empty_history_file_is_ignored(self):
        pathlib.Path("history.json").write_text("")
        self.run_main()
        history = json.loads(pathlib.Path("history.json").read_text())
        self.assertEqual(len(history), 1)

    def test_corrupt_history_is_renamed_and_not_overwritten(self):
        pathlib.Path("history.json").write_text("{broken")
        self.run_main()
        self.assertEqual(pathlib.Path("history.json.corrupt").read_text(), "{broken")
        history = json.loads(pathlib.Path("history.json").read_text())
        self.assertEqual(len(history), 1)

    def test_corrupt_history_alert_marker_is_persisted_without_due_accounts(self):
        pathlib.Path("history.json").write_text("{broken")
        accounts = [{"username": "Alice", "xsrf": "xsrf-token", "session": "s"}]
        state_seed = {"1": {"last_claim": d.time.time() - 3600}}
        self.run_main(accounts=accounts, state_seed=state_seed)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["_history"]["last_error_day"],
                         datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def test_empty_state_file_is_ignored(self):
        pathlib.Path("state.json").write_text("")
        self.run_main()
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertIn("1", state)

    def test_wrong_state_shape_does_not_abort(self):
        history, posts, _ = self.run_main(state_seed={"1": 5})
        self.assertEqual(len(history), 1)
        self.assertEqual(len(posts), 1)

    def test_recent_attempt_is_not_due(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state = {"1": {"last_attempt_day": today}}
        accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
        self.assertEqual(d.due_accounts(accounts, state, d.time.time()), [])

    def test_network_error_before_claim_does_not_consume_the_day(self):
        accounts = [{"username": "Alice", "xsrf": "xsrf-token", "session": "s"}]
        self.run_main(accounts=accounts, fail=d.API_URL)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(d.due_accounts(accounts, state, d.time.time()),
                         [(1, accounts[0], "1")])

    def test_failure_alert_is_deduplicated_per_utc_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state = {"1": {"last_error_day": today}}
        _, posts, _ = self.run_main(fail=d.API_URL, state_seed=state)
        self.assertEqual(posts, [])

    def test_utc_day_is_recomputed_after_delay(self):
        start = datetime(2026, 11, 24, 23, 59, 50, tzinfo=timezone.utc).timestamp()
        accounts = [{"username": str(i), "xsrf": "x", "session": "s"} for i in (1, 2)]
        sessions = [FakeSession("1"), FakeSession("2")]
        times = [start, start, start + 200, start + 200, start + 200]
        with mock.patch.object(d.time, "time", side_effect=times):
            self.run_main(accounts=accounts, sessions=sessions)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["2"]["last_attempt_day"], "2026-11-25")

    def test_last_claim_uses_claim_time_not_run_start(self):
        start = 1_800_000_000
        times = [start, start, start + 190]
        with mock.patch.object(d.time, "time", side_effect=times):
            self.run_main()
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["1"]["last_claim"], start + 190)

    def test_console_line_carries_timestamp_user_and_event(self):
        clock = mock.Mock()
        clock.now.return_value = datetime(2026, 11, 27, 9, 14, 2)
        output = io.StringIO()
        with mock.patch.object(d, "datetime", clock), contextlib.redirect_stdout(output):
            d.log("Alice: drop — MP7 | Forest DDPAT, 0.03 $")
        self.assertEqual(
            output.getvalue(),
            "[2026-11-27 09:14:02] Alice: drop — MP7 | Forest DDPAT, 0.03 $\n",
        )

    def test_console_shows_each_api_step_and_the_drop(self):
        _, posts, _ = self.run_main(username="Valmar")
        self.assertTrue(all(re.match(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] ", line)
                            for line in self.console))
        for expected in ("Valmar: GET /open/newbie",
                         "Valmar: POST claim",
                         "Valmar: ouverture OK (open_id 123)",
                         "Valmar: GET /open/newbie/state",
                         "Valmar: MP7 | Forest DDPAT — 0.03 $"):
            self.assertTrue(any(expected in line for line in self.console), expected)
        self.assertEqual(len(posts), 1)

    def test_console_shows_failure_even_when_discord_alert_is_suppressed(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _, posts, _ = self.run_main(fail=d.API_URL,
                                    state_seed={"1": {"last_error_day": today}})
        self.assertEqual(posts, [])
        self.assertTrue(any("compte #1: appel échoué" in line
                            for line in self.console))

    def test_console_says_when_no_account_is_due(self):
        self.run_main(state_seed={"1": {"last_claim": d.time.time() - 3600}})
        self.assertTrue(any("aucun compte à traiter" in line
                            for line in self.console))

    def test_cookie_contract_is_sent_on_the_session(self):
        _, _, session = self.run_main(username="Valmar")
        session.cookies.update.assert_called_once_with({
            "XSRF-TOKEN": "xsrf-token",
            "hellcase_session": "s",
        })

    def test_claim_without_open_id_is_an_alert(self):
        claim = claim_reply()
        del claim["open_id"]
        history, posts, _ = self.run_main(claim=claim)
        self.assertEqual(history, [])
        self.assertIn("ouverture échouée", posts[0])
        self.assertIn("raison inconnue", posts[0])

    def test_state_with_bought_false_has_no_drop(self):
        history, posts, _ = self.run_main(state=state_reply(bought=False))
        self.assertEqual(history, [])
        self.assertIn("gain non renseigné par l'API", posts[0])

    def test_weapon_without_name_has_no_drop(self):
        history, posts, _ = self.run_main(state=state_reply(weapons=[{}]))
        self.assertEqual(history, [])
        self.assertIn("gain non renseigné par l'API", posts[0])

    def test_non_dict_claim_response_does_not_crash(self):
        session = FakeSession()
        session.data[CLAIM_URL] = []
        history, posts, _ = self.run_main(sessions=session)
        self.assertEqual(history, [])
        self.assertIn("appel échoué", posts[0])

    def test_non_dict_state_response_keeps_open_id_in_alert(self):
        session = FakeSession()
        session.data[STATE_URL] = []
        history, posts, _ = self.run_main(sessions=session)
        self.assertEqual(history, [])
        self.assertIn("appel échoué", posts[0])
        self.assertIn("open_id 123", posts[0])

    def test_unreadable_post_response_alerts_without_a_drop(self):
        session = FakeSession()

        def bad_post(url, **kwargs):
            self.assertEqual(url, CLAIM_URL)
            return mock.Mock(json=mock.Mock(side_effect=ValueError("bad json")))

        session.post = bad_post
        history, posts, _ = self.run_main(sessions=session)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(history, [])
        self.assertIn("appel échoué", posts[0])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(state["1"]["last_attempt_day"], today)

    def test_get_json_retries_invalid_json(self):
        session = FakeSession()
        real_get = session.get
        calls = []

        def flaky_get(url, timeout=None):
            calls.append(url)
            if url == d.API_URL and calls.count(d.API_URL) == 1:
                return mock.Mock(json=mock.Mock(side_effect=ValueError("bad json")))
            return real_get(url, timeout=timeout)

        session.get = flaky_get
        history, posts, _ = self.run_main(sessions=session)
        self.assertEqual(calls.count(d.API_URL), 2)
        self.assertEqual(len(history), 1)
        self.assertFalse(any("appel échoué" in post for post in posts))

    def test_get_json_alerts_after_two_invalid_json_responses(self):
        session = FakeSession()
        real_get = session.get
        calls = []

        def bad_get(url, timeout=None):
            calls.append(url)
            if url == d.API_URL:
                return mock.Mock(json=mock.Mock(side_effect=ValueError("bad json")))
            return real_get(url, timeout=timeout)

        session.get = bad_get
        history, posts, _ = self.run_main(sessions=session)
        self.assertEqual(calls.count(d.API_URL), 2)
        self.assertEqual(history, [])
        self.assertIn("appel échoué", posts[0])

    def test_yesterday_attempt_is_due(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        with mock.patch.object(d, "datetime") as clock:
            clock.fromtimestamp.return_value = datetime(2026, 11, 27, tzinfo=timezone.utc)
            accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
            state = {"1": {"last_attempt_day": yesterday}}
            self.assertEqual(d.due_accounts(accounts, state, 0),
                             [(1, accounts[0], "1")])

    def test_non_numeric_last_claim_is_ignored(self):
        accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
        state = {"1": {"last_claim": "hier"}}
        self.assertEqual(d.due_accounts(accounts, state, d.time.time()),
                         [(1, accounts[0], "1")])

    def test_cooldown_boundary_is_due(self):
        now = d.time.time()
        accounts = [{"username": "Alice", "xsrf": "x", "session": "s"}]
        state = {"1": {"last_claim": now - d.COOLDOWN}}
        self.assertEqual(d.due_accounts(accounts, state, now),
                         [(1, accounts[0], "1")])

    def test_alert_keeps_marker_when_webhook_is_deduplicated(self):
        state = {}
        with mock.patch.object(d, "notify") as notify, \
             contextlib.redirect_stdout(io.StringIO()):
            d.alert("hook", state, "1", "2026-11-27", "panne")
            d.alert("hook", state, "1", "2026-11-27", "panne")
        self.assertEqual(state["1"]["last_error_day"], "2026-11-27")
        notify.assert_called_once_with("hook", "panne")

    def test_webhook_errors_are_ignored(self):
        with mock.patch.object(d.requests, "post",
                               side_effect=d.requests.RequestException("down")):
            d.notify("https://example.invalid/hook", "message")

    def test_two_failed_accounts_alert_separately(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Alice", fail=d.API_URL),
                    FakeSession("Bob", fail=d.API_URL)]
        _, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(len(posts), 2)
        self.assertIn("Alice", posts[0])
        self.assertIn("Bob", posts[1])

    def test_top_level_state_and_history_shapes_are_ignored(self):
        pathlib.Path("state.json").write_text("[]")
        pathlib.Path("history.json").write_text("{}")
        with mock.patch.object(d, "STATE_PATH", "state.json", create=True), \
             mock.patch.object(d, "HISTORY_PATH", "history.json", create=True):
            self.assertEqual(d.load_state(), {})
            self.assertEqual(d.load_history(), [])

    def test_history_records_case_name_and_console_counts_accounts(self):
        history, _, _ = self.run_main()
        self.assertEqual(history[0]["case"], "Newbie")
        self.assertTrue(any("exécution — 1 compte(s) à traiter" in line
                            for line in self.console))

    def test_state_write_failure_keeps_the_drop(self):
        real_open = open

        def failing_open(path, *args, **kwargs):
            if path == "state.json.tmp":
                raise OSError("disk full")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=failing_open):
            history, posts, _ = self.run_main()
        self.assertEqual(len(history), 1)
        self.assertTrue(any("MP7 | Forest DDPAT" in post for post in posts))
        self.assertTrue(any("état local non écrit" in line
                            for line in self.console))

    def test_history_is_written_before_state(self):
        calls = []

        def save(path, data):
            calls.append(os.path.basename(path))
            if path == "state.json":
                raise RuntimeError("crash between writes")
            with open(path, "w") as f:
                json.dump(data, f)

        with self.assertRaises(RuntimeError):
            self.run_main(save_json=save)
        self.assertEqual(calls[0], "history.json")
        self.assertTrue(pathlib.Path("history.json").exists())
        self.assertFalse(pathlib.Path("state.json").exists())

    def test_invalid_config_json_exits_cleanly(self):
        path = pathlib.Path("config.json")
        path.write_text("{broken")
        with mock.patch.object(d, "CONFIG_PATH", str(path), create=True):
            with self.assertRaises(SystemExit) as caught:
                d.main()
        self.assertIn("invalide", str(caught.exception))

    def test_malformed_account_is_not_retried_the_same_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        accounts = [
            {"username": "Broken"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Broken"), FakeSession("Bob")]
        _, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["1"]["last_attempt_day"], today)
        self.assertEqual(state["1"]["last_error_day"], today)
        self.assertEqual(len(posts), 2)

    def test_positive_lock_calls_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = pathlib.Path(tmp) / "daily-reward.lock"
            with mock.patch.object(d, "LOCK_PATH", str(lock), create=True), \
                 mock.patch.object(d, "main") as fake_main:
                d.run_locked()
        fake_main.assert_called_once_with()

    def test_failed_history_write_does_not_leak_row_into_next_account(self):
        accounts = [
            {"username": "Alice", "xsrf": "x", "session": "s"},
            {"username": "Bob", "xsrf": "x", "session": "s"},
        ]
        sessions = [FakeSession("Alice"), FakeSession("Bob")]
        real_open = open
        failures = []

        def flaky_open(path, *args, **kwargs):
            if path == "history.json.tmp":
                failures.append(path)
                if len(failures) == 1:
                    raise OSError("disk full")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=flaky_open):
            history, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["account"], "Bob")
        self.assertTrue(any("historique non écrit" in post and "Alice" in post
                            for post in posts))

    def test_non_dict_account_is_not_retried_the_same_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        accounts = ["alice", {"username": "Bob", "xsrf": "x", "session": "s"}]
        sessions = [FakeSession("alice"), FakeSession("Bob")]
        _, posts, _ = self.run_main(accounts=accounts, sessions=sessions)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["1"]["last_attempt_day"], today)
        self.assertEqual(len(posts), 2)

    def test_broken_api_user_shape_is_not_retried_the_same_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session = FakeSession()
        session.data[d.API_URL] = {"user": "oops"}
        _, posts, _ = self.run_main(sessions=session)
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(state["1"]["last_attempt_day"], today)
        self.assertIn("appel échoué", posts[0])
        self.assertEqual(session.post_calls.count(CLAIM_URL), 0)

    def test_non_dict_special_state_record_does_not_abort(self):
        pathlib.Path("history.json").write_text("{broken")
        _, posts, _ = self.run_main(state_seed={"_history": 5})
        state = json.loads(pathlib.Path("state.json").read_text())
        self.assertEqual(pathlib.Path("history.json.corrupt").read_text(), "{broken")
        self.assertIsInstance(state["_history"], dict)
        self.assertIn("last_error_day", state["_history"])
        self.assertTrue(posts)

    def test_corrupt_history_backup_is_not_clobbered(self):
        pathlib.Path("history.json").write_text("{first")
        self.run_main(state_seed={})
        pathlib.Path("history.json").write_text("{second")
        self.run_main(state_seed={})
        self.assertEqual(pathlib.Path("history.json.corrupt").read_text(), "{first")
        self.assertEqual(len(json.loads(pathlib.Path("history.json").read_text())), 1)


if __name__ == "__main__":
    unittest.main()
