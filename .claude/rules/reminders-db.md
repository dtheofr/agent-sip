---
paths:
  - "src/agent_sip/reminders/**"
  - "src/agent_sip/db/**"
  - "tests/test_reminder*.py"
  - "tests/test_db.py"
---
# Reminders and SQLite
- `db/migrations.py` is append-only: never edit or reorder a shipped entry.
- `ReminderStore` is the only SQL user; every public method is async (`to_thread` + lock).
- Attempts are persisted BEFORE ringing (crash safety); keep that ordering.
- Recurrence math works on local wall-clock time in the reminder's own `tz` (DST-safe).
- Scheduler and tools take an injected `now`; tests never sleep for real time.
- Delivery is confirmed by the handler through `call.metadata["on_opening_done"]`.
