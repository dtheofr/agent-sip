<!--
Template: Tests
Title format:  test(<scope>): <imperative summary>
Example:       test(sip): cover retransmission under packet loss
Use this for test-only changes. Delete these comments after filling.
-->

## At a glance

| | |
|---|---|
| **Type** | Tests (`test:`) |
| **Area** | unit / loopback SIP / integration |
| **Production code changed** | No |
| **Closes** | # |

> **TL;DR** —
> _Which behavior is now covered, and what bug or gap motivated the new tests._

## Coverage gap

_What was untested or under-tested? Was there a bug that slipped through, and would these
tests have caught it?_

- _…_

## What was added / changed

| Test file | New/updated cases | Verifies |
|---|---|---|
| `tests/…` | _…_ | _…_ |

_Distinguish unit tests from the end-to-end loopback call flow (`tests/` uses real
SIP/RTP sockets on localhost)._

## How the tests work

_Explain non-obvious setup: fake providers, audio fixtures, timing, ports. Note anything a
future maintainer could easily break._

## Reliability

- **Runtime:** _before → after (`make test`)._
- **Flakiness:** _do these rely on timing/sockets? How is that made deterministic?_
- **Isolation:** _ports and temp files cleaned up; no shared state between tests._

## Verification

```sh
make test
make lint
```

Result: _…_

**Do the new tests fail against the unfixed code?** Yes / No — _evidence (e.g. revert and run)._

## How to review

1. _Confirm each test asserts meaningful behavior, not implementation details._
2. _Check that a broken implementation would actually fail these tests._
3. _Look for sleeps, fixed ports, or order dependence._

## Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] Tests are deterministic and isolated
- [ ] No production code changed (or explain why a tiny seam was needed)
- [ ] `CHANGELOG.md` — usually not needed for test-only changes

## References

- Related issue/PR: #
