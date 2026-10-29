import os
import subprocess
import sys
import unittest
from pathlib import Path

import agent_sip
from agent_sip.agent.web_tools import UA

ROOT = Path(__file__).resolve().parents[1]


class Version(unittest.TestCase):
    def test_exposes_semver(self):
        self.assertRegex(agent_sip.__version__, r"^\d+\.\d+\.\d+(?:\.dev\d+)?$")

    def test_cli_reports_version(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        proc = subprocess.run([sys.executable, "-m", "agent_sip", "--version"],
                              check=False, cwd=ROOT, env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(agent_sip.__version__, proc.stdout)

    def test_user_agent_uses_version(self):
        self.assertIn(agent_sip.__version__, UA)


if __name__ == "__main__":
    unittest.main()
