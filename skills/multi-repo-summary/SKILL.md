---
name: multi-repo-summary
description: Collect every commit for a Jira ticket across all repositories and generate ONE consolidated summary plus per-repo MR descriptions and a Teams/Outlook update from the team templates. Use after committing, or when asked to summarise work across repos.
argument-hint: PROJ-123
---

# Multi-repo consolidated summary

Load `sdlc-conventions`.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer.

1. `@@SDLC@@ collect <KEY>` -> `<workdir>/commits.json` (repos, branches,
   commits, files, +/- lines, pushed or not). The numbers come from git;
   never type them by hand.
2. Write `<workdir>/narrative.json` with the fields the templates need that
   git cannot know. Required keys:
   ```json
   {
     "ticket_title": "", "ticket_type": "", "risk_level": "low|medium|high",
     "what_was_done": "- bullet\n- bullet",
     "what_and_why": "", "how_to_test": "1. ...", "quality_summary": "",
     "impact_short": "", "qa_notes": "", "follow_ups": "",
     "one_line_summary": "", "reviewers": "",
     "impact_summary": "", "repo_list": "", "branch_list": "",
     "screen_rows": "| Screen | Path | Change | Direct |", "endpoint_rows": "| /@@view | GET | View | Change | Direct |",
     "use_case_rows": "| 1 | Case | Steps | Expected | Happy |",
     "changed_units": "- Layer: file:method", "xml_refs": "- file:line element -> wires X", "regression_areas": "",
     "test_data_notes": "", "data_impact": "", "risks": "", "open_items": "",
     "per_repo": { "<repo-name>": { "what_and_why": "", "how_to_test": "" } }
   }
   ```
   Refresh the impact fields (screens, endpoints, use cases) from the
   ACTUAL diff, since the code may differ from the plan.
   Take content from understanding.md, impact.md, plan.md and quality.md.
   `per_repo` overrides global fields for that repo's MR.
3. `@@SDLC@@ summary <KEY>` renders `summary.md`, `qa-handoff.md`, `mr-<repo>.md` for each
   repo and `teams.md`. If it lists missing fields, add them to
   narrative.json and run again until nothing is missing.
4. After MRs exist (`mrs.json` written by `gitlab-mr-publisher`) run
   `summary` again so every MR links to its siblings and the summary table
   has MR links.
5. Show `summary.md` to the developer.
