# agent-sip

Talk to AI agents from an analog phone over SIP. Personal project first: a Socotel
phone behind a Linksys ATA on the LAN. Favour simplicity and LAN robustness over
SIP feature completeness.

## Commands
- `make check` (lint + tests): run before saying "done". Never skip or weaken a test.
- `make test` · `make lint` · `make fmt` · `make cov` · `make run`
- One test: `PYTHONPATH=src python -m unittest tests.test_call_flow -v`
- Tests are stdlib-only (`PYTHONPATH=src`) and include a loopback SIP call.

## Layout
- `src/agent_sip/sip/`: SIP/RTP transport, app-agnostic (see `.claude/rules/sip.md`).
- `audio/`: VAD, recorder, barge-in, earcons, decoding/resampling.
- `stt/`, `tts/`, `agent/`: each exposes a small `Protocol` in `base.py`; implementations
  live alongside and target OpenAI-shaped APIs (configurable base_url / api_key / model /
  voice), so any compatible server works.
- `reminders/`, `db/`: reminder store + scheduler on SQLite
  (see `.claude/rules/reminders-db.md`).
- `assistant.py`: the call loop (listen → STT → agent → TTS). `echo.py`: STT → TTS
  reference handler.
- `__main__.py`: CLI and wiring only (`build_app`).
- `config.py`: dataclasses; defaults < TOML < env `AGENT_SIP_<PATH>_<KEY>`.
- `prompts/system.md`: system prompt. Output is spoken: plain text, no markdown.
- `examples/poc_sip.py`: original single-file proof of concept, reference only.

## Invariants
- Audio is always 8 kHz mono int16 `array('h')`; 20 ms = 160 samples.
- asyncio everywhere. Never block the event loop: HTTP, SQL, ffmpeg and CPU-bound work
  go through `asyncio.to_thread`.
- Core stays stdlib-only; heavy deps go in optional extras in `pyproject.toml`.
- Python ≥ 3.11, ruff line length 100 (a hook lints and formats edited files).
- New config key: dataclass field + `config.example.toml` (`tests/test_config.py`
  enforces it). Env override works automatically.

## Adding an LLM tool
- Static tool: `@tool(...)` in `agent/tools.py`. Configured or per-call tool: a factory
  returning `list[Tool]` (see `web_tools`, `reminder_tools`), wired in `build_app`.
- Return a string; let exceptions propagate (the registry reports them to the model).
- Add a test, and a line in `prompts/system.md` if the model needs guidance.

## Workflow
Work runs autonomously; the maintainer's checkpoint is the PR review.
`.github/workflows/claude.yml` starts Claude (GitHub Actions) when the maintainer opens an
issue (forms in `.github/ISSUE_TEMPLATE/`, or a blank one-liner), replies on an open issue,
reviews a PR Claude opened, or writes `@claude` on any PR. Nobody else can trigger it; the
`no-claude` label opts an issue out. That run has no human in the loop: when it must wait,
it comments and stops, and the next maintainer reply resumes it from the issue.
Its instructions are the `issue-workflow` skill (`.claude/skills/issue-workflow/`).
1. A GitHub issue is the unit of work. The maintainer writes it (often one line), or
   Claude opens one for a bug or follow-up it finds but does not fix now.
2. Before coding, comment a short plan on the issue: approach, PR breakdown, risks.
   Then proceed without waiting, unless the change is in the ask-first list below:
   in that case wait for the maintainer's answer on the issue.
3. One logical change per PR. Multi-PR work: keep a checklist in the issue, tick it as
   PRs merge, and put `Closes #N` on the last PR only (`Part of #N` on the others).
   The issue, not session memory, is where the next session picks up.
4. The PR review is the gate: address review comments, never merge your own PR.
5. Releases follow "Versioning and release" below.

Ask first (comment on the issue and wait) when the change:
- adds or edits a DB migration;
- changes SIP/RTP behaviour as seen by the ATA (messages, timers, codecs);
- adds a dependency, even optional;
- changes a config default or removes a config key;
- removes a feature or a tool the agent can call;
- or when the request is ambiguous enough that two reasonable readings differ.

Conventional Commits (`feat(sip): …`, `fix(reminders): …`). User-visible change →
`CHANGELOG.md` under `[Unreleased]`.

## Pull requests
- The API does not apply templates: read `.github/pull_request_template.md` (or
  `.github/PULL_REQUEST_TEMPLATE/release.md` for a release) and fill it. Delete every
  comment and every section that does not apply.
- PR title in English (Conventional Commit); PR body in French, like the templates.
- The maintainer reviews on a phone: summary first, plain prose, no wide tables, about
  300 words outside the plan. One emoji per section heading (as in the template), none
  in the text.
- Never claim a check you did not run. From a cloud session the phone line is always
  `NON FAIT, à vérifier : …` with what to dial and what to expect.
- Fix: give the root cause and whether the new test fails without the fix. Refactor:
  say how you know behaviour is preserved.
- `📋 Plan` block: link the plan comment on the issue (or paste the plan when there is
  no issue) and list any deviation under `Changements`.
- `Closes #N` (or `Part of #N`) on its own line so GitHub links and closes the issue.

## Versioning and release
- SemVer. `__version__` in `src/agent_sip/__init__.py` is the only version;
  `pyproject.toml` reads it dynamically.
- A new stable version merged to `main` triggers a GitHub Release and a deploy, so a
  version bump is always its own `chore(release): X.Y.Z` PR, never mixed with feature or
  fix commits.
- Pick the bump from `[Unreleased]` (pre-1.0): any `feat` or breaking change → minor,
  only fixes → patch. Release when `[Unreleased]` holds a coherent set of changes and
  `make check` is green on `main`.
- Release PR (template `release.md`): move `[Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`,
  bump `__version__`, paste the CHANGELOG section and justify the bump in the PR body.
  `.dev`/pre-release versions are skipped by the workflow; every stable version needs a
  `CHANGELOG.md` section.

## Secrets and hardware
- Never read or print `config.toml`, `.env` or `data/`; use `config.example.toml`.
- No real phone from a cloud session: cover SIP changes with a loopback test in
  `tests/test_call_flow.py` and describe the manual phone check in the PR.
