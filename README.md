# hellcase-automation
Python script that opens the Hellcase Newbie case daily.

# requirements
- requests library
- python3.6+ (f-strings)
- account created on hellcase

# editing config files
Copy `config.example.json` to `config.json` before using the script, then edit `config.json`. It is gitignored; never commit it.
- "xsrf" is a token that is obtained from XSRF-TOKEN cookie from your browser, it doesn't need to be replaced every so often
- "session" is a session token that can be obtained from hellcase_session cookie, it must be replaced every session closage or 30 days

# obtaining tokens from cookies
To obtain tokens needed in config.json you should:
- go to [hellcase.com](https://hellcase.com)
- login via steam link
- press F12 when on main page of hellcase
- go down into data section
- search for cookies at https://hellcase.com
- copy values from browser into config.json file
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

Start the timer with `systemctl --user start daily-reward.timer` when you are ready — the first run really opens the case. Check it with `systemctl --user list-timers --all` and `journalctl --user -u daily-reward.service -f`.

The timer runs daily and `Persistent=true` catches up a missed run after a reboot. When the session token expires, edit `config.json` locally; no code change is needed.
