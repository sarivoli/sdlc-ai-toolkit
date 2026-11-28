# SDLC AI Toolkit — User Manual

Version 1.0 · For Python / Zope teams using Jira Cloud, GitLab, VS Code and GitHub Copilot

---

## Contents

1. [What you get](#1-what-you-get)
2. [Before you install](#2-before-you-install)
3. [Install](#3-install)
4. [Manual steps after installing](#4-manual-steps-after-installing)
5. [Your first ticket, end to end](#5-your-first-ticket-end-to-end)
6. [Using one stage at a time](#6-using-one-stage-at-a-time)
7. [What is written where](#7-what-is-written-where)
8. [Commit discipline and git hooks](#8-commit-discipline-and-git-hooks)
9. [Customising templates](#9-customising-templates)
10. [Team configuration reference](#10-team-configuration-reference)
11. [For team leads: rolling out and maintaining](#11-for-team-leads-rolling-out-and-maintaining)
12. [Troubleshooting](#12-troubleshooting)
13. [Upgrade and uninstall](#13-upgrade-and-uninstall)
    (Orbit code graph: see [section 15](#15-orbit-code-graph-for-impact-analysis))
14. [Safety rules the agents follow](#14-safety-rules-the-agents-follow)

---

## 1. What you get

The toolkit turns Copilot Chat in VS Code into a disciplined SDLC assistant.
You give it a Jira ticket key; it walks the ticket from understanding to
merge requests, stopping for your approval at the points that matter.

```
 Jira ticket ─► Understand ─► Impact + Plan ─► [you approve] ─► Implement ─► Quality gate
                                                                                 │
   Jira comment + transition ◄─ MRs (cross-linked) ◄─ Consolidated summary ◄─ Atomic commits (all repos)
```

### Agents (pick them in the Copilot Chat agent dropdown)

| Agent | Role | Changes code? |
|-------|------|---------------|
| **SDLC Orchestrator** | Start here. Runs every stage in order, resumes unfinished tickets, stops at checkpoints | via the specialists |
| SDLC Ticket Analyst | Reads ticket, all comments, links → understanding summary + open questions | No |
| SDLC Impact Analyst | Maps the ticket onto all repos (ZCML, adapters, templates, ZODB, catalog, callers) → impact analysis + plan | No |
| SDLC Implementer | Implements the **approved** plan, test first | Yes, no commits |
| SDLC Quality Gate | Lint, format, type, security, tests + standards review → quality report | Only fixes |
| SDLC Release Scribe | Atomic commits, consolidated summary, push, MRs, Jira comment/transition | Commits (after gate) |

**Reused community agents** (from [github/awesome-copilot](https://github.com/github/awesome-copilot), installed alongside):
`Debug Mode Instructions` (root-causing bugs), `SE: Security` (deep security
review), `Critical thinking mode instructions` (challenge a plan). The SDLC
agents call them when useful; you can also pick them yourself.

### Skills (type `/` in Copilot Chat)

| Skill | What it does |
|-------|--------------|
| `/jira-ticket-digest PROJ-123` | Understanding summary of a ticket |
| `/impact-analysis PROJ-123` | Impact analysis across repos |
| `/implementation-plan PROJ-123` | Reviewable plan + approval gate |
| `/quality-gate PROJ-123` | Run the quality gate |
| `/commit-discipline PROJ-123` | Commit the work properly |
| `/multi-repo-summary PROJ-123` | Collect commits across repos → summary, MR texts, Teams text |
| `/gitlab-mr-publisher PROJ-123` | Push + open/update cross-linked MRs |
| `/jira-progress-update PROJ-123 <stage>` | Post a templated progress comment |
| `/zope-python-standards` | Team coding standards & review checklist |
| Reused: `/git-commit`, `/security-review`, `/pytest-coverage`, `/refactor`, `/acquire-codebase-knowledge` | Community skills the toolkit builds on |

`sdlc-conventions` is loaded automatically by the other skills (shared rules).

### Connections

- **Jira Cloud** through the official **Atlassian Rovo MCP server** (OAuth, runs with *your* Jira permissions).
- **GitLab** through the official **GitLab MCP server** (OAuth, your permissions).
- **Microsoft 365**: the toolkit produces a ready-to-paste Teams/Outlook update (`teams.md`). There is no direct M365 posting in v1.

---

## 2. Before you install

| Need | Check |
|------|-------|
| VS Code, recent version, with **GitHub Copilot** + **Copilot Chat** signed in | Copilot Chat shows an *Agent* dropdown |
| Python 3.8+ | `python3 --version` (Windows: `py -3 --version`) |
| Git | `git --version` |
| Your repos cloned under one folder (e.g. `~/work`) | The folder where your buildout / checkouts live |
| A Jira Cloud and GitLab account | Browser sign-in works |
| **Copilot Business/Enterprise only:** org policy allows *MCP servers in Copilot* | Ask your GitHub org admin if Jira/GitLab tools stay greyed out |

Optional quality tools: `pip install ruff bandit mypy` (or whatever your
team configured in `[quality]`).

---

## 3. Install

**Quickest (no clone, any OS):** needs Git and Python 3.8+.

```bash
curl -fsSL https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.sh | bash          # macOS / Linux / WSL
irm https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.ps1 | iex                # Windows PowerShell
```

It clones to `~/.sdlc-ai-toolkit` and runs the installer; run it again to update.
Add installer options with `bash -s -- --target all --workspace ~/work`.

**Which editors?** `--target auto` (default) installs for GitHub Copilot and every
editor found on the machine (Claude Code, Cursor, Antigravity, Gemini CLI, Codex CLI).
Use `--target all` or a list such as `--target copilot,claude`. Editors without custom
agents (Gemini CLI, Codex) get each agent as a skill. In Claude Code, subagents cannot
start other subagents, so the orchestrator works step by step. After installing, restart
the editor and sign in to the Atlassian and GitLab MCP servers in that editor.
`--uninstall` removes every target.

**From a clone** (your team may keep the repo in GitLab), open it in your editor,
then use **one** of these:

### Option A — ask Copilot (recommended)

In Copilot Chat (Agent mode) type:

```
/install-sdlc-toolkit
```

or just *"install this toolkit for me"*. Copilot reads the repo's
instructions, asks for anything missing (Jira site, project keys, GitLab
group, your repos folder), runs the installer and shows you the manual steps.

### Option B — terminal

```bash
# macOS / Linux
python3 install.py --workspace ~/work

# Windows (PowerShell)
py -3 install.py --workspace C:\work
```

Add personal values if your team lead hasn't set them in the team config:

```bash
python3 install.py --workspace ~/work \
  --set jira.site=https://acme.atlassian.net \
  --set jira.project_keys=PROJ,CORE \
  --set gitlab.group=acme
```

### Option C — VS Code task

*Terminal → Run Task… → SDLC toolkit: install / upgrade*.

### What the installer does

| Where | What |
|-------|------|
| `~/.copilot/agents/` | the 6 SDLC agents + 3 reused agents |
| `~/.copilot/skills/` | 10 toolkit skills + 5 reused skills |
| `~/.copilot/sdlc-toolkit/` | `toolkit.ini`, `toolkit.local.ini` (your overrides), `templates/`, `scripts/sdlc.py`, `MANUAL_STEPS.md`, this manual |
| `~/.copilot/mcp-config.json` | adds `atlassian` and `gitlab` MCP servers (merged; a timestamped backup is kept) |
| each repo under your workspace | `commit-msg` and `pre-push` hooks; `.sdlc/` added to `.git/info/exclude` |

Everything is user-level, so it works in every workspace you open. It
never overwrites a skill, agent, MCP server or git hook you already had
— it keeps yours and tells you. Re-running is safe (that's also how you
upgrade). Use `--dry-run` to preview.

---

## 4. Manual steps after installing

### Post-install checklist (do these three first)

At the end the installer checks three things and prints them as a
**POST-INSTALL CHECKLIST** (also at the top of
`~/.copilot/sdlc-toolkit/MANUAL_STEPS.md`). Each item is `[x]` done,
`[ ]` to do, `[~]` in progress or `[?]` not verifiable automatically, and
every open item shows the exact command or steps.

| # | Item | How it is checked |
|---|------|-------------------|
| 1 | **Orbit code index - MANDATORY** (saves tokens) | Orbit CLI on PATH, and every repo of the workspace folder in `<folder>/.sdlc/orbit` (`orbit workspace list`). Fix: `npm install -g @gitlab/orbit`, then `sdlc orbit index --folder <folder>` |
| 2 | **Git authentication** | `git ls-remote` against one remote per host of your workspace repos, with prompts disabled (`GIT_TERMINAL_PROMPT=0`, SSH `BatchMode`, Credential Manager non-interactive), 15 s timeout. No repos yet: `ssh -T git@<gitlab host>` |
| 3 | **Jira authentication** | The agents use the `atlassian` MCP server, whose OAuth sign-in lives inside your editor and cannot be read from outside - so this shows `[?]` until you confirm it by asking the agent to call `atlassianUserInfo`. If `JIRA_API_TOKEN` + `JIRA_EMAIL` are set, they are verified with `GET /rest/api/3/myself` (8 s timeout) |

The checks never prompt, never print tokens (credentials in remote URLs are
masked) and never block the install. Re-check any time:

```bash
python3 ~/.copilot/sdlc-toolkit/scripts/sdlc.py checklist            # --offline skips git/Jira network checks
```

`python install.py --no-auth-checks` skips the network checks during install.

**Why the Orbit index is mandatory:** every ticket workflow (ticket digest,
impact analysis, plan, implement, quality gate, commits, summary, MRs, Jira
updates) starts with `sdlc preflight`. If Orbit is not installed or the
workspace folder is not indexed, the agent **stops** and tells you to install
Orbit or run the index first, with the exact command. It continues without
Orbit only if you explicitly say *proceed without Orbit*.

### Other manual steps

The installer also prints an **ACTION REQUIRED** list (same file). The usual items:

1. **Reload VS Code** — *Command Palette → Developer: Reload Window*.
2. **Sign in to Jira and GitLab (once).** *Command Palette → MCP: List Servers →
   `atlassian` → Start Server* → approve in the browser. Repeat for `gitlab`.
   Click **Trust** if VS Code asks.
3. **Team values** — if the Jira site / GitLab group are still placeholders,
   re-run with `--set` (see above) or ask your lead to fix the team config.
4. **Quality tools** — install the ones listed as missing.
5. **Org policy** (Copilot Business/Enterprise) — MCP must be allowed.
6. **Existing git hooks / husky / pre-commit** — if you already use hooks,
   the installer leaves them alone and tells you the one line to add (see §8).

Check status anytime:

```bash
python3 ~/.copilot/sdlc-toolkit/scripts/sdlc.py doctor
```

**How to know it worked:** In Copilot Chat, the agent dropdown lists
**SDLC Orchestrator**; typing `/` lists `jira-ticket-digest`; asking the
Ticket Analyst *"read PROJ-1"* returns the real ticket.

---

## 5. Your first ticket, end to end

1. Open your workspace in VS Code (the folder with your repos, or a
   multi-root workspace).
2. Copilot Chat → agent dropdown → **SDLC Orchestrator**.
3. Type the ticket key, optionally with notes:

   ```
   PROJ-123
   ```

What happens:

| # | Stage | You see | You do |
|---|-------|---------|--------|
| 1 | **Understand** | Understanding summary: problem, acceptance criteria, what the comments decided, open questions, confidence | If confidence is low, let it post the questions to Jira and stop. Otherwise continue |
| 2 | **Impact & plan** | Impact analysis (files with `repo/path:line`, Zope touch-points, callers, data/migration, risk) and a 2-minute plan: steps, branches, planned commits | **Checkpoint 1:** reply `approve`, or say what to change. Optional: *Challenge this plan* |
| 3 | **Implement** | Code changes, test first, per the plan | Watch / steer. It stops if it needs something outside the plan |
| 4 | **Quality gate** | `quality.md`: each check per repo — pass / fail / skipped / missing | Install missing tools if asked |
| 5 | **Review** | Changed files per repo | **Checkpoint 2:** review the diffs in VS Code (Source Control view), confirm |
| 6 | **Commit** | Atomic commits per repo, each validated against team rules; then a list of all commits across repos | — |
| 7 | **Publish** | Consolidated summary, then *"Push 3 branches and open 3 MRs?"* | Confirm |
| 8 | **Jira** | The exact summary comment + transition | Confirm |
| 9 | **Done** | MR links table, Jira link, Teams text to paste | Paste `teams.md` in your team channel if you like |

Progress comments on the ticket are posted according to the team's
`progress_updates` setting (every stage / milestones / off) — always after
your confirmation.

### Resuming

Everything is saved in `<workspace>/.sdlc/PROJ-123/`. Close VS Code, come
back tomorrow, pick SDLC Orchestrator and type `PROJ-123` again — it
detects what is done and continues from there. A teammate can continue
your ticket the same way if you share the folder.

### Good prompts

- `PROJ-123 — the fix must also work for the legacy Zope 2 skin`
- `PROJ-123 only do understanding and impact, I'll implement myself`
- `PROJ-123 resume`
- `PROJ-123 regenerate the MR descriptions, the plan changed`

---

## 6. Using one stage at a time

You don't have to run the full flow.

- **Pick a specialist agent** (e.g. *SDLC Impact Analyst*) and give the ticket key.
  Each agent has handoff buttons under its answer to move to the next stage.
- **Use a skill in any agent**, including the default Copilot agent:
  `/jira-ticket-digest PROJ-123`, `/quality-gate PROJ-123`,
  `/multi-repo-summary PROJ-123`.
- **Helper CLI in a terminal** (deterministic, no AI):

  ```bash
  alias sdlc='python3 ~/.copilot/sdlc-toolkit/scripts/sdlc.py'   # Windows: doskey / PowerShell function
  sdlc repos                       # repos, branches, dirty state
  sdlc branch-name JIVA70-1929 --type bugfix          # bugfix/<you>/JIVA70-1929
  sdlc check-commit --message "fix(catalog): PROJ-123 reindex after rename"
  sdlc quality PROJ-123            # run the gate
  sdlc collect PROJ-123            # all commits for the ticket, all repos
  sdlc summary PROJ-123            # render summary / MR / Teams texts
  sdlc template mr-description.md  # show the template in effect
  sdlc config                      # effective settings
  sdlc doctor                      # installation check
  sdlc checklist                   # Orbit index / git auth / Jira auth status
  sdlc preflight                   # Orbit gate run before ticket work (exit 3 = stop)
  ```

---

## 7. What is written where

| Artefact | Local file (`.sdlc/<KEY>/`) | Goes to | Template |
|----------|-----------------------------|---------|----------|
| Understanding summary | `understanding.md` | Jira comment (optional) | `ticket-understanding.md` |
| Impact analysis | `impact.md` | MR "Impact & risk" + summary | `impact-analysis.md` |
| Plan | `plan.md`, `plan.approved` | — (approval record) | `implementation-plan.md` |
| Quality report | `quality.md`, `quality.json` | MR "Quality gate" | `quality-report.md` |
| Commit messages | — | git | `commit-message.txt` |
| Commits across repos | `commits.json` | summary + MRs | (git data) |
| Narrative fields | `narrative.json` | summary + MRs | — |
| MR descriptions | `mr-<repo>.md` | each GitLab MR | `mr-description.md` |
| MR links | `mrs.json` | summary table, sibling links | — |
| Consolidated summary | `summary.md` | Jira comment | `consolidated-summary.md` |
| Progress pings | — | Jira comments | `jira-progress-comment.md` |
| Teams / Outlook update | `teams.md` | you paste it | `teams-update.md` |

`.sdlc/` is excluded from git in every repo by the installer.

Numbers in summaries and MRs (commits, files, +/- lines, branches) are
computed by `sdlc.py` from git, never typed by the AI.

---

## 8. Commit discipline and git hooks

**Format** (default; your team can change it in `[git] commit_regex`):

```
<type>(<scope>): <TICKET-KEY> <summary in imperative mood>

<body: WHY the change was needed>

Refs: <TICKET-KEY>
```

Example: `fix(catalog): PROJ-123 reindex objects after title change`

Rules enforced by the `commit-msg` hook (for everyone, with or without AI):
allowed types, ticket key from your Jira projects, subject ≤ 72 chars, no
trailing period, blank line after the subject, a body for `feat`/`fix`.
Merge, revert, `fixup!` and `squash!` commits are exempt.

The `pre-push` hook refuses pushes to protected branches (`main`,
`master`, `develop`, `release/*` by default).

**Already have hooks?** The installer keeps them. Add one line to your
existing `commit-msg` hook (or your husky / pre-commit config):

```sh
python3 ~/.copilot/sdlc-toolkit/scripts/sdlc.py check-commit --message-file "$1" || exit 1
```

For pre-commit framework users, a local hook:

```yaml
- repo: local
  hooks:
    - id: sdlc-commit-msg
      name: SDLC commit message
      entry: python3 ~/.copilot/sdlc-toolkit/scripts/sdlc.py check-commit --message-file
      language: system
      stages: [commit-msg]
```

New repo cloned later? Run `sdlc install-hooks` (or re-run the installer).

---

## 9. Customising templates

All output formats live in `templates/` in the toolkit repo. Edit the
Markdown, keep the placeholders you need, re-run the installer.

| Syntax | Meaning |
|--------|---------|
| `{{ticket_key}}` | a value |
| `{{#each repos}} … {{/each}}` | repeat per item (`{{name}}`, `{{branch}}`, `{{commits}}` …) |
| `{{#if follow_ups}} … {{/if}}` | only if non-empty |
| `<!-- guidance: … -->` | instruction for the AI; removed from the output |

**Override per project or workspace** without changing the team default:
put a file with the same name in `<repo>/.sdlc/templates/` (commit it in
that repo if it should apply to everyone working on it) or
`<workspace>/.sdlc/templates/`. Precedence: repo → workspace → team.
Check which one is used with `sdlc template <file> --repo <path>`.

Fields available to the summary / MR templates from git: `ticket_key`,
`ticket_url`, `date`, `developer`, `repo_count`, `commit_count`,
`files_total`, `insertions_total`, `deletions_total`, and per repo: `name`,
`branch`, `target`, `web_url`, `commit_count`, `files_changed`,
`insertions`, `deletions`, `commits[]` (`short_sha`, `subject`, `author`,
`date`), `mr_link`, `mr_url`, `sibling_mrs[]` (`repo`, `url`). Everything
else comes from `narrative.json`, which the AI writes from the earlier
stages — add your own fields there and use them in your templates.

**Coding standards** are in `skills/zope-python-standards/references/standards.md`;
the **Zope impact checklist** is in `skills/impact-analysis/references/zope-impact-checklist.md`.
Edit them like any document.

---

## 10. Team configuration reference

File: `config/toolkit.ini` in the toolkit repo (team defaults). Personal
overrides: `~/.copilot/sdlc-toolkit/toolkit.local.ini` (written by
`--set`). Never store tokens in either file.

| Section | Key | Default | Meaning |
|---------|-----|---------|---------|
| jira | `site` | — | `https://<site>.atlassian.net` |
| jira | `project_keys` | `PROJ` | allowed project keys (commits are checked) |
| jira | `progress_updates` | `every_stage` | `every_stage` / `milestones` / `off` |
| jira | `transition_on_start` / `transition_on_mr` | `In Progress` / `In Review` | workflow transition names; blank = skip |
| jira | `label` | `ai-assisted` | label added to the ticket |
| gitlab | `url`, `group` | — | for links |
| gitlab | `default_target_branch` | `main` | falls back to `origin/HEAD`, master, develop |
| gitlab | `mr_labels`, `mr_draft`, `squash_on_merge`, `remove_source_branch`, `default_reviewers` | | MR options |
| mcp | `atlassian_url` | `https://mcp.atlassian.com/v1/mcp/authv2` | Rovo MCP endpoint |
| mcp | `gitlab_url` | `https://gitlab.com/api/v4/mcp` | change host for self-managed |
| mcp | `write_vscode_profile_mcp` | `no` | also write VS Code profile `mcp.json` |
| git | `branch_pattern` | `{type}/{user}/{key}` | branch naming (`feature/kumar/JIVA70-1919`; spike uses the POC name) |
| git | `branch_types` | `feature, bugfix, spike, refactor, chore` | allowed branch types |
| git | `branch_mode` | `current` | `current` = stay on the repo's branch; `new` = create the convention branch |
| git | `commit_regex`, `max_subject_length`, `commit_types`, `require_body_for` | | commit rules |
| git | `protected_branches` | `main, master, develop, release/*` | never committed/pushed to |
| quality | `lint`, `format_check`, `typecheck`, `security`, `tests` | ruff / ruff format / – / bandit / auto | `{files}` = changed .py files; `tests` blank = auto (`bin/test`, `zope-testrunner`, `pytest`) |
| quality | `required` | `lint, tests` | checks that must pass |
| quality | `zope_flavor`, `python_version` | `zope5`, `3.11` | used by standards & impact skills |
| workspace | `root`, `work_dir`, `repo_search_depth` | `~/work`, `.sdlc`, `3` | where repos and notes are |
| safety | `confirm_before` | `push, create_mr, jira_comment, jira_transition` | always ask first |
| notify | `teams_summary` | `yes` | produce `teams.md` |

---

## 11. For team leads: rolling out and maintaining

**Set up once (30 min)**

1. Push this repo to your GitLab (e.g. `eng/sdlc-ai-toolkit`).
2. Edit `config/toolkit.ini` (Jira site, keys, transitions, GitLab group, quality commands, Zope flavour).
3. Review `templates/` and `standards.md` with the team; adjust wording.
4. Run `python3 -m unittest discover -s tests` and commit through an MR.

**Roll out in phases**

| Phase | Weeks | Who | Use |
|-------|-------|-----|-----|
| 1. Read-only | 2–3 | 2–3 volunteers | Ticket Analyst + Impact Analyst only. Measure: are summaries/impact accurate? |
| 2. Implement with gates | 2–4 | pilot group | Full Orchestrator flow, Jira `progress_updates = milestones` |
| 3. Team-wide | — | everyone | Hooks everywhere; CI runs the same checks as the quality gate |

**Back it up in CI.** Add the same lint/test/security commands to
`.gitlab-ci.yml`, and a commit-message check job, so the standards hold
even for people who don't use the agents.

**Measure**: ticket → MR time, MR review rounds, plan rejections (best
signal for improving skills), escaped defects, % commits passing format.

**Change the toolkit like code**: every change to agents, skills,
templates or config goes through an MR; bump `VERSION`; developers run
`git pull && python3 install.py`.

**Refresh reused community items**: `python3 scripts/update_vendor.py --ref main`,
review the diff, MR.

**Fallback GitLab connector.** If the official GitLab MCP server isn't
available on your plan/instance, use the community server
`@zereight/mcp-gitlab` with a personal access token: replace the `gitlab`
entry in `~/.copilot/mcp-config.json` with a stdio entry
(`"command": "npx", "args": ["-y", "@zereight/mcp-gitlab"]`, env
`GITLAB_PERSONAL_ACCESS_TOKEN`, `GITLAB_API_URL=https://gitlab.com/api/v4`).
Keep the name `gitlab` so the agents' `gitlab/*` tools still match. Store the
token via VS Code `inputs` or your OS keychain, never in the repo.

---

## 12. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Agents don't appear in the dropdown | Reload Window. Check files exist in `~/.copilot/agents/`. Update VS Code + Copilot Chat. Open *Chat: Open Customizations* to see what is loaded |
| Skills don't appear after `/` | Same as above for `~/.copilot/skills/`. On older VS Code versions agent skills may need enabling in settings (search "skills") |
| Jira/GitLab tools missing or greyed out | *MCP: List Servers* → start and sign in. Org policy may block MCP (Business/Enterprise). If servers aren't listed, *MCP: Open User Configuration* and add them under `"servers"` (same URLs as in `~/.copilot/mcp-config.json`), or re-install with `--set mcp.write_vscode_profile_mcp=yes` |
| Atlassian sign-in fails / "site not allowed" | Your Atlassian admin may need to allow the Rovo MCP server for your site |
| "Too many requests" from Jira | Atlassian rate-limits MCP calls per site per hour; wait, or ask your admin about your plan's limit |
| Commit rejected by hook | Read the message — it shows the expected format and an example. Ask the Release Scribe to rewrite it. Don't use `--no-verify` |
| Quality gate shows `missing` | Install the tool (`pip install ruff bandit`) or change the command in `[quality]` |
| Tests auto-detect picks the wrong runner | Set `[quality] tests = bin/test -s my.package` (or your command) |
| `sdlc collect` finds no commits | Commits must contain the ticket key; the branch must be ahead of the target (`git fetch` first) |
| Wrong repos found | Set `[workspace] root` (`--workspace`) or pass `--repo <path>` |
| Windows: `python3` not found | Use `py -3`; the installer already writes the right launcher into skills |
| Agent tries to do too much | Say "stop"; it must stay within `plan.md`. Report it so the skill can be tightened |

Run `sdlc doctor` and share its output when asking for help.

---

## 13. Upgrade and uninstall

```bash
cd sdlc-ai-toolkit
git pull
python3 install.py          # upgrade in place; your toolkit.local.ini is kept
python3 install.py --uninstall
```

Uninstall removes only what the installer added (agents, skills, MCP
entries, toolkit hooks, `~/.copilot/sdlc-toolkit/`), keeps your
`toolkit.local.ini`, and leaves your own agents, skills, servers and
hooks untouched.

---

## 14. Safety rules the agents follow

- Explicit "yes" before: push, creating MRs, Jira comments, Jira transitions.
- Never merge or approve MRs, force-push, rewrite pushed history, delete
  branches, or commit to protected branches.
- Never implement outside the approved plan; propose a plan change instead.
- Never weaken checks (`noqa`, `nosec`, skipping tests) without your OK.
- Skipped checks are reported as skipped, never as passed.
- Jira and GitLab are accessed with **your** permissions only.
- No secrets or customer data in commits, comments or MRs.

You remain the author and the reviewer of every change.

---

## 15. Orbit code graph for impact analysis

Impact analysis uses the **GitLab Orbit CLI** (https://docs.gitlab.com/orbit/cli/):
a local, offline code knowledge graph (definitions, callers, imports, tests;
includes unpushed commits). No account or running service needed.

**Install:** the installer runs `npm install -g @gitlab/orbit` (needs Node.js),
disables telemetry (`[orbit] telemetry = no`) and starts indexing the workspace
folder. If npm is missing it prints the manual step.

**Local `gitlab-orbit` MCP server (default).** The Orbit CLI (1.9.x) has no MCP
server of its own, so the toolkit ships one: `scripts/orbit_mcp.py`, a small
stdio MCP server that wraps the local CLI. The installer registers it as
`gitlab-orbit` in every editor (Copilot, Claude Code, Cursor, Antigravity,
Gemini CLI, Codex). It runs on your machine, serves the graph of the folder
your editor has open, starts indexing that folder the first time it sees it,
and **never calls GitLab**: no GitLab sign-in is needed for Orbit.

| Tool | Runs |
|---|---|
| `orbit_status` | `orbit workspace list`: indexed repos, branch, commit, graph location |
| `orbit_index` | `orbit workspace index <folder or repo> [--async]` |
| `orbit_grep` | `orbit grep` in every repo of the folder (or one `repo`) |
| `orbit_context` | `orbit context` for files, line ranges, names, `Definition:<id>` |
| `orbit_sql` / `orbit_schema` | read-only DuckDB queries on the local graph |

GitLab lookups (`mr:`, `issue:`, `pipeline:`, GitLab URLs ...) are refused; use
the `gitlab` MCP server for merge requests, issues and pipelines.

What the installer writes (VS Code `mcp.json`; the other editors get the same
command in their own format). There is no workspace path and no `${...}`
variable: the file is shared by all your workspaces, and Copilot refuses
unresolved variables ("Not supported by Copilot: Unresolved configuration ...
variables").

```json
"gitlab-orbit": {
  "type": "stdio",
  "command": "/usr/bin/python3",
  "args": ["/home/you/.copilot/sdlc-toolkit/scripts/orbit_mcp.py"]
}
```

The server finds the workspace folder itself, first match wins:
`--workspace <folder>` (if you add it by hand), the editor's open folder (the
MCP *roots* the editor reports; VS Code does), `$WORKSPACE_FOLDER` / `$PWD`,
else the folder the editor started it in. It never indexes your home directory
or `/` on its own: `orbit_status` then tells you how to index the right folder.

An existing `gitlab-orbit` entry that points at the hosted endpoint
(`https://gitlab.com/api/v4/orbit/mcp`), or an earlier local entry with
`--workspace ${workspaceFolder}`, is replaced when you re-run the installer;
your other servers are left alone.

**Check it:** VS Code > Command Palette > `MCP: List Servers` > `gitlab-orbit`
> Start Server (or Show Output), then ask Copilot to call `orbit_status`.

`[orbit] mcp_mode` chooses the server: `local` (default), `remote` (the hosted
GitLab endpoint `mcp_url`, which needs Orbit enabled on your GitLab group and
an OAuth sign-in) or `off`. `[orbit] enabled = no` turns Orbit off entirely.

**One graph per workspace folder.** Every `orbit` call made through
`sdlc.py orbit ...` sets `ORBIT_DATA_DIR=<workspace folder>/.sdlc/orbit`, so
different products or versions never share a graph. A workspace folder may
hold many repos; `workspace index` indexes all of them. The folder is taken
from `--folder`, `SDLC_WORKSPACE_ROOT`, `workspace.roots`/`workspace.root`
containing the current directory, else the current directory.

| Command | Purpose |
|---|---|
| `sdlc.py orbit index [-- --async]` | (re)index all repos of this workspace folder (incremental) |
| `sdlc.py orbit list` | indexed repos, branch, commit, status |
| `sdlc.py orbit grep --repo R -- NAME` | matches with enclosing definitions |
| `sdlc.py orbit context --repo R -- ARGS` | source, callers, tests |
| `sdlc.py orbit status` | same as `list`: state of the local graph |

New workspace folder? Opening it in the editor is enough: the local
`gitlab-orbit` server indexes it on first start. To index another folder by
hand, run `sdlc.py orbit index` there, or `sdlc.py orbit index --folder <path>`
(agents also do this before impact analysis). `sdlc.py doctor` reports whether the CLI is found
and whether the folder is indexed; `sdlc.py preflight` is the gate the agents run before any
ticket work (exit 3 = Orbit missing or folder not indexed: they stop and ask you to index first).
`orbit setup` does not support VS Code Copilot and writes one shared graph
(`~/.gitlab/orbit`), so the toolkit wires Orbit through its own MCP server and
the skills/agents instead.

---

## 16. Work journal and reports

Every time an agent finishes an activity on a ticket (understanding, impact
analysis, planning, development, bugfix, testing, quality gate, commit, MR,
Jira update ...) it appends one brief entry to your **personal work journal**:
`~/.copilot/sdlc-journal/worklog.jsonl`. The file is outside any workspace, so
all your VS Code workspaces write to the same list. It is kept on upgrade and
uninstall. Set `[journal] path` to put it in a synced folder (OneDrive,
Dropbox) or `[journal] enabled = no` to turn it off.

Each entry holds: timestamp, ticket key, ticket title (when known), activity,
brief summary, repos, branch, status and the workspace folder. Identical
entries on the same day are not repeated. Nothing is sent anywhere.

**Reports from chat.** Pick the **SDLC Work Journal** agent (or ask any SDLC
agent) and say what you need:

| Ask | Runs |
|-----|------|
| "weekly report" | `sdlc.py report --period week` |
| "what did I do last month, by ticket" | `sdlc.py report --period last-month --by ticket` |
| "yearly report" | `sdlc.py report --period year --by ticket` |
| "when did I work on PROJ-123" | `sdlc.py report --ticket PROJ-123 --period all --by ticket` |
| "all my bugfixes this year" | `sdlc.py report --period year --activity bugfix` |

Command reference:

| Command | Purpose |
|---------|---------|
| `sdlc.py log KEY --activity A --summary "..." [--title T --repos a,b --branch B --status S]` | add an entry (also usable by hand) |
| `sdlc.py worklog [--ticket K --period P --json]` | raw list of entries |
| `sdlc.py report [--period P --by day or ticket --ticket K --activity A --from D --to D --out file.md]` | Markdown report with totals, per day or per ticket |

Activities: understanding, impact-analysis, planning, development, bugfix,
refactor, testing, quality-gate, code-review, commit, merge-request,
jira-update, spike, investigation, other. Weeks run Monday to Sunday.
