<!-- guidance: This is the approval gate. Keep it short enough to review in 2 minutes. Nothing outside this plan may be implemented without asking. -->
## Implementation plan — {{ticket_key}}

**Approach:** {{approach}}

### Steps
<!-- guidance: Ordered, one line each, grouped by repo. Each step names the file(s). Tests first where practical. -->
{{steps}}

### Branches
{{#each repos}}
- `{{name}}` → `{{branch}}` (from `{{base}}`)
{{/each}}

### Planned commits
<!-- guidance: One line per atomic commit, already in the commit format. -->
{{planned_commits}}

### Not doing
{{not_doing}}

---
✅ Reply **approve** to implement, or tell me what to change.
