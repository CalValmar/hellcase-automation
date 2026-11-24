# hellcase-automation
Python script that opens the Hellcase Newbie case daily for one or several accounts, records drops locally and notifies Discord.

# requirements
- python3.6+ (f-strings)
- requests library (`python3 -m pip install requests`)
- at least one account on Hellcase

# project layout
- `daily_reward.py`: opens the cases, saves drops to `history.json` and notifies Discord. The systemd timer runs it.
- `test_daily_reward.py`: offline tests with a fake API (`python3 -m unittest -v test_daily_reward`).
- `.captures/`: gitignored local network captures, kept as a reference for the API flow.
- `config.example.json`: tracked template; copy it to the gitignored `config.json`.
- `systemd/`: user unit templates to install in `~/.config/systemd/user/`.

# setup
Copy `config.example.json` to `config.json`, then fill two things:
- `discord_webhook_url`: leave empty to disable notifications.
- `accounts`: one `{username, xsrf, session}` object per account. `username` is only a local label, shown in Discord and history, so you can tell your accounts apart. Leave it empty to fall back to the nickname returned by Hellcase. There is no check against the API nickname.

`config.json` and `history.json` are gitignored; never commit them. `history.json` only appears after the first drop, so create it before locking things down: `touch history.json && chmod 600 config.json history.json`. The script also creates its temporary file with mode `600`. Network captures live in the gitignored `.captures/` folder: they contain `auth_code` and a Steam trade link.

To add a friend's account, append another `{username, xsrf, session}` object to `accounts`.

# obtaining tokens from cookies
To obtain the tokens for an account:
- go to [hellcase.com](https://hellcase.com)
- login via steam link
- press F12 when on the main page of hellcase
- go down into the data section
- search for cookies at https://hellcase.com
- copy `XSRF-TOKEN` and `hellcase_session` values into `config.json`
Some values need to be replaced every so often.

# usage on a server (systemd user timer)
The unit files hardcode `~/Documents/PERSO/Projets/hellcase-automation` in `WorkingDirectory` and `ExecStart`. Clone there, or edit both paths before installing:

```bash
git clone <repo-url> ~/Documents/PERSO/Projets/hellcase-automation
cd ~/Documents/PERSO/Projets/hellcase-automation
python3 -m pip install requests
mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.* ~/.config/systemd/user/
touch history.json
chmod 600 config.json history.json
sudo loginctl enable-linger "$USER"
systemctl --user stop daily-reward.timer 2>/dev/null || true
systemctl --user clean --what=state daily-reward.timer 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable daily-reward.timer
# upgrade only: apply the new schedule (also starts the timer)
# systemctl --user restart daily-reward.timer
```

Cleaning the timer state avoids an immediate catch-up claim from a stale stamp after an upgrade. On an upgrade, uncomment the `restart` line after `daemon-reload` to apply the new schedule. Start it with `systemctl --user start daily-reward.timer` when you are ready — the first run really opens the case for every account. Verify the schedule read-only with `systemctl --user list-timers daily-reward.timer`.

The script prints nothing. For each due account it claims the daily free case, reads the resulting drop from the state endpoint, appends it to `history.json` (gitignored) with account label, user id, case, date, weapon, skin, price, rarity, exterior and open id, then posts one Discord message per successful claim or real failure; already-claimed accounts are silent:

```
Valmar: MP7 | Forest DDPAT — 0.03 $ (Forest DDPAT, consumer, Field-Tested)
```

A failed claim or a response without a drop is reported on Discord and is not recorded, so the history stays truthful. The alert shows the API's own error message (or "raison inconnue" if none). `user_level.reward.already_claim` means "not due yet" and stays silent, since the timer checks several times a day. Network failures say so too — an expired token is never assumed. When the claim succeeded, the alert includes its `open_id`: do not rerun the script for that account, the drop is already in your Hellcase inventory. Raw API responses are never logged: they contain account tokens.

A lock file (`daily-reward.lock`) makes a second run exit immediately if one is already running. A failed run is not retried automatically: a blind retry could open the same case twice. Run `python3 -m unittest -v test_daily_reward` for offline tests (no API call).

The timer checks at 00:00, 06:00, 12:00 and 18:00 UTC, so an account is at most six hours late between successful checks on its rolling cooldown; `Persistent=true` catches up a missed run after a reboot. Accounts are not given separate timers: Hellcase gives no authoritative countdown, and repeated checks are safer than guessing each account's reset time. The unit declares `After/Wants=network-online.target`, but a user manager has no wait-online implementation, so the initial read-only GET is retried once if the network is not ready. When a session token expires, edit `config.json` locally; no code change is needed. If a run fails, fix the cause and relaunch it by hand with `python3 daily_reward.py` from the repo root; the lock file prevents an overlap with the timer. Rerun only if the claim POST did not succeed: a successful claim followed by a failed state call must never be replayed.

# how the API flow was identified
Real responses are saved locally in the gitignored `.captures/` folder (`capture.json`, `newbie.json`, `state.json`, `newbie2.json`). `GET /open/newbie` only returns the case page — no drop. The site's own JavaScript (`useBoxService`) shows the real sequence:

1. `POST /user_level/claim_free_case/newbie` with `X-CSRF-Token` → `open_id`
2. `GET /open/newbie/state` → `bought` and `weapons[0]` (the drop)
3. `GET /open/newbie` → case page, used here only for the account nickname

# known limitations
There is no countdown field. `last_open_date` is not a reliable personal date — in a real capture it did not match the newest `top_items` entry either — so history rows use the local run time. A manual run really claims the case; do not use it just to "check" availability. If the cooldown is exactly 24 hours from the claim, a claim landing just after a UTC check is still early at that same check next day and waits until the next one: the effective cadence can reach about 30 hours. That is the cost of fixed checks without per-account timers or claim retries.
