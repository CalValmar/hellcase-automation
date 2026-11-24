import fcntl
import json
import os
import random
import time
from datetime import datetime

import requests

API_URL = "https://api.hellcase.com/open/newbie"
CLAIM_URL = "https://api.hellcase.com/user_level/claim_free_case/newbie"
STATE_URL = "https://api.hellcase.com/open/newbie/state"


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


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
        label = account.get("username") or f"compte #{index}"
        try:
            info = session.get(API_URL, timeout=30).json()
            label = account.get("username") or (info.get("user") or {}).get("nickname") or label
            claim = session.post(CLAIM_URL, timeout=30,
                                 headers={"X-CSRF-Token": account["xsrf"]}).json()
            if claim.get("status") != "success" or not claim.get("open_id"):
                reason = claim.get("error_message") or "raison inconnue"
                if reason == "user_level.reward.already_claim":
                    notify(webhook, f"{label}: caisse déjà réclamée aujourd'hui")
                else:
                    notify(webhook, f"{label}: ouverture échouée — {reason}")
                continue
            state = session.get(STATE_URL, timeout=30).json()
        except (requests.RequestException, ValueError):
            notify(webhook, f"{label}: appel échoué — réseau ou réponse inattendue")
            continue

        drop = extract_drop(state) if state.get("status") == "success" and state.get("bought") else None
        if not drop or not drop["weapon"]:
            notify(webhook, f"{label}: gain non renseigné par l'API")
            continue

        history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account": label,
            "user_id": state.get("user_id"),
            "case": info.get("casename"),
            "weapon": drop["weapon"],
            "skin": drop["skin"],
            "price": drop["price"],
            "rarity": drop["rarity"],
            "exterior": drop["exterior"],
            "open_id": drop["open_id"],
        })

        with open("history.json.tmp", "w") as f:
            json.dump(history, f, indent=2)
        os.replace("history.json.tmp", "history.json")

        message = f"{label}: {drop['weapon']} — {drop['price']} $"
        if drop["skin"]:
            message += f" ({drop['skin']}, {drop['rarity']}, {drop['exterior']})"
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
