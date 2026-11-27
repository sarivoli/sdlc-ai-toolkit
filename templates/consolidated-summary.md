### ✅ Delivery summary — {{ticket_key}}: {{ticket_title}}

**Developer:** {{developer}} · **Date:** {{date}} · **Repos:** {{repo_count}} · **Commits:** {{commit_count}} · **Files:** {{files_total}} (+{{insertions_total}} / -{{deletions_total}})

#### What was done
<!-- guidance: 3-6 bullets in business language, mapped to the acceptance criteria. -->
{{what_was_done}}

#### Merge requests
| Repo | Branch → target | MR | Commits | Files |
|------|-----------------|----|---------|-------|
{{#each repos}}
| {{name}} | `{{branch}}` → `{{target}}` | {{mr_link}} | {{commit_count}} | {{files_changed}} |
{{/each}}

#### Commits
{{#each repos}}
**{{name}}**
{{#each commits}}
- `{{short_sha}}` {{subject}}
{{/each}}

{{/each}}

#### Quality gate
{{quality_summary}}

#### Impact & risk
{{impact_short}}

#### Testing notes for QA
{{qa_notes}}

{{#if follow_ups}}
#### Follow-ups
{{follow_ups}}
{{/if}}
