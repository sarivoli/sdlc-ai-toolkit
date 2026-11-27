# SDLC AI Toolkit

Agents, skills, templates and a helper CLI that make GitHub Copilot in VS Code
run your team's SDLC on a Jira ticket, across **many repositories at once**.

Give it a ticket key (e.g. `PROJ-123`). It reads the ticket, analyses the
impact across every repo, plans, **waits for your approval**, implements,
runs the quality gate, makes disciplined commits, writes one consolidated
summary, opens cross-linked GitLab MRs and updates Jira. It is built for
Python / Zope / SQLAlchemy backends with Angular frontends.

## Contents

- [Features](#features)
- [How the workflow runs](#how-the-workflow-runs)
- [Install](#install)
- [Use](#use)
- [Templates](#templates)
- [Configuration](#configuration)
- [Work journal and reports](#work-journal-and-reports)
- [Branch and commit conventions](#branch-and-commit-conventions)
- [Impact analysis and Orbit](#impact-analysis-and-orbit)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [Requirements](#requirements)
- [Development](#development)

## Features

- **Seven agents**: SDLC Orchestrator (start here), Ticket Analyst, Impact
  Analyst, Implementer, Quality Gate, Release Scribe and Work Journal.
- **Eleven skills**: procedures for each stage plus the team's Python/Zope
  standards and checklists.
- **Human checkpoints**: approval of the plan, confirmation before editing
  each repo, and confirmation before pushing, opening MRs or updating Jira.
  Nothing is ever merged or force-pushed.
- **Multi-repo aware**: one ticket can touch several repos; commits, quality
  results and MRs are collected into one consolidated summary and cross-linked.
- **Full-stack impact analysis**: whole-method scope (one changed line means
  the whole method is analysed), endpoints and screens traced from Angular and
  Python/SQLAlchemy code, and every XML configuration reference listed.
- **QA hand-off**: after developer validation the ticket gets impacted
  screens, endpoints, use cases to validate, regression areas and test data.
- **Orbit code graph**: a local GitLab Orbit knowledge graph, one per
  workspace folder, backs callers, tests and reference searches.
- **Automatic work journal**: every activity on a ticket (impact analysis,
  development, bugfix, ...) is logged with a brief note to one personal file
  shared by all VS Code workspaces. Ask the **SDLC Work Journal** agent for
  a daily, weekly, monthly or yearly report right in chat.
- **Editable templates** for every output (Jira comments, MR text, commits,
  reports, Teams update).
- **Deterministic helper CLI** (`scripts/sdlc.py`) for the parts that must be
  exact: commit rules, branch names, quality checks, commit collection.
- **Quality gate** driven by config: lint, format, types, security scan and
  tests, with missing tools reported as missing, never as passed.
- **Git hooks** (optional) that reject commits breaking the team rules.
- **No service to run**: Jira and GitLab connect through MCP servers using
  your own sign-in.

## How the workflow runs

| Stage | Agent | Output |
|-------|-------|--------|
| 1. Understand | Ticket Analyst | understanding summary (description, comments, links, acceptance criteria, open questions) |
| 2. Analyse | Impact Analyst | impact analysis across all repos |
| 3. Plan | Impact Analyst | implementation plan, then **stops for your approval** |
| 4. Implement | Implementer | test-first changes on the current branch, after per-repo confirmation |
| 5. Quality gate | Quality Gate | lint, format, type, security and test report |
| 6. Release | Release Scribe | atomic commits, consolidated summary, MRs, Jira updates |

You can also run any single stage on its own.

## Install

### One line, from the public URL (macOS, Linux, Windows)

Needs only Git and Python 3.8+. The script clones the repo to `~/.sdlc-ai-toolkit`
(re-running it updates) and runs the installer.

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.sh | bash
# pass installer options after "-s --"
curl -fsSL https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.sh | bash -s -- --target all --workspace ~/work
```

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.ps1 | iex
```

Or just tell your AI editor: *"Clone https://github.com/sarivoli/sdlc-ai-toolkit and
install it"* - [AGENTS.md](AGENTS.md) tells the agent what to run.

### Supported editors

By default (`--target auto`) the installer sets up GitHub Copilot plus every
editor it finds on the machine. Choose explicitly with `--target all` or a list.

| Target | Editor / CLI | Skills | Agents | MCP servers |
|---|---|---|---|---|
| `copilot` | VS Code + GitHub Copilot | `~/.copilot/skills` | `~/.copilot/agents` | VS Code `mcp.json`, `~/.copilot/mcp-config.json` |
| `claude` | Claude Code | `~/.claude/skills` | `~/.claude/agents` | `~/.claude.json` |
| `cursor` | Cursor | `~/.cursor/skills` | `~/.cursor/agents` | `~/.cursor/mcp.json` |
| `antigravity` | Google Antigravity | `~/.gemini/config/skills` | `~/.gemini/config/agents` | `~/.gemini/config/mcp_config.json` |
| `gemini` | Gemini CLI | `~/.gemini/skills` | installed as skills | `~/.gemini/settings.json` |
| `codex` | OpenAI Codex CLI | `~/.codex/skills` | installed as skills | `~/.codex/config.toml` |

Notes: skills use the open Agent Skills format, so they are copied as is; agents
are converted to each editor's format. Editors without custom agents get each
agent as a skill. Claude Code subagents cannot start other subagents, so the
orchestrator hands over step by step there. Non-Copilot paths follow each
editor's documentation and are best effort. Existing configs are merged and
backed up; `--uninstall` removes only what the toolkit added.

### From a clone

```bash
git clone https://github.com/sarivoli/sdlc-ai-toolkit && cd sdlc-ai-toolkit
python3 install.py --workspace ~/work          # Windows: py -3 install.py --workspace C:\work
```

Optionally pass your team values:

```bash
python3 install.py --set jira.site=https://<site>.atlassian.net \
  --set jira.project_keys=PROJ --set gitlab.group=<group> --workspace ~/work
```

The installer copies agents and skills, writes the MCP server config (Jira,
GitLab, Orbit), installs the Orbit CLI through npm when Node.js is available,
and prints an **ACTION REQUIRED** list (sign in to Jira and GitLab once, reload
the editor). That list is also saved to `~/.copilot/sdlc-toolkit/MANUAL_STEPS.md`.

Other installer options:

```bash
python3 install.py --target claude,cursor   # only these editors
python3 install.py --dry-run      # show what would change
python3 install.py --no-hooks     # skip git hook installation
python3 install.py --uninstall    # remove everything the toolkit installed
```

Re-run the installer (or the one-liner) to update. Full instructions:
**[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** (sections 2 to 4 cover prerequisites,
install and the manual steps).

## Use

In Copilot Chat pick **SDLC Orchestrator** and type a ticket key, for example
`PROJ-123`. Skills are also slash commands, such as `/jira-ticket-digest`
or `/impact-analysis`.

Helper CLI examples (installed at `~/.copilot/sdlc-toolkit/scripts/sdlc.py`):

```bash
python3 sdlc.py doctor                                   # check the installation
python3 sdlc.py repos                                    # repos in the workspace
python3 sdlc.py branch-name PROJ-123 --type bugfix --user kumar
python3 sdlc.py check-commit --message "PROJ-123: fix lookup"
python3 sdlc.py quality PROJ-123                         # run the quality gate
python3 sdlc.py summary PROJ-123                         # render summary, MR and Teams text
python3 sdlc.py orbit index                              # code graph for this workspace
python3 sdlc.py log PROJ-123 --activity bugfix --summary "Fixed lookup"   # work journal entry
python3 sdlc.py report --period month --by ticket       # monthly work report
```

## Templates

Every artefact the agents produce is shaped by a template in
[templates/](templates). Edit the wording or sections, re-run the installer,
and every agent follows the new format. Overrides can also live per repo or
per workspace in `.sdlc/templates/`.

| Template | Purpose |
|----------|---------|
| `ticket-understanding.md` | Understanding summary of the ticket |
| `impact-analysis.md` | Impact analysis: change trace, endpoints, XML references, risk |
| `implementation-plan.md` | Plan per repo; the approval gate |
| `commit-message.txt` | Commit message format |
| `quality-report.md` | Quality gate results |
| `mr-description.md` | GitLab merge request description |
| `jira-progress-comment.md` | Short progress comments on the ticket |
| `jira-impact-comment.md` | QA and stakeholder hand-off: screens, endpoints, use cases |
| `consolidated-summary.md` | One summary across all repos and MRs |
| `teams-update.md` | Text to paste in Teams or Outlook |

Placeholder syntax and precedence rules: [templates/README.md](templates/README.md).

## Configuration

Team settings live in [config/toolkit.ini](config/toolkit.ini). Personal
overrides are saved by the installer to
`~/.copilot/sdlc-toolkit/toolkit.local.ini`.

| Section | Controls |
|---------|----------|
| `[team]` | Team name and general settings |
| `[jira]` | Site, project keys, update frequency, workflow transitions |
| `[gitlab]` | Group, default target branch |
| `[mcp]` | MCP server endpoints |
| `[journal]` | Work journal on/off and file location |
| `[orbit]` | Orbit CLI install, indexing, hosted MCP, telemetry |
| `[git]` | Branch convention, commit rules, protected branches |
| `[quality]` | Lint, format, type, security and test commands |
| `[workspace]` | Workspace folder, repo discovery depth, work dir |
| `[safety]` | Steps that need confirmation |
| `[notify]` | Teams / Outlook summary |

## Work journal and reports

Agents record each finished activity on a ticket with `sdlc.py log`. Entries
go to `~/.copilot/sdlc-journal/worklog.jsonl`: one personal file used by
every workspace, kept on upgrade and uninstall (change the location with
`[journal] path`, e.g. a OneDrive folder). In Copilot Chat pick **SDLC Work
Journal** and ask, for example:

- "weekly report" / "what did I do last month"
- "yearly report by ticket"
- "when did I work on PROJ-123"
- "log PROJ-123: investigated slow search"

Periods: `today`, `yesterday`, `week`, `last-week`, `month`, `last-month`,
`year`, `last-year`, `all`, or `--from/--to` dates. Details: section 16 of
the [user manual](docs/USER_MANUAL.md).

## Branch and commit conventions

Branches follow `<type>/<username>/<ticket_id>` with types `feature`,
`bugfix`, `spike` (`spike/<poc_name>/<ticket_id>`), `refactor` and `chore`,
for example `feature/kumar/JIVA70-1919`. By default the agents use each
repo's **current branch** and ask before editing files in each repo. Commit
messages carry the ticket key and are validated by `sdlc.py check-commit` and
the optional git hooks. Protected branches are never committed to.

## Impact analysis and Orbit

Impact analysis uses the [GitLab Orbit CLI](https://docs.gitlab.com/orbit/cli/)
for callers, imports, tests and references. Each workspace folder (which may
hold several repos) has its **own** graph in `<folder>/.sdlc/orbit`, so
different products or versions never mix. Details: section 15 of the
[user manual](docs/USER_MANUAL.md) and the checklist
[fullstack-trace-checklist.md](skills/impact-analysis/references/fullstack-trace-checklist.md).

## Repository layout

| Path | What | Who edits |
|------|------|-----------|
| `config/toolkit.ini` | Team settings | Team lead |
| `templates/` | Output formats | Team |
| `agents/` | 7 custom agents | Maintainers |
| `skills/` | 11 skills (procedures, Zope standards, checklists) | Maintainers |
| `vendor/awesome-copilot/` | Reused community skills and agents (MIT, pinned) | `scripts/update_vendor.py` |
| `scripts/sdlc.py` | Deterministic helper CLI | Maintainers |
| `install.py` | User-level installer, upgrade and uninstall | Maintainers |
| `docs/` | User manual and maintainer notes | Maintainers |
| `tests/` | Unit tests | Maintainers |
| `.github/` | Copilot instructions and the install prompt | Maintainers |
| `AGENTS.md` | Instructions for AI agents working in this repo | Maintainers |

## Documentation

- [docs/USER_MANUAL.md](docs/USER_MANUAL.md): install, first ticket, config
  reference, troubleshooting, safety rules.
- [docs/TOOLKIT_NOTES.md](docs/TOOLKIT_NOTES.md): architecture, connectivity
  design, Orbit integration and the fine-tuning backlog.
- [templates/README.md](templates/README.md): template syntax and precedence.
- [AGENTS.md](AGENTS.md): how AI agents should install and change this repo.

## Requirements

- An AI editor: VS Code with GitHub Copilot Chat (agent mode), Claude Code, Cursor, Antigravity, Gemini CLI or Codex CLI
- Python 3.8+ and Git
- Jira Cloud and GitLab accounts
- Node.js, optional, to auto-install the Orbit CLI

The installer itself uses only the Python standard library. For Copilot
Business or Enterprise, your org admin must allow MCP servers in Copilot.

## Development

```bash
python3 -m unittest discover -s tests
```

Keep the `@@SDLC@@` and `@@TOOLKIT_HOME@@` placeholders in agents and skills;
the installer replaces them. After changes, re-run `python3 install.py`.
