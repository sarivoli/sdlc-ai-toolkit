---
name: sdlc-conventions
description: Shared rules for every SDLC toolkit agent - where team config and templates live, the per-ticket notes folder, the helper CLI, and the safety rules (confirmations, never merge, never force-push). Load this before any other sdlc skill or whenever working on a Jira ticket end to end.
user-invocable: false
---

# SDLC toolkit conventions

## The helper CLI
All deterministic work goes through one command. Call it exactly like this
(paths are filled in by the installer):

```
@@SDLC@@ <command> ...
```

| Need | Command |
|------|---------|
| **Orbit preflight (before any ticket work)** | `@@SDLC@@ preflight` |
| Setup status: Orbit index, git auth, Jira auth | `@@SDLC@@ checklist` |
| Team settings (Jira site, GitLab group, commit rules, quality commands) | `@@SDLC@@ config` |
| A template, with per-repo overrides applied | `@@SDLC@@ template <file> [--repo <path>]` |
| Repos in the workspace + branch / dirty state | `@@SDLC@@ repos` |
| Per-ticket notes folder | `@@SDLC@@ workdir <KEY>` |
| Branch name for a ticket | `@@SDLC@@ branch-name <KEY> --type bugfix [--user <name> | --poc <poc_name>]` |
| Validate a commit message before committing | `@@SDLC@@ check-commit --message "<msg>"` |
| Run the quality gate | `@@SDLC@@ quality <KEY>` |
| List the ticket's commits across all repos | `@@SDLC@@ collect <KEY>` |
| Render summary / MR / Teams texts | `@@SDLC@@ summary <KEY>` |
| Record work in the personal journal | `@@SDLC@@ log <KEY> --activity <a> --summary "<brief>"` |
| Work reports (week / month / year) | `@@SDLC@@ report --period week` |

Read `config` once at the start of a session and follow it. Never hard-code
values that the config defines.

## Orbit preflight (mandatory before ticket work)
Every workflow that works on a Jira ticket (digest / analysis, impact, plan,
implement, quality gate, commits, summary, MRs, Jira updates) starts with,
in the workspace folder:

```
@@SDLC@@ preflight
```

It checks that the GitLab Orbit CLI is installed and that every repo of this
workspace folder is in its code index. The index is what keeps token use
low: without it the agent reads far more files to understand the code.

- **Exit 0** - go ahead, and use Orbit (`gitlab-orbit` MCP tools or
  `@@SDLC@@ orbit grep|context`) for code search.
- **Exit 3 (STOP)** - do not start the ticket work. Show the developer the
  message it printed (it names the exact install or index command), say that
  it is needed to save tokens, and ask what to do:
  1. *Index now* - run the printed `orbit index` command yourself (it only
     writes to `<folder>/.sdlc/orbit`), then run `preflight` again.
  2. *Install Orbit* - `npm install -g @gitlab/orbit` changes the machine:
     show the command and wait for "yes" before running it, then index.
  3. *Proceed without Orbit* - only when the developer says so explicitly.
     Write "Orbit: skipped by developer (no index)" at the top of the stage
     output and continue with plain search. Never choose this yourself.
  While it reports *still indexing*, offer to wait (re-run `preflight`) or
  to proceed without it (same rule as 3).
- Run it once per ticket per conversation. When you hand a stage to a
  subagent, start its prompt with `Orbit preflight: passed` or
  `Orbit preflight: skipped by developer`; a subagent that gets either line
  does not run it again.

## Panels in chat (`sdlc-ui` MCP tools)
In editors that show MCP Apps (VS Code Copilot Chat, Cursor) the `sdlc-ui`
server offers `sdlc_ui_*` tools that draw an interactive A2UI panel in the
chat. When the tools are available, use them instead of long text; when they
are not (Claude Code, Codex, Gemini CLI, or `[ui] mode = off`), write the
same content as text, exactly as before.

