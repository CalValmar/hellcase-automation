# AGENTS.md

- This repo is a single Python script that calls Hellcase's live API. There is no build, test, lint, or CI setup — "verification" means running the script against the real service.
- The script opens `config.json` via a relative path, so run it from the repo root: `python3 daily_reward.py`. Python 3.6+ is required for f-strings.
- `config.json` holds live credentials and is gitignored, but it used to be tracked — it was removed from the index. Never `git add` it; `config.example.json` is the tracked placeholder to copy from.
- The script sends `XSRF-TOKEN` and `hellcase_session` cookies to `api.hellcase.com`. `hellcase_session` expires on session close or ~30 days; refresh both from browser cookies when calls start failing. Token-extraction steps are in README.md.
- Running the script has real side effects on the configured account (opening the Newbie case via `https://api.hellcase.com/open/newbie`). Don't execute it as a casual test without user approval; there is no dry-run mode.
- `daily_reward.py` prints only selected status fields, not `response.text`: the Newbie response contains `auth_code` and a Steam trade link, so raw logging leaks account data. Non-JSON responses fall back to the HTTP status code.
- Scheduling is external (README suggests cron ~every 1450 minutes); there is no scheduler code in the repo.
