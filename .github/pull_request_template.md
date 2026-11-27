<!-- Title: Conventional Commit, e.g. `fix(sip): retransmit 200 OK until ACK`.
     Keep it short. Delete every comment and any section that does not apply. -->

## Summary

<!-- 1-3 plain sentences: what changes for the person on the phone (or "no user-visible
     change") and why. Bug fix: symptom -> root cause -> fix. -->

Closes #

## Changes

<!-- Bullets, most important first. Name files only when it helps the review. -->

-

## Review focus

<!-- Where to look first and what could break (SIP/RTP state, concurrency, event-loop
     blocking, DB schema, config defaults). "Mechanical change" is a valid answer. -->

## Verification

- `make check`: <!-- passed locally / CI only -->
- Tests: <!-- added or changed; for a fix, does the new test fail without the fix? If no
  test, say why. -->
- Phone: <!-- not needed | NOT DONE, maintainer to check: dial ..., expect ... | done: ... -->

## Notes

<!-- Only what applies, else delete the section:
     - Breaking or behavior change (refactor: "none intended" + how you know)
     - New or changed config key (dataclass + config.example.toml)
     - CHANGELOG: entry under [Unreleased], or "not user-visible"
     - Rollback beyond a plain revert: a revert only reaches the server with the next
       release; data or config written by this change stays
     - Follow-ups -->

<details>
<summary>Approved plan</summary>

<!-- Plan-mode plan, verbatim. Note any deviation under "Changes". Delete if none. -->

</details>
