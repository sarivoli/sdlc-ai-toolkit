---
name: gitlab-mr-publisher
description: Push ticket branches and create or update GitLab merge requests in every affected repo with the team MR template, cross-linking sibling MRs, then record them for the consolidated summary. Use when asked to open MRs, publish, or raise merge requests for a ticket.
argument-hint: PROJ-123
---

# GitLab MR publisher

Load `sdlc-conventions`. Requires `<workdir>/commits.json` and the rendered
`mr-<repo>.md` files from `multi-repo-summary`.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer.

1. Show the developer a table: repo, branch -> target, commits, pushed?
   Ask **one** confirmation for pushing all listed branches.
2. Push each branch: `git push -u origin <branch>` (never `--force`; if
   rejected, stop and explain).
3. For each repo, with the GitLab MCP tools (`gitlab/*`):
   - Look for an existing open MR from this source branch; update it instead
     of creating a duplicate.
   - Otherwise create one: title `<KEY>: <ticket title>` (prefix `Draft: `
     when `[gitlab] mr_draft = true`), description = `mr-<repo>.md`,
     target = the repo's target branch, labels = `[gitlab] mr_labels`,
     `remove_source_branch` and `squash` from config, reviewers from
     CODEOWNERS / `default_reviewers` if supported.
   Confirmation required before the first MR is created (`create_mr`).
4. Write `<workdir>/mrs.json`: `{"<repo-name>": {"url": "...", "iid": 12}}`.
5. Re-run `@@SDLC@@ summary <KEY>` and update every MR description with the
   re-rendered `mr-<repo>.md` (now containing sibling MR links).
6. Never approve, merge, or close MRs.

## Panel (when the `sdlc-ui` tools are available)
Before creating MRs ask with `sdlc_ui_confirm` (`action` `create_mr`, the MR title and description in `preview`). Afterwards show `sdlc_ui_summary` with each MR as a link. Otherwise write it as text. Rules: `sdlc-conventions` > Panels in chat.
