# development-process

Machine-level development workflow for the repositories under `C:\Dev`.

**agent-review**: Claude Opus (high effort) develops a mission; Codex with
GPT-6.2 Astra (`gpt-6.2-astra`, high effort) independently reviews each
checkpoint; a small local controller runs both, verifies every result and
keeps the whole exchange on a GitHub draft PR. The owner steps in only for a
human decision, a precise blocker, or the final review.

- Operating guide: [agent_review/README.md](agent_review/README.md)
- Behavioral specification: [docs/GITHUB-AGENT-REVIEW-PROTOCOL.md](docs/GITHUB-AGENT-REVIEW-PROTOCOL.md)
- Setup mission, owner addenda and acceptance: [planning/](planning/)
- Onboarded repositories: [agent_review/projects/](agent_review/projects/)

Install (from a reviewed checkout of this repository):

```powershell
python agent_review/agent_review.py install --dest C:/Dev/agent-review
python C:/Dev/agent-review/agent_review.py preflight --project development-process
```
