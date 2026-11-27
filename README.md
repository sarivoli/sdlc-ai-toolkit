# SDLC AI Toolkit

Agents, skills and templates that make GitHub Copilot in VS Code run your
team's SDLC on a Jira ticket. It reads the ticket, analyses the impact across
every repo, plans, waits for your approval, implements, runs the quality gate,
makes disciplined commits across repos, writes one consolidated summary,
opens cross-linked GitLab MRs and updates Jira. It is built for Python/Zope
teams.

## Install (2 minutes)

Open this repo in VS Code and ask Copilot Chat:

```
/install-sdlc-toolkit
```

or run it yourself:

```bash
python3 install.py --workspace ~/work          # Windows: py -3 install.py --workspace C:\work
```

Then follow the **ACTION REQUIRED** list it prints (sign in to Jira and
GitLab once, then reload VS Code). The list is also saved to
`~/.copilot/sdlc-toolkit/MANUAL_STEPS.md`.

## Use

In Copilot Chat pick **SDLC Orchestrator** and type a ticket key, e.g.
`PROJ-123`. Full guide: **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)**.

## Repository layout

| Path | What | Who edits |
|------|------|-----------|
| `config/toolkit.ini` | Team settings: Jira, GitLab, commit rules, quality commands, update frequency | Team lead |
| `templates/` | Formats for Jira comments, impact analysis, plan, commits, quality report, MR, summary, Teams text | Team |
| `agents/` | 6 custom agents (Orchestrator + specialists) | Maintainers |
| `skills/` | 10 skills (procedures + Zope standards and checklists) | Maintainers |
| `vendor/awesome-copilot/` | Reused community skills and agents (MIT, pinned) | `scripts/update_vendor.py` |
| `scripts/sdlc.py` | Deterministic helper CLI (config, templates, quality gate, commit checks, multi-repo collect and summary, hooks) | Maintainers |
| `install.py` | User-level installer, upgrade and uninstall | — |
| `tests/` | `python3 -m unittest discover -s tests` | — |

## Requirements

You need VS Code with GitHub Copilot Chat (agent mode), Python 3.8+ and Git.
You also need Jira Cloud and GitLab accounts. The installer itself uses only
the Python standard library.
