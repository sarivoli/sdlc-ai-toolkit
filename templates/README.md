# Templates

Every artefact the agents produce is shaped by a template in this folder.
Change the wording, add or remove sections, re-run `python install.py`, and
every developer's agents follow the new format.

## Placeholder syntax

| Syntax | Meaning |
|--------|---------|
| `{{name}}` | A single value, e.g. `{{ticket_key}}` |
| `{{#each repos}} ... {{/each}}` | Repeat the block for every item; inside it use the item's fields, e.g. `{{name}}` |
| `{{#if risk_notes}} ... {{/if}}` | Only keep the block if the value is non-empty |
| `<!-- guidance: ... -->` | Instructions to the agent. Removed from the final output |

The deterministic parts (commit lists, file counts, MR links) are filled by
`scripts/sdlc.py summary`; the narrative parts are written by the agent
following the guidance comments.

## Precedence (first match wins)

1. `<repo>/.sdlc/templates/<file>` - per-project override, committed in that repo
2. `<workspace root>/.sdlc/templates/<file>` - per-workspace override
3. `~/.copilot/sdlc-toolkit/templates/<file>` - team default (installed from here)

## Files

| File | Produced by | Posted to |
|------|-------------|-----------|
| `ticket-understanding.md` | Ticket Analyst | Jira comment + `.sdlc/<KEY>/understanding.md` |
| `impact-analysis.md` | Impact Analyst | `.sdlc/<KEY>/impact.md` (+ summary in Jira) |
| `jira-impact-comment.md` | Release Scribe (after developer validation) | Jira QA / stakeholder hand-off: impacted screens, endpoints, use cases to validate |
| `implementation-plan.md` | Impact Analyst | `.sdlc/<KEY>/plan.md` - the approval gate |
| `commit-message.txt` | Release Scribe / commit-discipline | git |
| `quality-report.md` | Quality Gate | `.sdlc/<KEY>/quality.md` + MR |
| `mr-description.md` | Release Scribe | each GitLab MR |
| `jira-progress-comment.md` | any stage | Jira comment |
| `consolidated-summary.md` | Release Scribe | Jira comment + `.sdlc/<KEY>/summary.md` |
| `teams-update.md` | Release Scribe | text to paste in Teams / Outlook |
