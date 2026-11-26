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
