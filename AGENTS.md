# AGENTS.md

- This repo is a small collection of Python scripts that call Hellcase's live API. There is no build, test, lint, or CI setup — "verification" means running a script against the real service.
- Scripts open `config.json` via a relative path, so run them from the repo root: `python3 daily_reward.py` or `python3 free_giveaway.py`. README says "python2+", but the code uses f-strings and requires Python 3.6+.
- `config.json` is gitignored because it holds live credentials. Never commit real `XSRF-TOKEN` / `hellcase_session` values; leave the placeholder file untouched.
- Both scripts send `XSRF-TOKEN` and `hellcase_session` cookies to `api.hellcase.com`. `hellcase_session` expires on session close or ~30 days; refresh both from browser cookies when calls start failing. Token-extraction steps are in README.md.
- `free_giveaway.py` requires the `X-Requested-With: XMLHttpRequest` header on giveaway endpoints. It checks `data.free_giveaway.is_user_joined`, joins only when not joined, otherwise prints time remaining until `finish`.
- Running a script has real side effects on the configured account (opening the Newbie case via `https://api.hellcase.com/open/newbie`, joining a giveaway). Don't execute them as a casual test without user approval; there is no dry-run mode.
- `daily_reward.py` prints only selected status fields, not `response.text`: the Newbie response contains `auth_code` and a Steam trade link, so raw logging leaks account data. `free_giveaway.py` still prints raw join responses and has no error handling — auth failures and HTML error pages can look like normal output.
- Scheduling is external (README suggests cron ~every 1450 minutes); there is no scheduler code in the repo.
