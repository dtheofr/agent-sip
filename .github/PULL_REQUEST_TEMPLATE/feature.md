<!--
Template: ✨ Feature
Title format:  feat(<scope>): <imperative summary>
Example:       feat(sessions): resume conversations between calls
Fill every section, then delete these comments.
Keep the TL;DR to 1-3 plain-language sentences: what a user can now do, and what changed.
-->

## 🧭 At a glance

| | |
|---|---|
| ✨ **Type** | Feature (`feat:`) |
| 🧩 **Area** | `sip` · `audio` · `stt` · `tts` · `agent` · `assistant` · `config` · `tools` |
| 🚦 **Risk** | 🟢 Low |
| 💥 **Breaking change** | No |
| 🔗 **Closes** | # |

> [!TIP]
> **TL;DR** — _One to three sentences a reviewer can read cold: what the caller/user can now
> do, what was added, and whether it is on by default._

---

## 📝 Summary

_What problem does this solve, and for whom? Write it as if the reviewer has never seen the
task. Avoid jargon or define it on first use._

### 🧠 Background

<details>
<summary>🧠 Context a reviewer without prior knowledge should have (expand)</summary>

- _Why this matters now / what prompted it._
- _Any related design notes in `docs/`, prior PRs, or issues._
- _Relevant SIP/RTP/audio constraints (e.g. 8 kHz mono int16, UDP only, PCMU only)._

</details>

---

## 🔧 What changed

- ➕ **Added:** _new modules, config, handlers, tools…_
- 🔁 **Changed:** _behavior or APIs that moved._
- ➖ **Removed:** _anything deleted and why._

### 📂 Files of interest

| Path | 👀 What to look at |
|---|---|
| `src/agent_sip/…` | _…_ |
| `tests/…` | _…_ |
| `docs/…` | _…_ |

---

## 🛠 How it works

_Explain the design and data flow. Mention alternatives you rejected and why. For signalling
or audio changes, describe the sequence end to end (a diagram or trace helps)._

```text
phone ⇄ SIP/RTP ⇄ STT → Agent → TTS ⇄ phone
```

**🔑 Key decisions**

- _Decision — rationale, trade-off._

**🧯 Edge cases handled**

- _e.g. concurrent calls, remote hangup mid-prompt, empty transcript._

---

## ⚙️ Configuration

_Delete this section if nothing is configurable._

| Key | Default | Meaning |
|---|---|---|
| `[section].key` | `…` | _…_ |

- [ ] Added to the settings dataclass in `src/agent_sip/config.py`
- [ ] Documented in `config.example.toml`

---

## 🧪 Testing

**🤖 Automated**

```sh
make test
make lint
```

Result: _e.g. 153 tests OK; ruff clean._

**📞 Manual / end-to-end**

1. _Steps to exercise the feature (config, dialing, expected audio/behavior)._
2. _…_

---

## 🔍 How to review

1. 🎯 _Start with `…` — this is the heart of the change._
2. 🔎 _Then check `…` for correctness._
3. 🧐 _Scrutinize `…` (concurrency, error paths, cleanup)._

---

## ⚠️ Risk, rollout & rollback

| | |
|---|---|
| 🚨 **Risk** | _what could go wrong, who is affected._ |
| 🚀 **Rollout** | _default on/off, migration, feature flag._ |
| ⏪ **Rollback** | _revert this PR — describe any cleanup/migration needed (or "none")._ |

---

## ✅ Checklist

- [ ] `make test` passes
- [ ] `make lint` is clean
- [ ] Tests cover the new behavior
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No blocking calls in handlers (`asyncio.to_thread` for CPU-bound work)
- [ ] `config.example.toml` and the config dataclass updated (if config changed)
- [ ] No secrets or real credentials committed (`config.toml` stays untracked)

---

## 📎 References

- 🔗 Related issue/PR: #
- 📄 Design note: `docs/…`
