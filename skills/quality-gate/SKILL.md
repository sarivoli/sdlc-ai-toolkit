---
name: quality-gate
description: Run the team quality gate on every repo changed for a ticket - lint, format, type check, security scan and tests from the team config - plus a standards and security review, and produce the quality report. Must pass before committing. Use when asked to check, verify, lint or test changes.
argument-hint: PROJ-123
---

# Quality gate

Load `sdlc-conventions` and `zope-python-standards`.

**Orbit preflight first:** run `@@SDLC@@ preflight` (rules in `sdlc-conventions`). If it stops (exit 3), tell the developer to install Orbit or run the index first to save tokens, with the command it printed, and wait for their answer.

1. Run `@@SDLC@@ quality <KEY>`. It detects changed files per repo, runs the
   configured checks (`[quality]` in config), and writes `quality.md` and
   `quality.json` to the workdir. Exit code 0 = PASS, 1 = FAIL.
2. For each failing check: read the output, fix the cause **within the scope
   of the approved plan**, and re-run. Formatting-only fixes are allowed;
   anything else that changes behaviour must be explained to the developer.
3. For checks reported `missing`, tell the developer which tool to install
   (e.g. `pip install ruff bandit`) - don't pretend they passed.
4. Review the diff (`git diff <target>...` per repo) against the review
   checklist in `zope-python-standards`.
5. Run the `security-review` skill on the changed files when the impact
   analysis risk is medium/high or the diff touches permissions, traversal,
   templates with `structure`, SQL, subprocess or file paths. For high-risk
   tickets suggest the `SE: Security` agent.
6. Add review findings to the bottom of `quality.md` under "Findings to fix".
7. Report: PASS/FAIL per repo, what was fixed, what is left. Only on PASS
   hand over to commits.

## Panel (when the `sdlc-ui` tools are available)
After `@@SDLC@@ quality <KEY>`, show `sdlc_ui_quality` `{ticket}` instead of pasting quality.md. Otherwise write it as text. Rules: `sdlc-conventions` > Panels in chat.
