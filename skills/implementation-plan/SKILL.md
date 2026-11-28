---
name: implementation-plan
description: Turn a ticket understanding and impact analysis into a short, reviewable implementation plan (steps per repo, branches, planned atomic commits, not-doing list) using the team template, then STOP for developer approval. Use before any code change for a ticket.
argument-hint: PROJ-123
---

# Implementation plan (approval gate)

Load `sdlc-conventions`. Read `<workdir>/understanding.md` and `<workdir>/impact.md`.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer.

1. Choose the simplest approach that meets every acceptance criterion. If
   there are real alternatives, list them in one line each with the reason
   for the choice.
2. For each repo take the branch from `@@SDLC@@ repos` (its current branch)
   when `[git] branch_mode = current`; only when it is `new` compute one with
   `@@SDLC@@ branch-name <KEY> --type <feature|bugfix|spike|refactor|chore> [--user <name> | --poc <poc_name>]`.
   If the current branch is protected, say so in the plan and ask what to do.
3. Write steps grouped by repo, tests first where practical.
4. Write the planned commits already in the commit format
   (`@@SDLC@@ template commit-message.txt`), one logical change each.
5. Fill `@@SDLC@@ template implementation-plan.md`, save to `<workdir>/plan.md`, show it
   (with the `sdlc_ui_plan` panel when the `sdlc-ui` tools are available).
6. Optionally offer the `Critical thinking mode instructions` agent to
   challenge the plan for high-risk tickets.
7. **Stop.** Only when the developer replies *approve* (or equivalent), write
   `<workdir>/plan.approved` with their name and the time. If they ask for
   changes, update plan.md and ask again.
8. If `[jira] progress_updates` is `every_stage` or `milestones`, offer a
   "Plan approved" progress comment (confirmation required).

## Panel (when the `sdlc-ui` tools are available)
Show the plan with `sdlc_ui_plan` `{ticket}`. Its Approve button sends *approve* into the chat; write `plan.approved` only after that message arrives. Otherwise write it as text. Rules: `sdlc-conventions` > Panels in chat.
