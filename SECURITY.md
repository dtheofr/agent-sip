# Security Policy

## Supported versions

Security fixes are applied to the latest released version. Please make sure you are on the
most recent tag before reporting an issue.

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| older   | :x:                |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues, discussions,
or pull requests.**

Report them privately using GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
(**Security** tab → **Report a vulnerability**), or by email to the repository owner.

Please include:

- a description of the issue and its impact;
- the affected version or commit;
- steps to reproduce, or a proof of concept;
- any suggested mitigation.

You can expect an acknowledgement within a few days. We will keep you informed of the
progress toward a fix and credit you in the release notes unless you prefer to stay anonymous.

## Scope and hardening notes

This project exposes a SIP listener and, optionally, network calls to STT/TTS/LLM providers.
When deploying:

- Treat `config.toml` as a secret; it can contain API keys and is not tracked by git.
- Do not expose the SIP/RTP ports to the public internet without a firewall or proxy.
- Run the service as an unprivileged user.
