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
│   ├── daily-reward.service
│   └── daily-reward.timer
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

Among the config/state files, only `config.example.json` is tracked; back up the two home directories, not the checkout.

## Setup
- Python 3.6+, `requests` (`python3 -m pip install requests`).
- On the first `./setup.sh`, `~/.config/hellcase-automation/config.json` is created from `config.example.json`. Fill `discord_webhook_url` (empty disables alerts) and `accounts` = `{username, xsrf, session}` objects, then rerun the script. `username` is a local label only; empty falls back to the API nickname.
- Get `XSRF-TOKEN` and `hellcase_session` from browser cookies on hellcase.com; edit the config when they expire (~30 days).
- Local files live outside the checkout: config in `~/.config/hellcase-automation/`, state/history/lock in `~/.local/state/hellcase-automation/`

## On a server
On a fresh clone, just run :

```bash
git pull
./setup.sh
# fill ~/.config/hellcase-automation/config.json
./setup.sh
systemctl --user list-timers daily-reward.timer
```

## Behavior
- Hourly UTC timer with a random 0–30 min delay. Each run picks up to 2 due accounts, shuffled, 30–180 s apart.
- `state.json` remembers each account's last claim and last attempt/error day. An account claimed in the last 24h + 1 min is skipped; a failed account is retried at most once per UTC day. `already_claim` also marks it claimed, so browser claims are not reattempted.
- Successful drops go to `history.json` with local time, account, weapon, skin, price, rarity, exterior and `open_id`. Discord gets one message per drop or real failure. Raw responses are never logged.
