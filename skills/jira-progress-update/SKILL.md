---
name: jira-progress-update
description: Post short, templated progress comments, the final consolidated summary, labels and workflow transitions to a Jira Cloud ticket through the Atlassian MCP server, following the team's update frequency setting. Use at each SDLC stage or when asked to update Jira.
argument-hint: PROJ-123 <stage>
---

# Jira progress updates

Load `sdlc-conventions`. Read `[jira]` from `@@SDLC@@ config`.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer. (Skip it when the stage that calls this skill already ran it.)

## When to post
| `progress_updates` | Stages that get a comment |
|--------------------|---------------------------|
| `every_stage` | understanding (or open questions), plan approved, implementation done, quality gate result, MRs opened + final summary |
| `milestones` | plan approved, MRs opened + final summary |
| `off` | final summary only |

Stage icons: 🧭 understanding · 📝 plan approved · 🛠 implemented · 🔍 quality gate · 🚀 MRs opened · ⛔ blocked.

## How
1. Progress comment: fill `@@SDLC@@ template jira-progress-comment.md`.
   After developer validation also post `<workdir>/qa-handoff.md` (impact,
   impacted screens/endpoints, use cases for QA), then the final summary:
   `<workdir>/summary.md` as is.
2. Show the exact text and ask for confirmation (`jira_comment`). Post with
   the Atlassian MCP comment tool as Markdown.
3. Transitions: on start use `transition_on_start`, when MRs are opened use
   `transition_on_mr`. Look up the transition id by name for this issue; if
   the name doesn't exist, list available transitions and ask. Confirmation
   required (`jira_transition`).
4. Add `[jira] label` to the issue if set and not already present.
5. Never edit or delete other people's comments. Never change assignee,
   priority or fix version unless asked.
