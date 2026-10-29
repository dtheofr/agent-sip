<!--
You are viewing the default pull request template.

Pick the template that matches your change:
  1. Click one of the links below (opens a new pull request pre-filled with that template), or
  2. Use the "Choose a template" dropdown when creating the pull request.

If you are an agent filling this in: choose the single best-matching template, open every
<details> block, replace every placeholder, then delete the guidance comments.
-->

# 🧵 Choose a pull request template

> [!NOTE]
> **TL;DR** — Pick the template that matches the **kind of work**, not the file you touched.
> Each one keeps the top of the PR skimmable for a reviewer who lacks context, with the
> long-form detail collapsed below.

| 🏷️ Kind of work | 🕐 Use when… | 📄 Template |
|---|---|---|
| ✨ Feature | New capability or user-visible behavior (`feat:`) | [**Open feature template**](?template=feature.md&expand=1) |
| 🐛 Bug fix | Something is broken (`fix:`) | [**Open bugfix template**](?template=bugfix.md&expand=1) |
| 📚 Documentation | README, `docs/`, `AGENTS.md`, docstrings (`docs:`) | [**Open docs template**](?template=docs.md&expand=1) |
| 🧹 Refactor / ⚡ performance | No behavior change intended (`refactor:`/`perf:`) | [**Open refactor template**](?template=refactor.md&expand=1) |
| 🧪 Tests | Test-only changes (`test:`) | [**Open test template**](?template=test.md&expand=1) |
| 🚦 CI / 📦 build / 🏷️ release | Workflows, packaging, release tooling (`ci:`/`build:`) | [**Open CI template**](?template=ci.md&expand=1) |
| 🧹 Chore / 📦 deps / ⚙️ config | Dependency bumps, tooling, defaults (`chore:`) | [**Open chore template**](?template=chore.md&expand=1) |
| ⏪ Revert | Undoing a merged change (`revert:`) | [**Open revert template**](?template=revert.md&expand=1) |

---

## 🤔 Not sure which to pick?

| If it… | Then… |
|---|---|
| ➕ **adds** behavior | ✨ **Feature** |
| 🔧 **restores** behavior | 🐛 **Bug fix** |
| 🛡️ leaves behavior **unchanged** | 🧹 **Refactor** |
| 📄 only touches docs / tests / pipelines / deps | the matching one |

---

## ✅ Every PR must

> [!IMPORTANT]
> `main` is protected: a PR needs **at least one approval** and **green CI** before merge.

- [ ] Pass `make test` and `make lint`
- [ ] Be based on an up-to-date `main`, with a **Conventional Commits** title
      (`feat:` · `fix:` · `docs:` · `refactor:` · `perf:` · `test:` · `ci:` · `build:` · `chore:` · `revert:`)
- [ ] Update `CHANGELOG.md` under `[Unreleased]` when the change is user-visible
- [ ] Avoid committing secrets — `config.toml` stays untracked
