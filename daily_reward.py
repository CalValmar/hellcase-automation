import fcntl
import json
import os
import random
import time

import requests

API_URL = "https://api.hellcase.com/open/newbie"


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def extract_drop(data, user_id):
    # shortcut: only matches drops listed in top_items for the current user, upgrade when the real drop field is known
    for entry in data.get("top_items", []):
        if (entry.get("user") or {}).get("id") != user_id:
            continue
        for item in entry.get("items", []):
            if item.get("drop_type") == "item":
                return item.get("weapon_name"), entry.get("steam_price_en")
    return None, None


def notify(webhook, message):
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": message}, timeout=10)
    except requests.RequestException:
        pass


def main():
    config = load_json("config.json", {})
    webhook = config.get("discord_webhook_url")
    accounts = config.get("accounts", [])
    history = load_json("history.json", [])

    for index, account in enumerate(accounts, 1):
        session = requests.session()
        session.cookies.update({
            "XSRF-TOKEN": account["xsrf"],
            "hellcase_session": account["session"],
        })
        try:
            response = session.get(API_URL, timeout=30)
            data = response.json()
        except (requests.RequestException, ValueError):
            name = account.get("username") or f"Compte #{index}"
            notify(webhook, f"{name}: appel échoué — vérifie le token")
            continue

        user = data.get("user") or {}
        nickname = user.get("nickname")
        configured = account.get("username")
        label = configured or nickname or f"compte #{index}"
        if data.get("status") != "success" or data.get("case_is_opened") is False:
            notify(webhook, f"{label}: ouverture échouée — vérifie le token")
            continue
        if configured and nickname and configured != nickname:
            notify(webhook, f"{label}: pseudo configuré « {configured} » ≠ pseudo Hellcase « {nickname} » — vérifie les tokens")
        user_id = user.get("id")
        weapon, price = extract_drop(data, user_id)
        history.append({
            "date": data.get("last_open_date"),
            "account": label,
            "user_id": user_id,
            "case": data.get("casename"),
            "weapon": weapon,
            "price": price,
        })

        with open("history.json.tmp", "w") as f:
            json.dump(history, f, indent=2)
        os.replace("history.json.tmp", "history.json")

        message = f"{label}: {data.get('status')}"
        if weapon:
            message += f" — {weapon} ({price})"
        notify(webhook, message)
        if index < len(accounts):
            time.sleep(random.uniform(5, 20))


def run_locked():
    try:
        with open("daily-reward.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main()
    except BlockingIOError:
        pass


if __name__ == "__main__":
    run_locked()
