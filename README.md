# hellcase-automation
Unofficial script that opens the Hellcase Newbie case for several accounts, records drops locally and alerts Discord. Automation may breach Hellcase's terms; this is not a ban guarantee.

## Setup
- Python 3.6+, `requests` (`python3 -m pip install requests`).
- Copy `config.example.json` to gitignored `config.json`: `discord_webhook_url` (empty disables alerts) and `accounts` = `{username, xsrf, session}` objects. `username` is a local label only; empty falls back to the API nickname. Keep account order stable: `state.json` keys by index.
- Get `XSRF-TOKEN` and `hellcase_session` from browser cookies on hellcase.com; edit `config.json` when they expire (~30 days).

## On the server
Run these on the server itself. Paths assume `~/Documents/PERSO/Projets/hellcase-automation`; edit the two unit paths if yours differs.

```bash
cd ~/Documents/PERSO/Projets/hellcase-automation
git pull --ff-only
python3 -m pip install --user requests
[ -f config.json ] || cp config.example.json config.json   # then fill tokens/webhook
touch history.json state.json
chmod 600 config.json history.json state.json
mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.* ~/.config/systemd/user/
sudo loginctl enable-linger "$USER"
systemctl --user stop daily-reward.timer 2>/dev/null || true
systemctl --user clean --what=state daily-reward.timer 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now daily-reward.timer
systemctl --user list-timers daily-reward.timer
```

`enable-linger` needs your sudo password and is required to keep the timer running after logout. The `stop`/`clean` lines avoid a stale catch-up claim on upgrade. After editing `config.json`, rerun the `chmod` line. A manual `python3 daily_reward.py` really claims cases; tests are offline: `python3 -m unittest -v test_daily_reward`.

## Behavior
- Hourly UTC timer with a random 0–30 min delay. Each run picks up to 2 due accounts, shuffled, 30–180 s apart.
- Gitignored `state.json` (mode `600`) remembers each account's last claim and last attempt/error day. An account claimed in the last 24h + 1 min is skipped; a failed account is retried at most once per UTC day. `already_claim` also marks it claimed, so browser claims are not reattempted.
- Successful drops go to gitignored `history.json` (mode `600`) with local time, account, weapon, skin, price, rarity, exterior and `open_id`. Discord gets one message per drop or real failure. Failures show the API's own error message (or "raison inconnue" / "réseau ou réponse inattendue") — never a guessed "token expiré". Failure alerts sent after a successful claim carry its `open_id`: do not replay them. `already_claim` is silent. Raw responses are never logged.
- No claim retry, no `Restart=` in the service, and a lock blocks overlapping runs. The read-only `GET /open/newbie` is retried once because user managers have no `network-online.target`.
- No API countdown and no verified `claim_available` gate. Worst case is ~1 h of lag after the cooldown; 5 accounts due together need 3 hourly runs.

## API flow
From captures and the site's `useBoxService` JS: `POST /user_level/claim_free_case/newbie` → `open_id`, then `GET /open/newbie/state` → `bought` + `weapons[0]`. `GET /open/newbie` only returns the case page, used for the nickname fallback. `last_open_date` and `top_items` are not reliable for the drop. Captures live in gitignored `.captures/`.
