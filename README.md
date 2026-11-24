# hellcase-automation
Python script that opens the Hellcase Newbie case daily for one or several accounts, records drops locally and notifies Discord.

# requirements
- requests library
- python3.6+ (f-strings)
- at least one account on Hellcase

# project layout
- `daily_reward.py`: opens the cases, saves drops to `history.json` and notifies Discord. The systemd timer runs it.
- `stats.py`: reads `history.json` and prints counts and total price per account. No API call, no writes.
- `test_daily_reward.py`: offline tests with a fake API (`python3 -m unittest -v test_daily_reward`).
- `config.example.json`: tracked template; copy it to the gitignored `config.json`.
- `systemd/`: user unit templates to install in `~/.config/systemd/user/`.

# setup
Copy `config.example.json` to `config.json`, then fill two things:
- `discord_webhook_url`: leave empty to disable notifications.
- `accounts`: one `{username, xsrf, session}` object per account. `username` is only a local label, shown in Discord and history, so you can tell your accounts apart. Leave it empty to fall back to the nickname returned by Hellcase. There is no check against the API nickname.

`config.json` and `history.json` are gitignored; never commit them. Run `chmod 600 config.json history.json` so other users on the server cannot read the tokens. Network captures (`capture.json`, `newbie*.json`, `state.json`) are gitignored too: they contain `auth_code` and a Steam trade link.

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
Assuming the repo is at `~/hellcase-automation`:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.* ~/.config/systemd/user/
chmod 600 config.json history.json
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable daily-reward.timer
```

Start the timer with `systemctl --user start daily-reward.timer` when you are ready — the first run really opens the case for every account.

The script prints nothing. For each account it claims the daily free case, reads the resulting drop from the state endpoint, appends it to `history.json` (gitignored) with account label, user id, case, date, weapon, skin, price, rarity, exterior and open id, then posts one Discord message per account:

```
Valmar: MP7 | Forest DDPAT — 0.03 $ (Forest DDPAT, consumer, Field-Tested)
```

A failed claim or a response without a drop is reported on Discord and is not recorded, so the history stays truthful. If the daily case was already taken from the browser, Hellcase answers `user_level.reward.already_claim` and the message says the case was already claimed today rather than blaming the token. Raw API responses are never logged: they contain account tokens.

A lock file (`daily-reward.lock`) makes a second run exit immediately if one is already running. A failed run is not retried automatically: a blind retry could open the same case twice. Run `python3 -m unittest -v test_daily_reward` for offline tests, and `python3 stats.py` to print the number of opens and the total price per account (no API call).

The timer runs daily with a random delay of up to 2 hours, and `Persistent=true` catches up a missed run after a reboot. When a session token expires, edit `config.json` locally; no code change is needed. If a run fails, fix the cause and relaunch it by hand with `python3 daily_reward.py` from the repo root; the lock file prevents an overlap with the timer.

# how the API flow was identified
Real responses are saved locally in `capture.json`, `newbie.json`, `state.json` and `newbie2.json` (all gitignored). `GET /open/newbie` only returns the case page — no drop. The site's own JavaScript (`useBoxService`) shows the real sequence:

1. `POST /user_level/claim_free_case/newbie` with `X-CSRF-Token` → `open_id`
2. `GET /open/newbie/state` → `bought` and `weapons[0]` (the drop)
3. `GET /open/newbie` → case page, used here only for the account nickname

# known limitations
There is no countdown field. `last_open_date` is not a reliable personal date — in a real capture it did not match the newest `top_items` entry either — so history rows use the local run time. A manual run really claims the case; do not use it just to "check" availability.
