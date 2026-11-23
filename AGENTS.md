# AGENTS.md

- This repo is a single Python script that calls Hellcase's live API daily for one or several accounts. There is no build, test, lint, or CI setup — "verification" means running the script against the real service.
- Run it from the repo root: `python3 daily_reward.py`. Python 3.6+ is required for f-strings.
- All local state lives in two gitignored files: `config.json` (`discord_webhook_url` + `accounts` array of `{username, xsrf, session}`) and `history.json` (generated drops). `config.example.json` is the only tracked template. `username` is a local label used in Discord/history; when set and different from the API's `user.nickname`, the script sends a Discord warning. Empty/missing label falls back to `user.nickname`.
- Each account gets its own `requests.session()` with its cookies. `hellcase_session` expires on logout or ~30 days; edit `config.json` locally when calls start failing.
- `GET https://api.hellcase.com/open/newbie` really opens the case. Don't execute the script or start the timer as a test: every run opens the case for every configured account.
- The script prints nothing. It appends `{date, account, user_id, case, weapon, price}` to `history.json` and posts one Discord message per account when a webhook is configured. Raw responses are never logged: they contain `auth_code` and a Steam trade link.
- `extract_drop()` matches drops in `top_items` filtered by the response's `user.id`. It carries a `shortcut:` comment because the real drop field has not been confirmed yet.
- The response's `user` object is the only known source of account info (nickname, id, wallet) — no separate read-only account API was found. Don't add an unverified endpoint.
- `systemd/` holds user unit templates: `daily-reward.service` (oneshot, waits for network, retries failures, 10min timeout) and `daily-reward.timer` (`OnCalendar=daily`, `Persistent=true`, `RandomizedDelaySec=2h`). Install them in `~/.config/systemd/user/`; `loginctl enable-linger $USER` is required to run while logged out.
- The HTTP call has a 30s timeout, accounts are separated by a small random delay, and webhook failures are ignored.
