<!--
Template: 🧹 Refactor / ⚡ performance
Title format:  refactor(<scope>): <imperative summary>  OR  perf(<scope>): <summary>
Example:       refactor(sip): extract dialog state from the server loop
Use this when behavior must NOT change. Delete these comments after filling.
-->

## 🧭 At a glance

| | |
|---|---|
| 🧹 **Type** | Refactor (`refactor:`) · ⚡ Performance (`perf:`) |
| 🧩 **Area** | `sip` · `audio` · `stt` · `tts` · `agent` · `assistant` · `config` |
| 🛡️ **Behavior change** | None intended |
| 🚦 **Risk** | 🟢 Low |
| 🔗 **Closes** | # |

> [!TIP]
> **TL;DR** — _What was restructured or sped up, and the guarantee that external behavior is
> unchanged (or the exact measurable improvement)._

---

## 💭 Motivation

_Why do this now? Maintenance pain, duplication, hot path, testability, a prerequisite for
another change. What goes wrong if we don't._

---

## 🔧 What changed

- 🧱 **Restructured:** _…_
- ✂️ **Extracted/replaced:** _…_
- ➖ **Deleted:** _…_

### 🔀 Before → after

<table>
<tr><th>❌ Before</th><th>✅ After</th></tr>
<tr><td>

```python
# old shape
```

</td><td>

```python
# new shape
```

</td></tr>
</table>

---

## 🛡️ Behavior preservation

> [!IMPORTANT]
> Refactors must be behavior-neutral. State how you know.

- [ ] Public APIs and protocols unchanged (or list deviations explicitly)
- [ ] Audio format unchanged (8 kHz mono int16 `array('h')`)
- [ ] Existing tests pass unmodified
- [ ] _Any intentional behavior change is called out here and in the CHANGELOG_

---

## ⚡ Performance evidence

_Delete if this is a pure refactor._

| 📊 Metric | 🔴 Before | 🟢 After | 🔬 How measured |
|---|---|---|---|
| _e.g. CPU per call_ | _…_ | _…_ | _…_ |

**🧪 Methodology:** _hardware, workload, command, iterations._

---

## 🧪 Testing

```sh
make test
make lint
```

Result: _…_

**📞 Manual:** _reproduce the same scenario before/after and compare._

---

## 🔍 How to review

1. 🧱 _Focus on the mechanical moves separately from the semantic changes._
2. 🔎 _Look for missed call sites or subtly different error handling._
3. 🕵️ _Confirm no behavior was smuggled in under the refactor._

---

## ⚠️ Risk & rollback

| | |
|---|---|
| 🚨 **Risk** | _regression despite passing tests; where to look._ |
| ⏪ **Rollback** | revert this PR; _migration or "none"._ |

---

## ✅ Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] No functional change intended (documented above)
- [ ] `CHANGELOG.md` updated only if user-visible
- [ ] No unrelated changes mixed in

---

## 📎 References

- 🔗 Related issue/PR: #
