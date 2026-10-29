<!--
Template: 🐛 Bug fix
Title format:  fix(<scope>): <imperative summary>
Example:       fix(sip): retransmit 200 OK until ACK
Fill every section, then delete these comments.
The most important parts are the reproduction and the confidence that this fixes the cause,
not just the symptom.
-->

## 🧭 At a glance

| | |
|---|---|
| 🐛 **Type** | Bug fix (`fix:`) |
| 🧩 **Area** | `sip` · `audio` · `stt` · `tts` · `agent` · `assistant` · `config` · `tools` |
| 🚦 **Severity** | 🟢 Low · 🟡 Medium · 🔴 High (data loss, crash, call drop…) |
| ↩️ **Regression?** | Yes / No — introduced in `vX.Y.Z` / PR # |
| 🔗 **Closes** | # |

> [!TIP]
> **TL;DR** — _What was broken, who hit it, and what now happens instead._

---

## 🐛 The bug

_Describe the observable symptom in plain language. What did the user see or hear? How was it
detected?_

| | |
|---|---|
| ✅ **Expected** | _…_ |
| ❌ **Actual** | _…_ |

### 🔁 Reproduction

<details>
<summary>🔁 Steps to reproduce on the previous revision (expand)</summary>

1. _Configuration used._
2. _Action (dial, hang up, send audio…)._
3. _Observed failure, with logs/traceback._

```text
<paste relevant logs, with secrets removed>
```

</details>

---

## 🎯 Root cause

_Explain the actual cause. "The order of X and Y caused Z" beats "it was broken". If the cause
was not fully identified, say so and describe the evidence for the best hypothesis._

---

## 🩹 The fix

_What you changed and how it addresses the root cause. Link to the code region._

- _…_

> [!IMPORTANT]
> **Why this is the right layer to fix it:** _not the caller, not a workaround._

### 💣 How big is the blast radius?

| | |
|---|---|
| 🎯 **Touched** | _modules/callers affected_ |
| 🛡️ **Untouched** | _what deliberately stays the same_ |
| 🔁 **Behavior changes** | _any side effects reviewers should expect_ |

---

## 🧪 Verification

**🤖 Automated**

```sh
make test
make lint
```

Result: _…_

**↩️ Regression test added?** Yes / No — if no, why not.

**📞 Manual check on the failing path**

1. _Reproduce the original scenario and confirm it now behaves correctly._
2. _Confirm adjacent behavior still works._

---

## 🔍 How to review

1. 🔁 _Reproduce mentally from the "Steps to reproduce" above._
2. 🎯 _Confirm the root cause section matches the diff._
3. 🧪 _Check the regression test would have failed before the fix._

---

## ⚠️ Risk & rollback

| | |
|---|---|
| 🚨 **Risk** | _…_ |
| ⏪ **Rollback** | revert this PR; _state any migration/cleanup or "none"._ |

---

## ✅ Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] Regression test added (or explanation why not)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No unrelated refactoring mixed in

---

## 📎 References

- 🔗 Related issue/PR: #
- 💣 Commit that introduced the bug: `<sha>`
