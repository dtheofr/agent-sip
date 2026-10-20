import os
import tempfile
import unittest
from pathlib import Path

from agent_sip.config import (
    Config,
    DbConfig,
    RemindersConfig,
    ToolsConfig,
    WebToolsConfig,
    load_config,
)

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "config.example.toml"

PHONE = '[[phones]]\nname = "p"\nip = "1.1.1.1"\n'


def load(toml: str, env=None) -> Config:
    """Write ``toml`` to a temp file and load it with a deterministic env."""
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(toml)
        name = f.name
    try:
        return load_config(name, env={} if env is None else env)
    finally:
        os.unlink(name)


class NestedToml(unittest.TestCase):
    def test_nested_values_land(self):
        cfg = load(
            "[tools.web]\n"
            'tavily_api_key = "k"\n'
            "search_max_results = 5\n"
            "[tools.reminders]\n"
            'timezone = "Europe/Berlin"\n'
            'default_phone = "p"\n'
            "retry_attempts = 4\n"
            "[db]\n"
            'path = "data/x.db"\n' + PHONE
        )
        self.assertEqual(cfg.tools.web.tavily_api_key, "k")
        self.assertEqual(cfg.tools.web.search_max_results, 5)
        self.assertEqual(cfg.tools.reminders.timezone, "Europe/Berlin")
        self.assertEqual(cfg.tools.reminders.default_phone, "p")
        self.assertEqual(cfg.tools.reminders.retry_attempts, 4)
        self.assertEqual(cfg.db.path, "data/x.db")

    def test_env_beats_toml(self):
        cfg = load(
            '[tools.web]\ntavily_api_key = "toml"\n[db]\npath = "toml.db"\n' + PHONE,
            env={
                "AGENT_SIP_TOOLS_WEB_TAVILY_API_KEY": "env",
                "AGENT_SIP_DB_PATH": "env.db",
                "AGENT_SIP_TOOLS_REMINDERS_DEFAULT_PHONE": "envphone",
            },
        )
        self.assertEqual(cfg.tools.web.tavily_api_key, "env")
        self.assertEqual(cfg.db.path, "env.db")
        self.assertEqual(cfg.tools.reminders.default_phone, "envphone")

    def test_nested_sections_are_dataclasses(self):
        cfg = load(PHONE)
        self.assertIsInstance(cfg.tools, ToolsConfig)
        self.assertIsInstance(cfg.tools.web, WebToolsConfig)
        self.assertIsInstance(cfg.tools.reminders, RemindersConfig)
        self.assertIsInstance(cfg.db, DbConfig)


class UnknownKeys(unittest.TestCase):
    def assert_unknown(self, toml, needle):
        with self.assertRaises(ValueError) as ctx:
            load(toml)
        self.assertIn(needle, str(ctx.exception))

    def test_unknown_key_in_web(self):
        self.assert_unknown("[tools.web]\nfoo = 1\n" + PHONE, "[tools.web]")

    def test_unknown_key_in_reminders(self):
        self.assert_unknown("[tools.reminders]\nfoo = 1\n" + PHONE, "[tools.reminders]")

    def test_unknown_key_in_db(self):
        self.assert_unknown("[db]\nfoo = 1\n" + PHONE, "[db]")

    def test_unknown_subsection(self):
        self.assert_unknown("[tools.foo]\nbar = 1\n" + PHONE, "[tools]")

    def test_unknown_top_level_section(self):
        self.assert_unknown("[foo]\nbar = 1\n" + PHONE, "top-level")

    def test_old_flat_tools_layout_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            load('[tools]\ntavily_api_key = "k"\n' + PHONE)
        msg = str(ctx.exception)
        self.assertIn("[tools]", msg)
        self.assertIn("tavily_api_key", msg)
        self.assertIn("[tools.web]", msg)  # hint about the new location


