import pathlib
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