| When | Tool |
|------|------|
| Before every `[safety] confirm_before` action (show repo, branch, files, exact text/command in `preview`) | `sdlc_ui_confirm` |
| Checkpoint 1: plan.md ready for approval | `sdlc_ui_plan` `{ticket}` |
| After `@@SDLC@@ quality <KEY>` | `sdlc_ui_quality` `{ticket}` |
| Resume a ticket / "where is PROJ-123?" | `sdlc_ui_ticket` `{ticket}` |
| `preflight` stopped, or the developer asks about setup | `sdlc_ui_checklist` |
| End of every stage or skill run: what was done, results, links, next step | `sdlc_ui_summary` |
| Before installing / updating the toolkit, and after it | `sdlc_ui_install_preview`, `sdlc_ui_install_report` |

Rules:
- A panel never replaces the developer's answer. Its buttons only send a
  reply ("yes", "approve", "changes: ...") into the chat as the developer's
  message. Keep waiting for that message exactly as if you had asked in text;
  never act on a panel being shown.
- One panel per step: do not repeat its content as text afterwards. One line
  saying what you are waiting for is enough.
- If a `sdlc_ui_*` call fails, say so in one line and fall back to text.

## Branch convention (team)
`<type>/<username>/<KEY>`; types `feature`, `bugfix`, `spike`, `refactor`,
`chore`. For `spike` the middle part is the POC name, not the user.
Examples: `feature/kumar/JIVA70-1919`, `bugfix/kumar/JIVA70-1929`,
`spike/py3/JIVA66-9988`. Use `branch-name` to build it; never invent names.
Map ticket type -> branch type: Story/Task -> feature, Bug -> bugfix,
Spike/POC -> spike, tech-debt -> refactor, maintenance -> chore.

## Work journal (always)
Every agent that works on a ticket key logs its finished activity with the
`work-journal` skill (`@@SDLC@@ log ...`): one brief entry per activity, no
confirmation needed. The journal is personal and shared across workspaces.

## Per-ticket notes folder
`@@SDLC@@ workdir <KEY>` returns a folder (default `<workspace>/.sdlc/<KEY>/`)
that is excluded from git. Every stage writes its output there so the next
stage - or a teammate - can pick up the work:

| File | Written by |
|------|-----------|
| `understanding.md` | Ticket Analyst |
| `impact.md`, `plan.md` | Impact Analyst |
| `plan.approved` (contains approver + timestamp) | created only after the developer types *approve* |
| `quality.md`, `quality.json` | Quality Gate (via CLI) |
| `commits.json`, `narrative.json`, `mrs.json` | Release Scribe |
| `summary.md`, `mr-<repo>.md`, `teams.md` | Release Scribe (via CLI) |

If a file for an earlier stage exists, read it instead of redoing the work.

## Templates
Every text that leaves the developer's machine (Jira comments, MR
descriptions, commit messages, summaries) MUST be produced from its template:
`@@SDLC@@ template <file>`. Keep the headings and order; follow the
`<!-- guidance: -->` comments, then delete them. Never add sections the
template does not have unless the developer asks.

## Safety rules (non-negotiable)
1. Ask for an explicit "yes" in chat before every action listed in
   `[safety] confirm_before` (edit_repo, push, create_mr, jira_comment, jira_transition).
   `edit_repo` = before the FIRST file edit in each repo: show repo, current
   branch and the files you will change, then wait for "yes" for that repo.
   Show the exact text/command first.
2. Never merge an MR, approve an MR, force-push, rewrite pushed history,
   delete branches, or commit to a protected branch.
3. Never implement anything that is not in an approved plan. If you discover
   more work, stop and propose a plan change.
4. Never put secrets, tokens or customer data in commits, comments or MRs.
5. If a tool or MCP call fails twice, stop and tell the developer what failed
   and what to do; don't work around it silently.
6. Report honestly: a skipped check is "skipped", not "passed".
