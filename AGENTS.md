# AGENTS.md

- This repo is a single Python script that calls Hellcase's live API for one or several accounts. There is no build, test, lint, or CI setup — "verification" means running the script against the real service.
- Run it from the repo root: `python3 daily_reward.py`. Python 3.6+ is required for f-strings.
- `accounts.json` holds each account's `xsrf` / `session`, `secrets.json` holds the optional Discord webhook URL, and `history.json` stores drops. All are gitignored; `accounts.example.json` and `secrets.example.json` are the tracked templates. `config.json` is the old single-account file and is no longer read.
- Each account gets its own `requests.session()` with its cookies. `hellcase_session` expires on logout or ~30 days; edit `accounts.json` locally when calls start failing.
- `GET https://api.hellcase.com/open/newbie` really opens the case. Don't execute the script or start the timer as a test: every run opens the case for every configured account.
- The script prints nothing. It appends `{date, account, user_id, case, weapon, price}` to `history.json` and posts a Discord message only when a webhook is configured. Raw responses are never logged: they contain `auth_code` and a Steam trade link.
- `extract_drop()` matches drops in `top_items` filtered by the response's `user.id`. It carries a `shortcut:` comment because the real drop field has not been confirmed yet.
- `systemd/` holds user unit templates: `daily-reward.service` (oneshot, waits for network, retries failures, 10min timeout) and `daily-reward.timer` (`OnCalendar=daily`, `Persistent=true`, `RandomizedDelaySec=2h`). Install them in `~/.config/systemd/user/`; `loginctl enable-linger $USER` is required to run while logged out.
- The HTTP call has a 30s timeout, accounts are separated by a small random delay, and webhook failures are ignored.
