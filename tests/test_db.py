import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from agent_sip.db import connect, migrate, split_statements
from agent_sip.db.migrations import MIGRATIONS


class ConnectTest(unittest.TestCase):
    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deeper" / "agent.db"
            self.assertFalse(path.parent.exists())
            conn = connect(path)
            self.addCleanup(conn.close)
            self.assertTrue(path.parent.is_dir())
            self.assertTrue(path.exists())

    def test_wal_and_foreign_keys_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agent.db")
            self.addCleanup(conn.close)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_row_factory_is_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agent.db")
            self.addCleanup(conn.close)
            conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
            conn.execute("INSERT INTO t VALUES (1, 'x')")
            row = conn.execute("SELECT * FROM t").fetchone()
            self.assertIsInstance(row, sqlite3.Row)
            self.assertEqual(row["b"], "x")

    def test_usable_from_another_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agent.db")
            self.addCleanup(conn.close)
            errors: list[BaseException] = []

            def worker():
                try:
                    conn.execute("SELECT 1").fetchone()
                except sqlite3.Error as exc:  # pragma: no cover - only on regression
                    errors.append(exc)

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
            self.assertEqual(errors, [])


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conn = connect(Path(self._tmp.name) / "migrate.db")
        self.addCleanup(self.conn.close)

    def _tables(self) -> set[str]:
        return {
            row[0]
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    def test_fresh_db_starts_at_version_zero(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_applies_migrations_in_order_and_sets_version(self):
        applied = migrate(
            self.conn,
            [
                "CREATE TABLE t (a INTEGER); INSERT INTO t VALUES (1)",
                "ALTER TABLE t ADD COLUMN b TEXT",
            ],
        )
        self.assertEqual(applied, 2)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)
        columns = [row["name"] for row in self.conn.execute("PRAGMA table_info(t)")]
        self.assertEqual(columns, ["a", "b"])

    def test_idempotent(self):
        self.assertEqual(migrate(self.conn, MIGRATIONS), len(MIGRATIONS))
        self.assertEqual(migrate(self.conn, MIGRATIONS), 0)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], len(MIGRATIONS))

    def test_already_migrated_db_is_untouched(self):
        self.conn.execute("PRAGMA user_version = 1")
        self.assertEqual(migrate(self.conn, MIGRATIONS), 0)
        self.assertNotIn("reminders", self._tables())

    def test_failing_migration_rolls_back(self):
        with self.assertRaises(sqlite3.Error):
            migrate(
                self.conn,
                [
                    "CREATE TABLE good (a INTEGER)",
                    "CREATE TABLE bad (b INTEGER); INSERT INTO missing VALUES (1)",
                ],
            )
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 1)
        tables = self._tables()
        self.assertIn("good", tables)
        self.assertNotIn("bad", tables)

    def test_failing_first_migration_rolls_back_everything(self):
        with self.assertRaises(sqlite3.Error):
            migrate(self.conn, ["CREATE TABLE x (a INTEGER); INSERT INTO missing VALUES (1)"])
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 0)
        self.assertNotIn("x", self._tables())

    def test_reminders_schema_and_index(self):
        migrate(self.conn, MIGRATIONS)
        columns = [row["name"] for row in self.conn.execute("PRAGMA table_info(reminders)")]
        self.assertEqual(
            columns,
            [
                "id",
                "message",
                "due_at",
                "tz",
                "repeat",
                "until",
                "phone",
                "status",
                "attempts",
                "next_try_at",
                "created_at",
            ],
        )
        indexes = {row["name"] for row in self.conn.execute("PRAGMA index_list(reminders)")}
        self.assertIn("reminders_due", indexes)


class SplitStatementsTest(unittest.TestCase):
    def test_splits_on_semicolons_and_skips_comments(self):
        script = (
            "CREATE TABLE t (a INTEGER); -- trailing comment\n"
            "-- whole-line comment\n"
            "INSERT INTO t VALUES (1);\n"
        )
        statements = split_statements(script)
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[0].startswith("CREATE TABLE"))
        # Leading comments stay attached to the following statement; SQLite accepts them.
        self.assertIn("INSERT INTO t VALUES (1)", statements[1])

    def test_keeps_semicolons_inside_string_literals(self):
        statements = split_statements("INSERT INTO t VALUES ('a; b'); INSERT INTO t VALUES ('c')")
        self.assertEqual(len(statements), 2)
        self.assertIn("'a; b'", statements[0])

    def test_trailing_statement_without_semicolon(self):
        self.assertEqual(len(split_statements("SELECT 1")), 1)


if __name__ == "__main__":
    unittest.main()
