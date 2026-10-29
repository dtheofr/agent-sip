<!--
Template: Chore / dependencies / configuration
Title format:  chore(<scope>): <imperative summary>
Example:       chore(deps): bump onnxruntime to 1.20
Use this for maintenance that is not a feature, fix, refactor, docs, or CI change:
dependency bumps, tooling, default config, housekeeping.
Delete these comments after filling.
-->

## At a glance

| | |
|---|---|
| **Type** | Chore (`chore:`) |
| **Kind** | Dependency bump / Tooling / Default config / Housekeeping |
| **Runtime impact** | None / _describe_ |
| **Closes** | # |

> **TL;DR** —
> _What housekeeping was done and why it is safe._

## Motivation

_Why now? Security advisory, upstream release, unblocker, cleanup. Link the advisory or
release notes._

## What changed

| Item | From | To | Notes |
|---|---|---|---|
| _package_ | _x.y_ | _x.z_ | _link to upstream changelog_ |

_For config defaults, list the key and old/new default. For tooling, describe the change._

### Dependency review

_Delete if not a dependency bump._

- **Release notes / changelog:** _link_
- **Breaking changes:** none / _list, with impact_
- **License of new/updated dep:** _compatible with Apache-2.0? (MIT/BSD/Apache: yes; GPL/AGPL: call out)_
- **Transitive changes:** _…_

## Compatibility

- **Python versions:** still `>=3.11`; checked against _…_
- **Optional extras:** `stt` / `vad` / `dev` still resolve
- **Platforms:** _linux/macOS, as applicable_

## Verification

```sh
make test
make lint
```

Result: _…_

Manual smoke test: _only for default-config changes — describe what you ran._

## How to review

1. _Confirm the version bump matches the stated intent._
2. _Skim upstream release notes for breaking changes affecting our usage._
3. _For config defaults: confirm both the dataclass and `config.example.toml` changed together._

## Risk & rollback

- **Risk:** _…_
- **Rollback:** revert this PR; _migration or "none"._

## Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] Config dataclass and `config.example.toml` updated together (if config changed)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if user-visible
- [ ] No secrets committed

## References

- Upstream changelog: _link_
- Related issue/PR: #
