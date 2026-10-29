<!--
Template: ⏪ Revert
Title format:  revert: <what is being reverted>
Example:       revert: "feat(sessions): resume conversations between calls"
Use this to undo a previously merged change. Delete these comments after filling.
-->

## 🧭 At a glance

| | |
|---|---|
| ⏪ **Type** | Revert (`revert:`) |
| ↩️ **Reverts** | # / `<sha>` |
| 🚨 **Urgency** | 🔥 Immediate (production impact) · 🧊 Normal |
| 🔗 **Closes** | # |

> [!NOTE]
> **TL;DR** — _Which change is being backed out and the reason, in one or two sentences._

---

## 🔎 What is being reverted

| | |
|---|---|
| 🔗 **PR/commit** | # / `<sha>` |
| 📝 **Original title** | _…_ |
| 🏷️ **Merged in** | `vX.Y.Z` |

---

## ❓ Why

_What went wrong. Prefer facts and evidence (logs, failing calls, error rates) over
speculation. If the original change is being fixed-forward instead, explain why revert is
still the right move._

---

## ♻️ What this restores

_Describe the behavior readers will get back. Note anything that will be lost and will need a
follow-up (e.g. a feature users already started using, data written by the reverted code)._

> [!WARNING]
> Call out any data or config written by the reverted change that this PR does **not** undo.

---

## 🧪 Verification

```sh
make test
make lint
```

Result: _…_

**📞 Manual:** _reproduce the regression and confirm it is gone._

- [ ] Revert is clean (no unrelated changes absorbed from the revert)
- [ ] Any data/config introduced by the reverted change is handled or documented

---

## 🔍 How to review

1. 🔁 _Confirm the diff is the inverse of the original change (and nothing else)._
2. 🧪 _Confirm tests that were added by the original change are also reverted, if appropriate._
3. ➡️ _Check the follow-up plan below._

---

## ➡️ Follow-up

- 🎟️ _Is a fixed-forward plan being tracked? Link the issue._
- 🧹 _Any migration/cleanup required for data or config._

---

## ✅ Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Follow-up issue opened
