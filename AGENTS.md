# AGENTS.md

- This repo is a single Python script that calls Hellcase's live API. There is no build, test, lint, or CI setup — "verification" means running the script against the real service.
- The script opens `config.json` via a relative path, so run it from the repo root: `python3 daily_reward.py`. Python 3.6+ is required for f-strings.
- `config.json` holds live credentials and is gitignored, but it used to be tracked — it was removed from the index. Never `git add` it; `config.example.json` is the tracked placeholder to copy from.
- The script sends `XSRF-TOKEN` and `hellcase_session` cookies to `api.hellcase.com`. `hellcase_session` expires on session close or ~30 days; refresh both from browser cookies when calls start failing. Token-extraction steps are in README.md.
- Running the script has real side effects on the configured account (opening the Newbie case via `https://api.hellcase.com/open/newbie`). Don't execute it as a casual test without user approval; there is no dry-run mode.
- `daily_reward.py` prints only `status`, `casename`, `case_is_opened` and `claim_available`, not `response.text`: the Newbie response contains `auth_code` and a Steam trade link, so raw logging leaks account data. `need_refill` is deliberately omitted (the case is free). Non-JSON responses fall back to the HTTP status code.
- `systemd/` holds user unit templates: `daily-reward.service` (oneshot, waits for network, retries failures, 60s timeout) and `daily-reward.timer` (`OnCalendar=daily`, `Persistent=true`, `RandomizedDelaySec=2h`). Install them in `~/.config/systemd/user/`; `loginctl enable-linger $USER` is required for them to run while logged out.
- The script uses a 30s HTTP timeout. Don't start the timer as a setup test — the first run opens the real case. README has the exact install commands.
