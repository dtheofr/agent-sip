<!--
Template: 🚦 CI, build & release
Title format:  ci(<scope>): <imperative summary>  OR  build(...)  OR  chore(release): ...
Example:       ci(release): auto-release stable version bumps after CI
Use this for .github/workflows, pyproject/build config, and release tooling.
Delete these comments after filling.
-->

## 🧭 At a glance

| | |
|---|---|
| 🚦 **Type** | CI (`ci:`) · 📦 Build (`build:`) · 🏷️ Release (`chore(release):`) |
| 📄 **Workflows touched** | `ci.yml` · `release.yml` · other |
| 🔑 **Requires new secrets** | Yes (list below) / No |
| 🛡️ **Affects `main` protection** | No / Yes |
| 🔗 **Closes** | # |

> [!NOTE]
> **TL;DR** — _What the pipeline does differently now, and what a contributor or release
> manager will notice._

---

## 💭 Motivation

_What was wrong, slow, manual, or unsafe? What happens today that shouldn't, or vice versa._

---

## 🔧 What changed

- 🎬 _Triggers/`on:` changes._
- 🧱 _Jobs/steps added, removed, reordered._
- 🔐 _`permissions:` and concurrency changes._

### 🔀 Workflow diagram

_Before → after, if the flow is non-trivial._

```text
push → CI → release (only if version bumped) → build → deploy
```

---

## 🔐 Permissions & secrets

> [!WARNING]
> Pipelines are a security boundary. Be explicit about what runs and with what rights.

| Item | Scope | Purpose | Pre-existing? |
|---|---|---|---|
| `GITHUB_TOKEN` | `contents: write` | _create release_ | ✅ Yes |
| `DEPLOY_SSH_PRIVATE_KEY` | repo secret | _ssh to server_ | ✅ Yes |
| _new secret_ | _…_ | _…_ | ❗ **No — must be added** |

- [ ] No secret values appear in logs or in the diff
- [ ] Third-party actions are pinned to a version tag (and trusted)
- [ ] `GITHUB_TOKEN` scoped to the minimum needed

---

## 🧑‍💻 Effect on contributors

- 🔔 _New checks that become required on `main` (names must match the branch ruleset exactly)._
- 🔁 _Any change to required status checks or job names._
- 🍴 _Impact on forks / external contributors._

---

## 🧪 Verification

> [!NOTE]
> CI changes cannot be fully tested like application code — describe how you validated them.

- [ ] `actionlint .github/workflows/*.yml` clean
- [ ] YAML parses
- [ ] Ran the equivalent steps locally where possible: _…_
- [ ] Dry-run / test branch run: _link_

**🏷️ Release specifically**

- [ ] Tag/version check still matches `__version__` and `CHANGELOG.md`
- [ ] Deploy still gated on a successful build
- [ ] Rollback path if deploy fails mid-release: _…_

---

## 🔍 How to review

1. 🎬 _Read the `on:`/`permissions:` blocks first — they decide when and with what rights this runs._
2. 🛤️ _Trace the happy path and one failure path._
3. 🔔 _Confirm required-check names match the branch ruleset._

---

## ⏪ Rollback

_Revert this PR. Note any published tags, releases, or deployments that need manual cleanup._

---

## ✅ Checklist

- [ ] `make test` and `make lint` still pass
- [ ] Branch-protection required check names considered
- [ ] New secrets documented (and added by the maintainer)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for user-visible changes
- [ ] `AGENTS.md` release notes updated if the process changed

---

## 📎 References

- 🔗 Related issue/PR: #
