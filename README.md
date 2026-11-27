# hellcase-automation
Unofficial script that opens the Hellcase Newbie case for several accounts, records drops locally and alerts Discord. Automation may breach Hellcase's terms; this is not a ban guarantee.

## Layout

```text
hellcase-automation/
├── README.md
├── setup.sh
├── daily_reward.py
├── config.example.json
├── systemd/
│   ├── daily-reward.timer        # shared by both modes
│   ├── user/
│   │   └── daily-reward.service  # laptop
│   └── system/
│       └── daily-reward.service  # LXC
└── tests/
```

```text
~/
├── .config/hellcase-automation/
│   └── config.json
└── .local/state/hellcase-automation/
    ├── state.json
    ├── history.json
    └── daily-reward.lock
```

`config.example.json` is the only tracked template; the config and state files shown here are generated locally. Back up the home directories, not the checkout.

## Setup
- Python 3.6+, `requests` (`python3 -m pip install requests`).
- On the first `./setup.sh`, `~/.config/hellcase-automation/config.json` is created from `config.example.json`. Fill `discord_webhook_url` (empty disables alerts) and `accounts` = `{username, xsrf, session}` objects, then rerun the script. `username` is a local label only; empty falls back to the API nickname. Values starting with `REPLACE_` are rejected by the installer.
- Get `XSRF-TOKEN` and `hellcase_session` from browser cookies on hellcase.com; edit the config when they expire (~30 days).
- Local files live outside the checkout: config in `~/.config/hellcase-automation/`, state/history/lock in `~/.local/state/hellcase-automation/`
- On a server/LXC, run `./setup.sh --system` as root from `/opt/hellcase-automation`; see below. Plain `./setup.sh` as root is refused.

## On a Proxmox LXC (recommended)
Create an unprivileged Debian 13 (Trixie) LXC with 1 core, 512 MB–1 GB RAM, 8 GB disk and a `vmbr0` network. Run these commands as root in the LXC console:

```bash
apt update && apt install -y git python3 python3-venv ca-certificates
git clone <your-repo-url> /opt/hellcase-automation
cd /opt/hellcase-automation
./setup.sh --system
# fill /var/lib/hellcase/.config/hellcase-automation/config.json
./setup.sh --system
systemctl list-timers daily-reward.timer --no-pager
journalctl -u daily-reward.service -S today --no-pager
```

The system unit runs as `hellcase` with `HOME=/var/lib/hellcase`, so config/state/lock live under that home, not `/root`. On the first system-mode install, copy the old `config.json`, `state.json` and `history.json` into that home before enabling the timer. If you edit the config as root, rerun the installer afterwards to restore `hellcase` ownership. System mode never runs `git pull`: update with `git -C /opt/hellcase-automation pull` before rerunning the installer. Keep the accounts array in the same order: `state.json` is keyed by index. Back up the container with encrypted `vzdump`/PBS — the config contains live cookies and a Discord webhook. Do not run `python3 daily_reward.py` or `systemctl start daily-reward.service` as a test: a due account really claims its case.

## Behavior
- Hourly UTC timer with a random 0–30 min delay. Each run picks up to 2 due accounts, shuffled, ~5 min apart.
- `state.json` remembers each account's last claim and last attempt/error day. An account claimed in the last 24h + 1 min is skipped; a failed account is retried at most once per UTC day. `already_claim` also marks it claimed, so browser claims are not reattempted.
- Successful drops go to `history.json` with local time, account, weapon, skin, price, rarity, exterior and `open_id`. A non-empty invalid `history.json` is renamed to `history.json.corrupt` with an alert instead of being overwritten; empty files are ignored. `history.json` is written before `state.json`, so a crash between the two writes keeps the drop. Discord gets one message per drop or real failure. Raw responses are never logged.
