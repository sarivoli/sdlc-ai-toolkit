---
name: impact-analysis
description: Analyse the impact of a Jira ticket on the current source code across ALL repositories in the workspace - frontend (Angular) and backend (Python, SQLAlchemy) change trace by whole method, endpoints, XML configuration references, affected files, Zope wiring (ZCML, adapters, templates, catalog, ZODB), callers, data migration, compatibility, tests and risk - and write it using the team's impact-analysis template. Use after the ticket understanding exists, or when asked "what does this change affect?".
argument-hint: PROJ-123
---

# Impact analysis

Load `sdlc-conventions` and `zope-python-standards` first. Read
`<workdir>/understanding.md`; if missing, run `jira-ticket-digest` first.

## Steps
0. **Orbit code graph (per workspace folder).** Run
   `@@SDLC@@ orbit index` (incremental; indexes every repo under the current
   workspace folder into `<folder>/.sdlc/orbit`, isolated from other
   workspaces/products/versions). Then use it for the trace:
   `@@SDLC@@ orbit grep --repo <repo> -- "<name>"` (matches with enclosing
   definitions) and `@@SDLC@@ orbit context --repo <repo> -- <args>` (source,
   callers, tests). Use it for callers, imports, tests and XML/config
   references; cite results as "Orbit (<workspace folder>)". If the CLI is
   missing or fails, say so and fall back to grep/usages. Never mix results
   from another workspace folder. The `gitlab-orbit` MCP (if signed in) adds
   MR/issue context from GitLab.
1. `@@SDLC@@ repos` - list every repo in the workspace with its branch and
   whether it is dirty. Warn about dirty repos before going further.
2. If a repo is unfamiliar and large, use the `acquire-codebase-knowledge`
   skill to map it first (only once per repo; reuse its notes).
3. **Build the change trace.** If code already changed (post-implementation)
   or a plan lists files, take the diff and expand every hunk to the WHOLE
   enclosing method/function/class (one changed line = whole method in
   scope). Follow [the full-stack checklist](./references/fullstack-trace-checklist.md):
   Angular directives/services/controllers/templates, Python controllers/views,
   models and SQLAlchemy methods; trace upwards to endpoints and screens and
   downwards to tables, and list every XML configuration reference.
   Before implementation, do the same for the units you expect to change.
3b. Locate the entry points: search for terms from the ticket (UI labels,
   error messages, view names, field names, permission names, URLs).
4. For each candidate, follow the Zope wiring with
   [the checklist](./references/zope-impact-checklist.md). Search across
   ALL repos, not just the one you started in - shared packages are
   often in another checkout (`src/` via mr.developer, eggs, etc.).
5. Find callers and dependants, including dynamic lookups
   (`getattr`, `restrictedTraverse`, `unrestrictedTraverse`,
   `queryMultiAdapter`, `getUtility(name=...)`, ZCML `name=`, TAL path
   expressions `context/@@view`, `python:` expressions, skin script names).
6. Identify existing tests that cover the code and the new tests needed.
7. Score risk with the matrix in the checklist. Any ZODB persistent class
   change, catalog index change, security/permission change, or public API
   change is at least **medium**.
8. Fill `@@SDLC@@ template impact-analysis.md`, including **Impacted screens
   and endpoints** and **Use cases to validate**. The Jira QA hand-off
   (`jira-impact-comment.md`) is posted later by the Release Scribe, after
   developer validation. Cite `repo/path:line` for
   every row. If something could not be verified, write "unverified".
9. Save to `<workdir>/impact.md`. Then hand over to the
   `implementation-plan` skill.

Impacted screens, endpoints, XML references and use cases must come from
the trace, not from guesses. Re-run the trace after implementation so the
Jira QA hand-off reflects the real diff.

Never edit files during impact analysis.
