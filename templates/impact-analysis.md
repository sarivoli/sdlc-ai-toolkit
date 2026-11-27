<!-- guidance: Written by the Impact Analyst. Base every row on code you actually read or searched; cite file paths and line numbers. If you could not verify something, say so. -->
## Impact analysis — {{ticket_key}}

**Overall risk:** {{risk_level}} (low / medium / high) · **Repos affected:** {{repo_count}}

### Summary
{{impact_summary}}

### Affected components
<!-- guidance: One row per file/module to change or that is affected indirectly. -->
| Repo | File / module | Change type | Why it is affected | Risk |
|------|---------------|-------------|--------------------|------|
{{component_rows}}

### Change trace (whole-method scope)
<!-- guidance: One row per changed unit (function/method/class/directive/service/controller/model/query). If one line changed, the whole method is listed. Layer = Angular | Python controller | Model/SQLAlchemy | Util | Template. Upstream = callers/routes/screens reaching it; Downstream = tables, services, helpers it touches. See skills/impact-analysis/references/fullstack-trace-checklist.md -->
| Repo | Layer | Unit (file:line, name) | Change | Upstream (screens / endpoints / callers) | Downstream (tables / services) |
|------|-------|------------------------|--------|-------------------------------------------|--------------------------------|
{{trace_rows}}

### XML configuration references
<!-- guidance: Every XML file/element referencing a changed unit (ZCML, GenericSetup profiles, menus, workflows, build/config XML ...), with file:line and verdict: still correct / needs change / needs new entry. -->
| XML file:line | Element | Wires | Changed unit | Verdict |
|---------------|---------|-------|--------------|---------|
{{xml_rows}}

### Zope / framework touch-points
<!-- guidance: Tick each that applies and explain: ZCML registrations (adapters, utilities, browser views, subscribers), interfaces, page templates (ZPT), skins/layers, catalog indexes & metadata, ZODB persistent classes (schema change => migration / upgrade step), GenericSetup profiles, permissions & roles, i18n message ids, acquisition-dependent lookups. -->
{{zope_touchpoints}}

### Impacted screens and endpoints
<!-- guidance: Screens (UI pages, forms, reports, menus) and endpoints (browser views, REST/JSON/XML-RPC routes) affected directly or through callers, with path, method and permission where known. Feeds the QA hand-off comment. -->
| Kind | Name / path | Method | Permission | Source (frontend route/template or backend view) | Changed unit |
|------|-------------|--------|------------|--------------------------------------------------|--------------|
{{screens_and_endpoints}}

### Use cases to validate
<!-- guidance: Happy path, edge, negative/permission and regression cases QA should run. -->
{{use_cases}}

### Callers and dependants
<!-- guidance: Who calls the code you will change (search usages across ALL repos in the workspace). Include dynamic lookups: getattr, restrictedTraverse, queryAdapter/getUtility by name, ZCML-registered names, TAL path expressions. -->
{{callers}}

### Data & migration impact
{{data_impact}}

### Backward compatibility
{{compatibility}}

### Tests
| Existing tests that cover this | New tests needed |
|--------------------------------|------------------|
{{test_rows}}

### Risks and mitigations
{{risks}}

### Rollback plan
{{rollback}}
