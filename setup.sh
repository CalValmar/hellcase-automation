#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

CONFIG_DIR="$HOME/.config/hellcase-automation"
STATE_DIR="$HOME/.local/state/hellcase-automation"
CONFIG_PATH="$CONFIG_DIR/config.json"
STATE_PATH="$STATE_DIR/state.json"
HISTORY_PATH="$STATE_DIR/history.json"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BLUE=$'\033[1;34m'
  GREEN=$'\033[1;32m'
  RED=$'\033[1;31m'
  RESET=$'\033[0m'
else
  BLUE= GREEN= RED= RESET=
fi

step_n=0
step() {
  step_n=$((step_n + 1))
  printf '%s[%d/8]%s %s\n' "$BLUE" "$step_n" "$RESET" "$*"
}

ok() {
  printf '%s  ✔ done%s\n' "$GREEN" "$RESET"
}

fail() {
  printf '%s✘ %s%s\n' "$RED" "$*" "$RESET" >&2
}

trap 'status=$?; fail "setup failed at line $LINENO (exit $status)"; exit "$status"' ERR

step "Stopping timer"
systemctl --user stop daily-reward.timer 2>/dev/null || true
systemctl --user clean --what=state daily-reward.timer 2>/dev/null || true
active_state=$(systemctl --user show -p ActiveState --value daily-reward.service 2>/dev/null || true)
if systemctl --user is-active --quiet daily-reward.service || [ "$active_state" = "activating" ]; then
  fail "daily-reward.service is still running; retry when it finishes"
  exit 1
fi
ok

step "Updating code and dependencies"
git pull --ff-only
python3 -m pip install --user requests
ok

step "Preparing directories and migrating legacy files"
mkdir -p "$CONFIG_DIR" "$STATE_DIR"
chmod 700 "$CONFIG_DIR" "$STATE_DIR"

migrate() {
  local src=$1 dst=$2
  [ -e "$src" ] || return 0
  if [ -e "$dst" ]; then
    echo "warning: $src exists but $dst already exists; left untouched" >&2
    return 0
  fi
  mv "$src" "$dst"
  chmod 600 "$dst"
}

migrate config.json "$CONFIG_PATH"
migrate history.json "$HISTORY_PATH"
migrate state.json "$STATE_PATH"
ok

step "Checking config"
if [ ! -f "$CONFIG_PATH" ]; then
  cp config.example.json "$CONFIG_PATH"
  chmod 600 "$CONFIG_PATH"
  fail "config created at $CONFIG_PATH: fill discord_webhook_url and accounts, then rerun ./setup.sh"
  exit 1
fi
chmod 600 "$CONFIG_PATH"
ok

step "Validating config"
python3 - "$CONFIG_PATH" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    config = json.load(f)
if not any(a.get("xsrf") and a.get("session") for a in config.get("accounts", [])):
    raise SystemExit("config.json needs at least one account with xsrf and session")
PY
ok

step "Running tests"
python3 -m unittest discover -s tests -t . -q
ok

step "Initialising state files"
touch "$HISTORY_PATH" "$STATE_PATH"
chmod 600 "$HISTORY_PATH" "$STATE_PATH"
ok

step "Installing systemd timer"
mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.service systemd/daily-reward.timer ~/.config/systemd/user/
sudo loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now daily-reward.timer
systemctl --user list-timers daily-reward.timer --no-pager
ok

printf '%s✔ setup complete%s\n' "$GREEN" "$RESET"
