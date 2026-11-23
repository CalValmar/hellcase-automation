# hellcase-automation
Python script that opens the Hellcase Newbie case daily for one or several accounts.

# requirements
- requests library
- python3.6+ (f-strings)
- at least one account on Hellcase

# accounts and secrets
Copy `accounts.example.json` to `accounts.json` and fill one entry per account:
- `name` is just a label used in Discord messages and history.
- `xsrf` comes from the `XSRF-TOKEN` browser cookie; it rarely changes.
- `session` comes from the `hellcase_session` cookie; it must be replaced after logout or ~30 days.

Optionally copy `secrets.example.json` to `secrets.json` and set `discord_webhook_url`. All these files are gitignored; never commit them. Run `chmod 600 accounts.json secrets.json`.

# obtaining tokens from cookies
To obtain the tokens for `accounts.json`:
- go to [hellcase.com](https://hellcase.com)
- login via steam link
- press F12 when on the main page of hellcase
- go down into the data section
- search for cookies at https://hellcase.com
- copy the values into `accounts.json`
Some values need to be replaced every so often.

# usage on a server (systemd user timer)
Assuming the repo is at `~/hellcase-automation`:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/daily-reward.* ~/.config/systemd/user/
chmod 600 accounts.json secrets.json
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable daily-reward.timer
```

Start the timer with `systemctl --user start daily-reward.timer` when you are ready — the first run really opens the cases. Check it with `systemctl --user list-timers --all`.

The script prints nothing. It appends each open to `history.json` (gitignored) with account, case, date, weapon and price. If a webhook is configured, it posts only the drop or a failure notice — never the raw API response, which contains account tokens.

The timer runs daily with a random delay of up to 2 hours, and `Persistent=true` catches up a missed run after a reboot. When a session token expires, edit `accounts.json` locally; no code change is needed.
