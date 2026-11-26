import fcntl
import json
import os
import random
import time
from datetime import datetime, timezone

import requests

API_URL = "https://api.hellcase.com/open/newbie"
CLAIM_URL = "https://api.hellcase.com/user_level/claim_free_case/newbie"
STATE_URL = "https://api.hellcase.com/open/newbie/state"
COOLDOWN = 24 * 3600 + 60
MAX_PER_RUN = 2
CONFIG_PATH = os.path.expanduser("~/.config/hellcase-automation/config.json")
STATE_PATH = os.path.expanduser("~/.local/state/hellcase-automation/state.json")
HISTORY_PATH = os.path.expanduser("~/.local/state/hellcase-automation/history.json")
LOCK_PATH = os.path.expanduser("~/.local/state/hellcase-automation/daily-reward.lock")


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def get_json(session, url):
    # Read-only GETs are retried once: network-online.target does not guarantee DNS here.
    for attempt in range(2):
        try:
            return session.get(url, timeout=30).json()
        except requests.RequestException:
            if attempt:
                raise


def utc_day(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def load_state():
    try:
        data = load_json(STATE_PATH, {})
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def load_history():
    try:
        data = load_json(HISTORY_PATH, [])
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def extract_drop(data):
    weapons = data.get("weapons") or []
    if not weapons:
        return None
    item = weapons[0]
    price = item.get("steam_price_en")
    if price is None:
        price = item.get("item_price")
    return {
        "weapon": item.get("item_name"),
        "skin": item.get("skin_name"),
        "price": price,
        "rarity": item.get("rarity"),
        "exterior": item.get("steam_exterior"),
        "open_id": item.get("id"),
    }


def notify(webhook, message):
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": message}, timeout=10)
    except requests.RequestException:
        pass


def alert(webhook, state, key, day, message):
    record = state.setdefault(key, {})
    if record.get("last_error_day") == day:
        return
    record["last_error_day"] = day
    notify(webhook, message)


def due_accounts(accounts, state, now):
    day = utc_day(now)
    picked = []
    for index, account in enumerate(accounts, 1):
        key = str(index)
        record = state.get(key)
        if not isinstance(record, dict):
            record = state[key] = {}
        last = record.get("last_claim")
        if isinstance(last, (int, float)) and now - last < COOLDOWN:
            continue
        if record.get("last_attempt_day") == day:
            continue
        picked.append((index, account, key))
    random.shuffle(picked)
    return picked[:MAX_PER_RUN]


def main():
    config = load_json(CONFIG_PATH, None)
    if not isinstance(config, dict):
        raise SystemExit("config.json introuvable ou invalide")
    webhook = config.get("discord_webhook_url")
    accounts = config.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise SystemExit("config.json: 'accounts' doit contenir au moins un compte")
    history = load_history()
    state = load_state()
    now = time.time()
    first = True

    for index, account, key in due_accounts(accounts, state, now):
        if not first:
            time.sleep(random.uniform(30, 180))
        first = False
        day = utc_day(time.time())
        label = f"compte #{index}"
        open_id = None
        state.setdefault(key, {})["last_attempt_day"] = day
        try:
            label = account.get("username") or label
            session = requests.session()
            session.cookies.update({
                "XSRF-TOKEN": account["xsrf"],
                "hellcase_session": account["session"],
            })
            info = get_json(session, API_URL)
            if not isinstance(info, dict):
                raise ValueError("case info inattendu")
            label = account.get("username") or (info.get("user") or {}).get("nickname") or label
            claim = session.post(CLAIM_URL, timeout=30,
                                 headers={"X-CSRF-Token": account["xsrf"]}).json()
            if claim.get("status") != "success" or not claim.get("open_id"):
                reason = claim.get("error_message") or "raison inconnue"
                if reason == "user_level.reward.already_claim":
                    # Covers a claim made in the browser: no second POST for 24h.
                    state[key]["last_claim"] = time.time()
                else:
                    alert(webhook, state, key, day, f"{label}: ouverture échouée — {reason}")
                continue
            state[key]["last_claim"] = time.time()
            open_id = claim.get("open_id")
            state_reply = get_json(session, STATE_URL)
            drop = extract_drop(state_reply) if state_reply.get("status") == "success" and state_reply.get("bought") else None

            if not drop or not drop["weapon"]:
                alert(webhook, state, key, day, f"{label}: gain non renseigné par l'API (open_id {open_id})")
                continue

            history.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "account": label,
                "user_id": state_reply.get("user_id"),
                "case": info.get("casename"),
                "weapon": drop["weapon"],
                "skin": drop["skin"],
                "price": drop["price"],
                "rarity": drop["rarity"],
                "exterior": drop["exterior"],
                "open_id": drop["open_id"],
            })
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            detail = f" (open_id {open_id})" if open_id else ""
            alert(webhook, state, key, day,
                  f"{label}: appel échoué — réseau ou réponse inattendue{detail}")
            continue
        finally:
            try:
                save_json(STATE_PATH, state)
            except OSError:
                detail = f" (open_id {open_id})" if open_id else ""
                notify(webhook, f"{label}: état local non écrit — disque ou permissions{detail}")

        try:
            save_json(HISTORY_PATH, history)
        except OSError:
            alert(webhook, state, key, day,
                  f"{label}: historique non écrit — disque ou permissions (open_id {open_id})")
            continue

        message = f"{label}: {drop['weapon']} — {drop['price']} $"
        if drop["skin"]:
            message += f" ({drop['skin']}, {drop['rarity']}, {drop['exterior']})"
        notify(webhook, message)


def run_locked():
    try:
        with open(LOCK_PATH, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main()
    except BlockingIOError:
        pass


if __name__ == "__main__":
    run_locked()