class Defaults(unittest.TestCase):
    def test_defaults_when_sections_absent(self):
        cfg = load(PHONE)
        self.assertEqual(cfg.tools.web.tavily_api_key, "")
        self.assertEqual(cfg.tools.web.search_max_results, 3)
        self.assertEqual(cfg.tools.web.fetch_max_chars, 4000)
        self.assertIs(cfg.tools.reminders.enabled, True)
        self.assertEqual(cfg.tools.reminders.timezone, "")
        self.assertEqual(cfg.tools.reminders.default_phone, "")
        self.assertEqual(cfg.tools.reminders.ring_timeout, 30.0)
        self.assertEqual(cfg.tools.reminders.retry_attempts, 3)
        self.assertEqual(cfg.tools.reminders.retry_interval, 300.0)
        self.assertEqual(cfg.tools.reminders.max_late, 3600.0)
        self.assertEqual(cfg.tools.reminders.keep_days, 7)
        self.assertEqual(cfg.db.path, "data/agent-sip.db")


class EnvCoercion(unittest.TestCase):
    def test_int_float_and_bool(self):
        cfg = load(
            PHONE,
            env={
                "AGENT_SIP_TOOLS_WEB_SEARCH_MAX_RESULTS": "7",
                "AGENT_SIP_TOOLS_WEB_FETCH_MAX_CHARS": "123",
                "AGENT_SIP_TOOLS_REMINDERS_RING_TIMEOUT": "12.5",
                "AGENT_SIP_TOOLS_REMINDERS_MAX_LATE": "60",
                "AGENT_SIP_TOOLS_WEB_FETCH_ENABLED": "no",
                "AGENT_SIP_TOOLS_REMINDERS_ENABLED": "off",
            },
        )
        self.assertEqual(cfg.tools.web.search_max_results, 7)
        self.assertEqual(cfg.tools.web.fetch_max_chars, 123)
        self.assertEqual(cfg.tools.reminders.ring_timeout, 12.5)
        self.assertEqual(cfg.tools.reminders.max_late, 60.0)
        self.assertIs(cfg.tools.web.fetch_enabled, False)
        self.assertIs(cfg.tools.reminders.enabled, False)


class RemindersValidation(unittest.TestCase):
    def test_enabled_requires_phones(self):
        with self.assertRaises(ValueError) as ctx:
            load("[tools.reminders]\nenabled = true\n")
        self.assertIn("[[phones]]", str(ctx.exception))

    def test_disabled_without_phones_is_allowed(self):
        cfg = load("[tools.reminders]\nenabled = false\n")
        self.assertIs(cfg.tools.reminders.enabled, False)
        self.assertEqual(cfg.phones, [])

    def test_absent_reminders_section_needs_no_phones(self):
        # Only a config that opts into reminders must declare a phone; a phone-less
        # config that never mentions [tools.reminders] keeps loading (slice 1 is
        # behaviour-preserving for non-reminder setups).
        cfg = load("")
        self.assertIs(cfg.tools.reminders.enabled, True)
        self.assertEqual(cfg.phones, [])

    def test_reminders_env_without_phones_raises(self):
        with self.assertRaises(ValueError) as ctx:
            load("", env={"AGENT_SIP_TOOLS_REMINDERS_ENABLED": "true"})
        self.assertIn("[[phones]]", str(ctx.exception))

    def test_reminders_section_with_phone_is_fine(self):
        cfg = load("[tools.reminders]\n" + PHONE)
        self.assertIs(cfg.tools.reminders.enabled, True)
        self.assertEqual([p.name for p in cfg.phones], ["p"])

    def test_invalid_timezone_raises(self):
        with self.assertRaises(ValueError) as ctx:
            load('[tools.reminders]\ntimezone = "Not/AZone"\n' + PHONE)
        self.assertIn("Not/AZone", str(ctx.exception))

    def test_valid_timezone_is_accepted(self):
        cfg = load('[tools.reminders]\ntimezone = "Europe/Berlin"\n' + PHONE)
        self.assertEqual(cfg.tools.reminders.timezone, "Europe/Berlin")


class ExampleConfig(unittest.TestCase):
    def test_example_loads_without_error(self):
        cfg = load_config(EXAMPLE, env={})
        self.assertTrue(cfg.phones)
        self.assertEqual(cfg.db.path, "data/agent-sip.db")
        self.assertIs(cfg.tools.reminders.enabled, True)
        self.assertEqual(cfg.tools.reminders.timezone, "")


if __name__ == "__main__":
    unittest.main()
