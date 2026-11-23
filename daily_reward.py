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
    accounts = load_json("accounts.json", [])
    secrets = load_json("secrets.json", {})
    webhook = secrets.get("discord_webhook_url")
    history = load_json("history.json", [])

    for account in accounts:
        session = requests.session()
        session.cookies.update({
            "XSRF-TOKEN": account["xsrf"],
            "hellcase_session": account["session"],
        })
        try:
            response = session.get(API_URL, timeout=30)
            data = response.json()
        except (requests.RequestException, ValueError):
            notify(webhook, f"{account['name']}: appel échoué")
            continue

        user_id = (data.get("user") or {}).get("id")
        weapon, price = extract_drop(data, user_id)
        history.append({
            "date": data.get("last_open_date"),
            "account": account["name"],
            "user_id": user_id,
            "case": data.get("casename"),
            "weapon": weapon,
            "price": price,
        })
        if weapon:
            notify(webhook, f"{account['name']}: {weapon} — {price}")
        time.sleep(random.uniform(5, 20))

    with open("history.json.tmp", "w") as f:
        json.dump(history, f, indent=2)
    os.replace("history.json.tmp", "history.json")


if __name__ == "__main__":
    main()
