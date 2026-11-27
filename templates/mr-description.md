## {{ticket_key}}: {{ticket_title}}

**Jira:** [{{ticket_key}}]({{ticket_url}}) · **Type:** {{ticket_type}} · **Risk:** {{risk_level}}

### What & why
<!-- guidance: 2-4 sentences: the problem and the solution, for a reviewer who has not read the ticket. -->
{{what_and_why}}

### Changes in this repo (`{{repo_name}}`)
{{#each commits}}
- `{{short_sha}}` {{subject}}
{{/each}}

**Files:** {{files_changed}} changed · +{{insertions}} / -{{deletions}}

{{#if sibling_mrs}}
### Related MRs — merge together
{{#each sibling_mrs}}
- {{repo}}: {{url}}
{{/each}}
{{/if}}

### How to test
<!-- guidance: Numbered steps a reviewer can follow locally, including buildout/instance commands if relevant. -->
{{how_to_test}}

### Quality gate
{{quality_summary}}

### Impact & risk
{{impact_short}}

### Checklist
- [ ] Acceptance criteria from {{ticket_key}} met
- [ ] Tests added/updated and passing
- [ ] No ZODB schema change, or upgrade step included
- [ ] ZCML / GenericSetup changes reviewed
- [ ] Docs / changelog updated
- [ ] Merge order with related MRs agreed

<sub>Prepared with the SDLC AI Toolkit by {{developer}}. A human reviewed and approved every change.</sub>
