#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

if [ "$#" -gt 1 ]; then
  printf 'usage: %s [--system]\n' "$0" >&2
  exit 2
fi

MODE=user
case "${1:-}" in
  "") ;;
  --system) MODE=system ;;
  *) printf 'usage: %s [--system]\n' "$0" >&2; exit 2 ;;
esac

if [ "$MODE" = system ] && [ "$(id -u)" -ne 0 ]; then
  printf '%s✘ --system must be run as root%s\n' "${RED:-}" "${RESET:-}" >&2
  exit 1
fi

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

svc_systemctl() {
  if [ "$MODE" = system ]; then
    systemctl "$@"
  else
    systemctl --user "$@"
  fi
}

if [ "$MODE" = system ]; then
  SERVICE_USER=hellcase
  SERVICE_HOME=/var/lib/hellcase
  CONFIG_DIR="$SERVICE_HOME/.config/hellcase-automation"
  STATE_DIR="$SERVICE_HOME/.local/state/hellcase-automation"
  UNIT_DIR=/etc/systemd/system
  UNIT_SRC=systemd/system
  PYTHON="$PWD/.venv/bin/python"
else
  SERVICE_USER="$(id -un)"
  SERVICE_HOME="$HOME"
  CONFIG_DIR="$HOME/.config/hellcase-automation"
  STATE_DIR="$HOME/.local/state/hellcase-automation"
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_SRC=systemd
  PYTHON=/usr/bin/python3
fi

CONFIG_PATH="$CONFIG_DIR/config.json"
STATE_PATH="$STATE_DIR/state.json"
HISTORY_PATH="$STATE_DIR/history.json"

if [ "$MODE" = system ]; then
  [ "$PWD" = /opt/hellcase-automation ] || {
    fail "system mode must be run from /opt/hellcase-automation"
    exit 1
  }
  for home in /home/* /root /var/lib/hellcase; do
    if [ -e "$home/.config/systemd/user/daily-reward.timer" ]; then
      fail "a daily-reward.timer user unit still exists; disable it before --system"
      exit 1
    fi
  done
elif [ -e /etc/systemd/system/daily-reward.timer ]; then
  fail "a daily-reward.timer system unit exists; uninstall it before user setup"
  exit 1
fi

step "Checking timer state"
active_state=$(svc_systemctl show -p ActiveState --value daily-reward.service 2>/dev/null || true)
if svc_systemctl is-active --quiet daily-reward.service || [ "$active_state" = "activating" ]; then
  fail "daily-reward.service is still running; retry when it finishes"
  exit 1
fi
ok

step "Updating code and dependencies"
if [ "$MODE" = system ]; then
  # shortcut: system mode never runs git pull; update /opt/hellcase-automation explicitly first.
  python3 -m venv .venv
  "$PYTHON" -m pip install requests
else
  git pull --ff-only
  "$PYTHON" -m pip install --user requests
fi
ok

step "Preparing directories and migrating legacy files"
if [ "$MODE" = system ]; then
  if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$SERVICE_HOME" --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
  install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$CONFIG_DIR" "$STATE_DIR"
else
  mkdir -p "$CONFIG_DIR" "$STATE_DIR"
  chmod 700 "$CONFIG_DIR" "$STATE_DIR"
fi

migrate() {
  local src=$1 dst=$2
  [ -e "$src" ] || return 0
  if [ -e "$dst" ]; then
    echo "warning: $src exists but $dst already exists; left untouched" >&2
    return 0
  fi
  mv "$src" "$dst"
  chmod 600 "$dst"
  if [ "$MODE" = system ]; then
    chown "$SERVICE_USER:$SERVICE_USER" "$dst"
  fi
}

migrate config.json "$CONFIG_PATH"
migrate history.json "$HISTORY_PATH"
migrate state.json "$STATE_PATH"
ok

step "Checking config"
if [ ! -f "$CONFIG_PATH" ]; then
  cp config.example.json "$CONFIG_PATH"
  chmod 600 "$CONFIG_PATH"
  if [ "$MODE" = system ]; then
    chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_PATH"
  fi
  rerun="$0"
  if [ "$MODE" = system ]; then
    rerun="$0 --system (as root)"
  fi
  fail "config created at $CONFIG_PATH: fill accounts; webhook is optional, then rerun $rerun"
  exit 1
fi
chmod 600 "$CONFIG_PATH"
if [ "$MODE" = system ]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_PATH"
fi
ok

step "Validating config"
HOME="$SERVICE_HOME" "$PYTHON" - "$CONFIG_PATH" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    config = json.load(f)
if not any(a.get("xsrf") and a.get("session") for a in config.get("accounts", [])):
    raise SystemExit("config.json needs at least one account with xsrf and session")
PY
ok

step "Running tests"
HOME="$SERVICE_HOME" "$PYTHON" -m unittest discover -s tests -t . -q
ok

step "Initialising state files"
touch "$HISTORY_PATH" "$STATE_PATH"
chmod 600 "$HISTORY_PATH" "$STATE_PATH"
if [ "$MODE" = system ]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$HISTORY_PATH" "$STATE_PATH"
fi
ok

step "Installing systemd timer"
mkdir -p "$UNIT_DIR"
cp "$UNIT_SRC/daily-reward.service" "$UNIT_SRC/daily-reward.timer" "$UNIT_DIR/"
svc_systemctl stop daily-reward.timer 2>/dev/null || true
if [ "$MODE" = system ]; then
  systemctl daemon-reload
  systemctl enable --now daily-reward.timer
  systemctl list-timers daily-reward.timer --no-pager
else
  sudo loginctl enable-linger "$(id -un)"
  systemctl --user daemon-reload
  systemctl --user enable --now daily-reward.timer
  systemctl --user list-timers daily-reward.timer --no-pager
fi
ok

printf '%s✔ setup complete%s\n' "$GREEN" "$RESET"
