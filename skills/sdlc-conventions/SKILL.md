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
| Team settings (Jira site, GitLab group, commit rules, quality commands) | `@@SDLC@@ config` |
| A template, with per-repo overrides applied | `@@SDLC@@ template <file> [--repo <path>]` |
| Repos in the workspace + branch / dirty state | `@@SDLC@@ repos` |
| Per-ticket notes folder | `@@SDLC@@ workdir <KEY>` |
| Branch name for a ticket | `@@SDLC@@ branch-name <KEY> --type bugfix [--user <name> | --poc <poc_name>]` |
| Validate a commit message before committing | `@@SDLC@@ check-commit --message "<msg>"` |
| Run the quality gate | `@@SDLC@@ quality <KEY>` |
| List the ticket's commits across all repos | `@@SDLC@@ collect <KEY>` |
| Render summary / MR / Teams texts | `@@SDLC@@ summary <KEY>` |

Read `config` once at the start of a session and follow it. Never hard-code
values that the config defines.

## Branch convention (team)
`<type>/<username>/<KEY>`; types `feature`, `bugfix`, `spike`, `refactor`,
`chore`. For `spike` the middle part is the POC name, not the user.
Examples: `feature/kumar/JIVA70-1919`, `bugfix/kumar/JIVA70-1929`,
`spike/py3/JIVA66-9988`. Use `branch-name` to build it; never invent names.
Map ticket type -> branch type: Story/Task -> feature, Bug -> bugfix,
Spike/POC -> spike, tech-debt -> refactor, maintenance -> chore.

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
