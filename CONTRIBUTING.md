# Contributing to agent-sip

Thanks for your interest in improving agent-sip. This document explains how to set up the
project, what we expect from a change, and how it gets merged. For a deeper tour of the
architecture and conventions, read [`AGENTS.md`](AGENTS.md).

## Development setup

Requires Python ≥ 3.11 and `make`.

```sh
make install   # create .venv, install the project with dev + VAD extras, fetch the Silero model
make test      # unit tests plus a loopback SIP call (no install needed: PYTHONPATH=src)
make lint      # ruff, line length 100
make run       # copy config.example.toml to config.toml and start the server
```

`config.toml` is intentionally untracked; start from `config.example.toml` and never commit
real credentials.

## Before you open a pull request

- `make test` passes.
- `make lint` is clean.
- New behavior is covered by tests where practical (the suite already exercises the SIP
  loopback path end to end).
- User-visible changes are added to `CHANGELOG.md` under `## [Unreleased]`.
- Public APIs and protocols in `src/agent_sip/*/base.py` stay small and documented.

## Branching and commits

`main` is protected: every change lands through a pull request with **at least one approval**
and green CI (tests on 3.11–3.13 and lint). Branch names are free-form but descriptive, e.g.
`feat/reminders` or `fix/200-ok-retransmit`.

Write commit messages in [Conventional Commits](https://www.conventionalcommits.org/) form,
matching the existing history:

```
feat(sessions): resume conversations between calls
fix(sip): retransmit 200 OK until ACK
ci(release): deploy published releases
docs(readme): describe the config file
chore(release): prepare 0.9.0
```

Keep pull requests focused. One logical change per PR is easier to review and revert.

When you open the PR, choose the template that matches the **kind of work** — feature, bug
fix, docs, refactor/performance, tests, CI/build/release, chore/dependencies, or revert. Each
template keeps the top of the description skimmable for a reviewer who lacks context and
asks for the details (root cause, risk, verification, how to review) in collapsible sections
below.

## Versioning and releases

- `src/agent_sip/__init__.py` holds the single `__version__`; `pyproject.toml` reads it
  dynamically. Never edit the version in two places.
- Releases follow [Semantic Versioning](https://semver.org/) and are published as GitHub
  Releases tagged `vX.Y.Z`. See `AGENTS.md` for the release steps.

## Reporting bugs and security issues

- Bugs and feature requests: use the issue templates.
- Security vulnerabilities: **do not** open a public issue — follow [`SECURITY.md`](SECURITY.md).

By participating you agree to abide by the [Code of Conduct](.github/CODE_OF_CONDUCT.md).
Contributions are accepted under the [Apache-2.0](LICENSE) license.
