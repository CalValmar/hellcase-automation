#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

git pull --ff-only
python3 -m pip install --user requests

if [ ! -f config.json ]; then
  cp config.example.json config.json
  chmod 600 config.json
  echo "config.json created: fill discord_webhook_url and accounts, then rerun ./setup.sh" >&2
  exit 1
fi
chmod 600 config.json

python3 - <<'PY'
import json
config = json.load(open("config.json"))
if not any(a.get("xsrf") and a.get("session") for a in config.get("accounts", [])):
    raise SystemExit("config.json needs at least one account with xsrf and session")
PY

python3 -m unittest -q test_daily_reward

touch history.json state.json
chmod 600 config.json history.json state.json

mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.service systemd/daily-reward.timer ~/.config/systemd/user/
sudo loginctl enable-linger "$(id -un)"

systemctl --user stop daily-reward.timer 2>/dev/null || true
systemctl --user clean --what=state daily-reward.timer 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now daily-reward.timer
systemctl --user list-timers daily-reward.timer --no-pager
