<!-- guidance: QA & stakeholder hand-off, posted to Jira AFTER the developer has validated the change. Refresh every field from the ACTUAL diff (commits.json, git diff), not from the pre-implementation plan. Business language; QA and PMs read this. Impacted screens/endpoints: derive from ZCML browser:page/view registrations, page templates, REST/JSON/XML-RPC routes, menu/action entries and form classes touched directly or via callers. Mark anything unverified as "unverified". -->
### 🔎 Impact & QA hand-off — {{ticket_key}}: {{ticket_title}}

**Overall risk:** {{risk_level}} · **Repos / MRs:** {{repo_list}} · **Branch(es):** {{branch_list}}

#### What changed
{{impact_summary}}

#### Impacted screens (UI)
<!-- guidance: One row per screen/page/form/report/menu: where users reach it, what is different now. -->
| Screen / page | Navigation path | Change | Direct / indirect | Changed unit (frontend) |
|---------------|-----------------|--------|-------------------|-------------------------|
{{screen_rows}}

#### Impacted endpoints (API / views)
<!-- guidance: One row per URL/view name/REST/JSON/XML-RPC route, with HTTP method and permission where known. -->
| Endpoint / view | Method | Permission | Change | Direct / indirect | Changed unit (backend) |
|-----------------|--------|------------|--------|-------------------|------------------------|
{{endpoint_rows}}

#### Use cases to validate
<!-- guidance: Numbered, executable by QA without reading code. Include happy path, edge cases, negative/permission cases and at least one regression case per impacted area. -->
| # | Use case | Steps | Expected result | Type |
|---|----------|-------|-----------------|------|
{{use_case_rows}}

#### Changed units (whole-method scope)
<!-- guidance: Short list: Angular directive/service/controller and Python controller/model/SQLAlchemy methods changed. One changed line = the whole method is listed. -->
{{changed_units}}

#### XML configuration involved
<!-- guidance: ZCML / GenericSetup / other XML entries that reference the changed units, as file:line + what it wires. -->
{{xml_refs}}

#### Regression areas
{{regression_areas}}

#### Test data / environment notes
{{test_data_notes}}

{{#if data_impact}}#### Data / migration impact
{{data_impact}}
{{/if}}
{{#if risks}}#### Risks & rollback
{{risks}}
{{/if}}
{{#if open_items}}#### Open items / known limitations
{{open_items}}
{{/if}}
_Developer-validated · {{developer}} · {{timestamp}} · Full analysis: `.sdlc/{{ticket_key}}/impact.md`_
