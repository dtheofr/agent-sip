<!--
Template: Documentation
Title format:  docs(<scope>): <imperative summary>
Example:       docs(readme): describe the config file
Use this for README, CONTRIBUTING, AGENTS.md, docs/*, config.example.toml comments and
code docstrings. Delete these comments after filling.
-->

## At a glance

| | |
|---|---|
| **Type** | Documentation (`docs:`) |
| **Audience** | New users / operators / contributors / API consumers |
| **Files** | `README.md` / `docs/…` / `CONTRIBUTING.md` / docstrings |
| **Closes** | # |

> **TL;DR** —
> _Which document changed and what a reader now understands that they did not before._

## Why

- **Reader problem:** _what confusion, gap, or wrong statement prompted this._
- **Trigger:** _new feature, user question, drift from the code, broken link._

## What changed

- _Document(s) and sections rewritten/added/removed._
- _Corrections: quote the old claim and the new claim if it was wrong._

| Path | Before | After |
|---|---|---|
| `README.md` | _…_ | _…_ |

## Accuracy check

_Docs must match the code. Confirm each claim against the source._

- [ ] Commands/paths/config keys verified against the repository
- [ ] New keys exist in both the config dataclass and `config.example.toml`
- [ ] No step depends on behavior that no longer exists
- [ ] Versioning/release notes still consistent with `AGENTS.md`

## How to review

1. _Read as the target audience would, top to bottom, without prior context._
2. _Check the "Accuracy check" list against the code._
3. _Confirm links render and point to real files/anchors._

**Preview:** _how you rendered/checked it (e.g. `gh markdown`? GitHub diff? local viewer)._

## Checklist

- [ ] Internal links resolve
- [ ] Code blocks are copy-pasteable and correct
- [ ] Tone/terminology matches the rest of the project
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if user-visible

## References

- Related issue/PR: #
