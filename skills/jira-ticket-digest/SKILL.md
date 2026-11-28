---
name: jira-ticket-digest
description: Read a Jira Cloud ticket completely (fields, description, ALL comments, linked issues, sub-tasks, attachment names) through the Atlassian MCP server and produce the team's "understanding summary" from the ticket-understanding template. Use when the user gives a ticket key like PROJ-123 or asks what a ticket is about.
argument-hint: PROJ-123
---

# Jira ticket digest

Load the `sdlc-conventions` skill first.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer.

## Steps
1. Validate the key against `[jira] ticket_regex` and `project_keys` from
   `@@SDLC@@ config`. If it does not match, ask.
2. Fetch the issue with the Atlassian MCP tools (`atlassian/*`): summary,
   type, status, priority, reporter, assignee, labels, components, fix
   versions, description, acceptance-criteria custom field if present.
3. Fetch **every** comment (page through them; oldest first). For each, note
   author, date and whether it changes scope, adds a decision, or contradicts
   something earlier. The latest decision wins - say so when it overrides.
4. Fetch linked issues and sub-tasks (key, summary, status, link type).
   Read the description of "blocks / is blocked by / duplicates" links.
5. If Confluence pages are linked, read them (titles + relevant sections).
6. Fill `@@SDLC@@ template ticket-understanding.md`. Rules:
   - Never invent requirements. Unknowns go to *Open questions*.
   - Derived acceptance criteria are marked "(derived)".
   - Confidence is **low** if there are open questions that change the
     solution.
7. Save to `<workdir>/understanding.md` and show it in chat.
8. Posting: if `[jira] progress_updates` is `every_stage`, offer to post it as
   a Jira comment (confirmation required). If confidence is low, recommend
   posting the open questions instead and pausing.

## Output quality bar
A teammate who never saw the ticket can explain the problem, the acceptance
criteria and what is still unclear after reading only this summary.
