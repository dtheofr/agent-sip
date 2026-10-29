# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.1] - 2026-10-29

### Changed

- Releases are now created automatically after CI succeeds on `main` when `__version__` is a
  new stable version. The workflow builds the distribution, creates the GitHub Release,
  attaches the artifacts and deploys that commit.

### Added

- Project hygiene for open-source collaboration: Apache-2.0 license, contributing and
  security guides, code of conduct, type-specific pull request templates, issue forms,
  CODEOWNERS and Dependabot configuration.

## [0.8.0] - 2026-10-29

### Added

- Versioning and release plumbing: changelog, tags, and a GitHub Release workflow that
  verifies the tag, attaches the build and deploys it instead of deploying every push to
  `main`.

### Changed

- The package version now lives only in `src/agent_sip/__init__.py`; `pyproject.toml`
  reads it dynamically.
- `agent-sip --version` reports the package version, and the startup banner includes it.
- The web tools' HTTP `User-Agent` is derived from the package version.

## Pre-versioning history

The project was not tagged before 0.8.0. These milestones map the existing history for
reference:

| Version | Milestone | Commit |
|---|---|---|
| 0.1.0 | SIP/RTP, configuration, STT/TTS contracts | `dfdeabe` |
| 0.2.0 | LLM agent, VAD, barge-in, assistant loop | `b49ad6b` |
| 0.3.0 | Tool calling and `get_current_datetime` | `27483cc` |
| 0.4.0 | Earcons (beep and waiting melody) | `cb4202c` |
| 0.5.0 | `web_search` and `fetch_url` | `8760a2f` |
| 0.6.0 | Phone reminders and scheduler | `455762c` |
| 0.7.0 | `update_reminder` and busy-phone handling | `dec8556` |
