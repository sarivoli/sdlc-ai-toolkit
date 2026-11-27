## Quality gate — {{ticket_key}}

**Result:** {{result}} · **Run at:** {{timestamp}}

{{#each repos}}
### {{name}}
| Check | Command | Result | Details |
|-------|---------|--------|---------|
{{check_rows}}

{{/each}}
{{#if findings}}
### Findings to fix
{{findings}}
{{/if}}
<!-- guidance: "Result" is PASS only if every required check passed in every repo. Skipped (tool missing) checks are listed, never hidden. -->
