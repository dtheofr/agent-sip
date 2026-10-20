import asyncio
import tempfile
import unittest
from pathlib import Path

from agent_sip.db import connect, migrate
from agent_sip.db.migrations import MIGRATIONS
from agent_sip.reminders.store import ReminderStore

DAY = 86_400


class ReminderStoreTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "reminders.db"
        self.conn = connect(self.path)
        migrate(self.conn, MIGRATIONS)
        self.store = ReminderStore(self.conn)

    async def asyncTearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    async def add(self, **kwargs):
        kwargs.setdefault("message", "msg")
        kwargs.setdefault("due_at", 100)
        kwargs.setdefault("tz", "UTC")
        kwargs.setdefault("phone", "phone")
        return await self.store.add(**kwargs)

    async def test_add_maps_every_column(self):
        reminder = await self.add(
            message="call the dentist",
            due_at=100,
            tz="Europe/Berlin",
            phone="handset",
            repeat="weekly",
            until=200,
            created_at=42,
        )
        self.assertIsNotNone(reminder.id)
        self.assertEqual(
            (
                reminder.message,
                reminder.due_at,
                reminder.tz,
                reminder.repeat,
                reminder.until,
                reminder.phone,
                reminder.status,
                reminder.attempts,
                reminder.next_try_at,
                reminder.created_at,
            ),
            (
                "call the dentist",
                100,
                "Europe/Berlin",
                "weekly",
                200,
                "handset",
                "pending",
                0,
                100,
                42,
            ),
        )

    async def test_add_defaults_next_try_at_to_due_at(self):
        reminder = await self.add(due_at=777)
        self.assertEqual(reminder.next_try_at, 777)

    async def test_get_returns_row_and_none_for_missing(self):
        reminder = await self.add()
        fetched = await self.store.get(reminder.id)
        self.assertEqual(fetched, reminder)
        self.assertIsNone(await self.store.get(999_999))

    async def test_delete_is_hard(self):
        reminder = await self.add()
        self.assertTrue(await self.store.delete(reminder.id))
        self.assertIsNone(await self.store.get(reminder.id))
        self.assertFalse(await self.store.delete(reminder.id))

    async def test_list_defaults_to_pending_and_filters_by_status(self):
        pending = await self.add(message="a")
        done = await self.add(message="b")
        await self.store.mark_delivered(done.id)

        self.assertEqual([r.id for r in await self.store.list()], [pending.id])
        self.assertEqual([r.id for r in await self.store.list("done")], [done.id])
        self.assertEqual([r.id for r in await self.store.list("missed")], [])
        self.assertEqual([r.id for r in await self.store.list(None)], [pending.id, done.id])

    async def test_next_due_ordering_and_none_when_empty(self):
        self.assertIsNone(await self.store.next_due())
        later = await self.add(due_at=500)
        sooner = await self.add(due_at=300)
        self.assertEqual(await self.store.next_due(), 300)
        await self.store.mark_delivered(sooner.id)
        self.assertEqual(await self.store.next_due(), 500)
        await self.store.mark_delivered(later.id)
        self.assertIsNone(await self.store.next_due())

    async def test_claim_due_only_due_pending_and_ordered(self):
        early = await self.add(due_at=100)
        mid = await self.add(due_at=200)
        await self.add(due_at=300)
        finished = await self.add(due_at=50)
        await self.store.mark_delivered(finished.id)

        claimed = await self.store.claim_due(200)
        self.assertEqual([r.id for r in claimed], [early.id, mid.id])
        self.assertEqual(await self.store.claim_due(50), [])

    async def test_mark_attempt_counts_and_optionally_reschedules(self):
        reminder = await self.add(due_at=100)
        updated = await self.store.mark_attempt(reminder.id, 160)
        self.assertEqual((updated.attempts, updated.next_try_at), (1, 160))

        updated = await self.store.mark_attempt(reminder.id)
        self.assertEqual((updated.attempts, updated.next_try_at), (2, 160))

    async def test_set_next_try_moves_time_without_counting_attempt(self):
        reminder = await self.add(due_at=100)
        await self.store.mark_attempt(reminder.id, 130)
        updated = await self.store.set_next_try(reminder.id, 200)
        self.assertEqual((updated.attempts, updated.next_try_at), (1, 200))
        # the due_at is untouched; only next_try_at moves
        self.assertEqual(updated.due_at, 100)
        self.assertIsNone(await self.store.set_next_try(999_999, 1))

    async def test_mark_delivered_and_missed(self):
        delivered = await self.add()
        missed = await self.add()
        await self.store.mark_delivered(delivered.id)
        await self.store.mark_missed(missed.id)
        self.assertEqual((await self.store.get(delivered.id)).status, "done")
        self.assertEqual((await self.store.get(missed.id)).status, "missed")

    async def test_reschedule_resets_attempts_and_moves_both_times(self):
        reminder = await self.add(due_at=100, repeat="daily")
        await self.store.mark_attempt(reminder.id, 130)
        updated = await self.store.reschedule(reminder.id, 86_500)
        self.assertEqual(
            (updated.due_at, updated.next_try_at, updated.attempts, updated.status),
            (86_500, 86_500, 0, "pending"),
        )

    async def test_update_changes_only_given_columns(self):
        reminder = await self.add(message="old", due_at=100, repeat="weekly", until=500)
        await self.store.mark_attempt(reminder.id, 130)
        updated = await self.store.update(
            reminder.id,
            message="new",
            due_at=200,
            until=None,
            status="pending",
            attempts=0,
            next_try_at=200,
        )
        self.assertEqual(updated.message, "new")
        self.assertEqual(updated.due_at, 200)
        self.assertIsNone(updated.until)
        self.assertEqual(updated.next_try_at, 200)
        self.assertEqual(updated.attempts, 0)
        self.assertEqual(updated.repeat, "weekly")  # untouched
        self.assertEqual(updated.phone, "phone")

    async def test_update_without_fields_is_a_noop_and_missing_is_none(self):
        reminder = await self.add(message="same")
        self.assertEqual(await self.store.update(reminder.id), reminder)
        self.assertIsNone(await self.store.update(999_999, message="x"))

    async def test_update_rejects_unknown_columns(self):
        reminder = await self.add()
        with self.assertRaises(ValueError):
            await self.store.update(reminder.id, created_at=1)

    async def test_purge_finished_respects_retention_window(self):
        now = 1_000_000_000
        old_done = await self.add(message="old", due_at=now - 10 * DAY)
        await self.store.mark_delivered(old_done.id)
        old_missed = await self.add(message="old missed", due_at=now - 8 * DAY)
        await self.store.mark_missed(old_missed.id)
        recent = await self.add(message="recent", due_at=now)
        await self.store.mark_missed(recent.id)
        pending = await self.add(message="pending", due_at=now - 30 * DAY)

        deleted = await self.store.purge_finished(keep_days=7, now=now)
        self.assertEqual(deleted, 2)
        self.assertIsNone(await self.store.get(old_done.id))
        self.assertIsNone(await self.store.get(old_missed.id))
        self.assertIsNotNone(await self.store.get(recent.id))
        self.assertIsNotNone(await self.store.get(pending.id))

    async def test_data_survives_reopening_the_database(self):
        reminder = await self.add(message="persist", due_at=1234)
        self.conn.close()

        self.conn = connect(self.path)
        store = ReminderStore(self.conn)
        self.assertEqual((await store.get(reminder.id)).message, "persist")

    async def test_concurrent_adds_do_not_corrupt_or_deadlock(self):
        results = await asyncio.wait_for(
            asyncio.gather(*(self.add(message=f"m{i}", due_at=i) for i in range(25))),
            timeout=10,
        )
        self.assertEqual(len({r.id for r in results}), 25)
        self.assertEqual(len(await self.store.list(None)), 25)

    async def test_one_shot_state_machine(self):
        reminder = await self.add(due_at=100)
        self.assertEqual([r.id for r in await self.store.claim_due(100)], [reminder.id])
        await self.store.mark_attempt(reminder.id, 130)
        await self.store.mark_delivered(reminder.id)
        final = await self.store.get(reminder.id)
        self.assertEqual((final.status, final.attempts), ("done", 1))

    async def test_recurring_state_machine(self):
        reminder = await self.add(due_at=100, repeat="daily")
        await self.store.mark_attempt(reminder.id, 130)
        await self.store.reschedule(reminder.id, 100 + DAY)
        final = await self.store.get(reminder.id)
        self.assertEqual(
            (final.status, final.attempts, final.due_at, final.next_try_at),
            ("pending", 0, 100 + DAY, 100 + DAY),
        )
        self.assertEqual([r.id for r in await self.store.claim_due(100 + DAY)], [reminder.id])


if __name__ == "__main__":
    unittest.main()
