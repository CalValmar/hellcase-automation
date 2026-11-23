# hellcase-automation
Python script that opens the Hellcase Newbie case daily for one or several accounts, records drops locally and notifies Discord.

# requirements
- requests library
- python3.6+ (f-strings)
- at least one account on Hellcase

# setup
Copy `config.example.json` to `config.json`, then fill two things:
- `discord_webhook_url`: leave empty to disable notifications.
- `accounts`: one `{xsrf, session}` object per account. There is no `name` field: the account label is taken from the Hellcase nickname returned by the API.

`config.json` is gitignored; never commit it. Run `chmod 600 config.json`.

To add a friend's account, append another `{xsrf, session}` object to `accounts`.

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
chmod 600 config.json
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable daily-reward.timer
```

Start the timer with `systemctl --user start daily-reward.timer` when you are ready — the first run really opens the case for every account.

The script prints nothing. It appends each open to `history.json` (gitignored) with account nickname, user id, case, date, weapon and price, then posts one Discord message per account. Raw API responses are never logged: they contain account tokens.

The timer runs daily with a random delay of up to 2 hours, and `Persistent=true` catches up a missed run after a reboot. When a session token expires, edit `config.json` locally; no code change is needed.
