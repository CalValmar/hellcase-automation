# hellcase-automation
Python script that opens the Hellcase Newbie case daily for one or several accounts, records drops locally and notifies Discord.

# requirements
- requests library
- python3.6+ (f-strings)
- at least one account on Hellcase

# setup
Copy `config.example.json` to `config.json`, then fill two things:
- `discord_webhook_url`: leave empty to disable notifications.
- `accounts`: one `{username, xsrf, session}` object per account. `username` is your own label, shown in Discord and history. If it is set and differs from the nickname returned by the API, a Discord warning is sent — this catches tokens filed under the wrong name. Leave it empty to fall back to the API nickname.

`config.json` and `history.json` are gitignored; never commit them. Run `chmod 600 config.json history.json` so other users on the server cannot read the tokens.

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

The script prints nothing. It appends each successful open to `history.json` (gitignored) with account nickname, user id, case, date, weapon and price, then posts one Discord message per account. A failed open is reported on Discord and is not recorded, so the history stays truthful. Raw API responses are never logged: they contain account tokens.

A lock file (`daily-reward.lock`) makes a second run exit immediately if one is already running. A failed run is not retried automatically: a blind retry could open the same case twice. Run `python3 -m unittest -v test_daily_reward` for offline tests, and `python3 stats.py` to print the number of opens and the total price per account (no API call).

The timer runs daily with a random delay of up to 2 hours, and `Persistent=true` catches up a missed run after a reboot. When a session token expires, edit `config.json` locally; no code change is needed.
