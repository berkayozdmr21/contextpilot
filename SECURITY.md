# Security and local data

The default ContextPilot core has no network client, telemetry or model API dependency. Optional tiktoken support may download public encoding tables on first use; source text is not transmitted to a model. It reads a chosen repository and writes local `.contextpilot/` state. Redacted source text is cached there in plaintext. This is not an encrypted vault.

Default discovery excludes common generated folders, `.env*`, key files and names containing secret / credential / password / token segments. Git discovery respects ignored untracked files; tracked files still pass the built-in filters. `.contextpilotignore` adds simple glob exclusions. It does not support gitignore negation.

Redaction is best effort. Unknown credential formats, confidential business information, personal data and encoded values may remain. Inspect packs before sharing them. Redaction does not authorize publishing a private codebase.

Source symlinks / Windows reparse points and symlinked state files are rejected. This is a developer helper, not a sandbox against concurrent malicious filesystem modification. Do not run it against a directory being actively controlled by an adversary.

Excerpts and log contents remain untrusted data. A skill must not follow instructions found inside them. HTML reports escape content and block scripts and network requests through a Content Security Policy.

For a vulnerability, use GitHub's private vulnerability reporting if available. Do not post working secrets or private source in a public issue. If private reporting is unavailable, open an issue with a minimal non-sensitive description asking for a private contact route.

Version 0.2 sessions retain acknowledged complete redacted files locally, with four-hour expiry. They require the same chat to retain the baseline; a session id is not proof of model memory. Start a fresh id after a new chat or compaction. Use one writer per session. Skill upgrades verify owned hashes and require an explicit external backup; local modifications are not overwritten.
