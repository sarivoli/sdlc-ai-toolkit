---
name: work-journal
description: Automatically record every piece of ticket work (impact analysis, development, bugfix, testing, commits, MRs ...) in the developer's personal, cross-workspace work journal, and generate daily, weekly, monthly or yearly work reports from it. Use whenever work happens on a Jira ticket key, or when the user asks what they worked on, when, or for a weekly/monthly/yearly report.
argument-hint: "log PROJ-123 ... | report week|month|year"
---

# Work journal

One personal file, `~/.copilot/sdlc-journal/worklog.jsonl`, shared by ALL VS
Code workspaces (path can be changed in `[journal] path`, e.g. a OneDrive
folder). It survives toolkit upgrade and uninstall. Disable with
`[journal] enabled = no`.

## Logging (automatic - do not ask the developer)
Whenever you finish a unit of work on a ticket, run ONE command:

```
@@SDLC@@ log <KEY> --activity <activity> --summary "<what was done, 1-2 short sentences>" [--title "<ticket title>"] [--repos a,b] [--branch <name>] [--status <done|in-progress|blocked>]
```

- Log **after** the activity completes, once per activity per ticket per
  session, not per tool call. Repeated identical entries on the same day
  are ignored.
- Activities: `understanding`, `impact-analysis`, `planning`, `development`,
  `bugfix`, `refactor`, `testing`, `quality-gate`, `code-review`, `commit`,
  `merge-request`, `jira-update`, `spike`, `investigation`, `other`
  (aliases: impact, dev, fix, mr, plan, test, poc, debug).
- The summary says what changed or was found (screens/endpoints touched,
  root cause, tests added, MR link), never secrets or code dumps.
- Pass `--title` the first time you know the ticket title.
- The developer may also say "log this under PROJ-123": run the command.
- If the command fails, mention it in one line and carry on; never block the
  real work on journalling.

## Reports (when the user asks what they worked on)
```
@@SDLC@@ report --period today|yesterday|week|last-week|month|last-month|year|last-year|all [--by day|ticket] [--ticket KEY] [--activity A] [--from YYYY-MM-DD --to YYYY-MM-DD] [--out file.md]
@@SDLC@@ worklog --ticket KEY --period all        # raw list, add --json for JSON
```
1. Map the request to a period ("this week" -> `week`, "last month" ->
   `last-month`, "2025" -> `--from 2025-01-01 --to 2025-12-31`).
2. Use `--by day` for "what did I do when", `--by ticket` for "what did I do
   on each ticket".
3. Show the report in chat. Offer a short narrative summary on top (themes,
   tickets completed, time spread) but do not invent anything that is not in
   the journal. Offer `--out` to save it as Markdown.
4. Empty result: say so and check `@@SDLC@@ doctor` for the journal path.
