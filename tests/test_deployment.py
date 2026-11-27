import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DeploymentTest(unittest.TestCase):
    def test_system_service_uses_dedicated_user_home_and_venv(self):
        service = (ROOT / "systemd" / "system" / "daily-reward.service").read_text()
        self.assertIn("User=hellcase", service)
        self.assertIn("Environment=HOME=/var/lib/hellcase", service)
        self.assertIn(
            "ExecStart=/opt/hellcase-automation/.venv/bin/python "
            "/opt/hellcase-automation/daily_reward.py",
            service,
        )
        self.assertNotIn("Restart=", service)

    def test_setup_accepts_system_mode_without_breaking_user_mode(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("--system", setup)
        self.assertIn('MODE=system', setup)
        self.assertIn('/etc/systemd/system', setup)
        self.assertIn("git pull --ff-only", setup)
        self.assertIn("systemctl --user daemon-reload", setup)

    def test_venv_is_ignored(self):
        self.assertIn(".venv/", (ROOT / ".gitignore").read_text())

    def test_default_mode_uses_system_interpreter(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("PYTHON=/usr/bin/python3", setup)

    def test_installer_does_not_clear_timer_state(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertNotIn("clean --what=state", setup)

    def test_system_mode_checks_other_user_homes(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("/home/*", setup)

    def test_readme_lxc_commands_run_as_root(self):
        readme = (ROOT / "README.md").read_text()
        self.assertNotIn("sudo ./setup.sh", readme)
        self.assertIn("as root", readme)

    def test_setup_rejects_extra_arguments(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn('"$#" -gt 1', setup)

    def test_config_created_message_says_webhook_optional(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("webhook is optional", setup)

    def test_services_are_scoped_and_timer_is_shared(self):
        self.assertTrue((ROOT / "systemd" / "user" / "daily-reward.service").is_file())
        self.assertTrue((ROOT / "systemd" / "system" / "daily-reward.service").is_file())
        self.assertTrue((ROOT / "systemd" / "daily-reward.timer").is_file())
        self.assertFalse((ROOT / "systemd" / "system" / "daily-reward.timer").exists())

    def test_setup_copies_shared_timer_for_both_modes(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn('cp "$UNIT_SRC/daily-reward.service" "$UNIT_DIR/"', setup)
        self.assertIn('cp systemd/daily-reward.timer "$UNIT_DIR/"', setup)

    def test_setup_rejects_placeholder_credentials(self):
        setup = (ROOT / "setup.sh").read_text()
        snippet = setup.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / "config.json"
            config.write_text(json.dumps({"accounts": [{
                "xsrf": "REPLACE_WITH_XSRF_TOKEN",
                "session": "real-session",
            }]}))
            result = subprocess.run([sys.executable, "-c", snippet, str(config)],
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REPLACE_", result.stdout + result.stderr)

    def test_timer_runs_hourly_with_bounded_jitter(self):
        timer = (ROOT / "systemd" / "daily-reward.timer").read_text()
        self.assertIn("OnCalendar=*-*-* *:00:00 UTC", timer)
        self.assertIn("RandomizedDelaySec=30m", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("AccuracySec=1s", timer)
        self.assertIn("Unit=daily-reward.service", timer)

    def test_setup_rejects_both_unit_types_in_the_other_mode(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn('"$home/.config/systemd/user/daily-reward.service"', setup)
        self.assertIn("/etc/systemd/system/daily-reward.service", setup)

    def sandbox_setup(self, extra_env=None, id_as_root=False):
        tmp = tempfile.mkdtemp(prefix="hellcase-setup-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = pathlib.Path(tmp)
        repo = root / "repo"
        shutil.copytree(ROOT, repo,
                        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
        home = root / "home"
        config_dir = home / ".config" / "hellcase-automation"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(json.dumps({
            "discord_webhook_url": "",
            "accounts": [{"username": "Alice", "xsrf": "real", "session": "real"}],
        }))
        bin_dir = root / "bin"
        bin_dir.mkdir()
        scripts = {
            "git": "#!/bin/sh\nexit 0\n",
            "systemctl": "#!/bin/sh\ncase \" $* \" in\n  *' is-active '*) exit 1 ;;\nesac\nexit 0\n",
            "sudo": "#!/bin/sh\nexec \"$@\"\n",
            "loginctl": "#!/bin/sh\nexit 0\n",
        }
        if id_as_root:
            scripts["id"] = (
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-u\" ]; then echo 0; else echo root; fi\n"
            )
        for name, body in scripts.items():
            script = bin_dir / name
            script.write_text(body)
            script.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "NO_COLOR": "1",
            "PIP_NO_INDEX": "1",
            "PIP_BREAK_SYSTEM_PACKAGES": "1",
            "HELLCASE_SKIP_SETUP_INTEGRATION": "1",
        })
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(["bash", str(repo / "setup.sh")], cwd=str(repo),
                                env=env, capture_output=True, text=True)
        return result, home, repo

    @unittest.skipIf(os.environ.get("HELLCASE_SKIP_SETUP_INTEGRATION"),
                     "sandbox setup already running")
    def test_user_setup_installs_service_from_current_checkout(self):
        result, home, repo = self.sandbox_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        service = (home / ".config" / "systemd" / "user" /
                   "daily-reward.service").read_text()
        self.assertIn(f"ExecStart=/usr/bin/python3 {repo}/daily_reward.py", service)
        self.assertNotIn("%h/Documents/PERSO", service)

    @unittest.skipIf(os.environ.get("HELLCASE_SKIP_SETUP_INTEGRATION"),
                     "sandbox setup already running")
    def test_user_setup_refuses_to_run_as_root(self):
        result, _, _ = self.sandbox_setup(id_as_root=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("use --system", result.stdout + result.stderr)

    def test_config_validator_rejects_non_object_accounts(self):
        setup = (ROOT / "setup.sh").read_text()
        snippet = setup.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / "config.json"
            config.write_text(json.dumps({"accounts": ["oops"]}))
            result = subprocess.run([sys.executable, "-c", snippet, str(config)],
                                    capture_output=True, text=True)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("accounts", output)
        self.assertNotIn("AttributeError", output)

    def test_mode_switch_message_requires_removing_unit_files(self):
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("remove the user unit files", setup)
        self.assertIn("remove the system unit files", setup)
