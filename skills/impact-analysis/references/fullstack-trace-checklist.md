# Full-stack trace checklist (frontend -> API -> backend -> data -> XML)

Use together with `zope-impact-checklist.md`. The stack has Angular
(directives, services, controllers, templates), Python controllers/views,
models and SQLAlchemy methods, with XML configuration (ZCML, GenericSetup,
and any other XML the project uses).

## Rule: whole-method scope
If even ONE line of a method/function changed, treat the ENTIRE method (and
the class it lives in, for class-level state) as changed. Build the trace
from the whole unit, never from the diff hunk.

Changed unit = Python function/method, SQLAlchemy model/query method,
Angular controller function, service method, directive (link/controller/
template), filter, route/state definition, or a template fragment.

Get the units from the actual diff (`git diff <target>...HEAD`), expand each
hunk to its enclosing function/class, and list them in the trace table.

## Use Orbit first (scoped to the current workspace folder)
`@@SDLC@@ orbit index` then, per changed unit: `orbit grep` for the name,
dotted path and string references (also over `.zcml`/`.xml`/`.html`), and
`orbit context` for source, callers and tests. The graph is per workspace
folder (`<folder>/.sdlc/orbit`), so results only cover this product/version.
Confirm gaps (dynamic lookups, XML) with plain grep and record Orbit as the
evidence source in the report.

## Trace each changed unit in BOTH directions
**Upwards (who reaches it - find endpoints and screens)**
1. Callers across ALL repos (usages / grep for the name, dotted path and any
   string references: `getattr`, `queryAdapter(name=)`, `$injector.get('X')`,
   `$controller('X')`, template `ng-controller`, `ng-include`, route `controller:`).
2. Backend: Python method -> controller/view -> URL (ZCML `browser:page`,
   route/blueprint/REST registration, `@route`, traversal name) -> HTTP method
   and permission.
3. Frontend: service method -> controllers/directives/components injecting it
   -> templates (`.html`) and routes/states -> screens and menu entries;
   service `$http`/`$resource` URL -> backend endpoint.
4. Directive: every template using its tag/attribute/class (`restrict`
   matters) and every screen rendering those templates.

**Downwards (what it touches - find data and config)**
5. SQLAlchemy: models, tables, columns, relationships, query/filter methods,
   sessions/transactions, stored procedures/raw SQL, Alembic/migration files,
   indexes. Note read vs write and cascade effects.
6. Other backends: ZODB objects/catalog, external HTTP services, queues,
   files, caches.
7. Shared helpers/utilities called by the unit (one level down, deeper if
   they are shared widely).

## XML configuration references (list ALL for every changed unit)
Search every XML file in all repos for the unit's dotted path, class,
interface, view/template name, permission, utility name and URL fragment.
Report file:line, the element and what it wires. Check at least:
- ZCML: `configure.zcml`, `browser/configure.zcml`, `overrides.zcml`,
  `meta.zcml`, `permissions.zcml` (`browser:page|view|viewlet`, `adapter`,
  `utility`, `subscriber`, `include`, `permission`).
- GenericSetup: `profiles/*/*.xml` (`rolemap`, `workflows`, `types`,
  `registry`, `catalog`, `actions`, `controlpanel`, `viewlets`, `metadata.xml`).
- Page-template/skin XML, menu/action definitions, workflow definitions.
- Build/config XML (`pom`, `web.xml`, logging, report/layout definitions)
  when present in the repo.
- Any other `*.xml` containing a match (use a repo-wide search, do not assume).
For each hit say: still correct / needs change / needs new entry.

## Use cases from the trace
For each impacted screen/endpoint derive: happy path, edge/boundary,
negative and permission cases, and a regression case. Each use case names the
screen or endpoint, the changed unit that justifies it, and the XML/config it
exercises.

## Output
Fill the `Change trace` table in `impact-analysis.md` (one row per changed
unit) and the `XML configuration references` section. Mark anything not
verified as "unverified".
