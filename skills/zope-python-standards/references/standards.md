# Team standards - Python / Zope
<!-- Edit this file to match your team. It is the single source of truth the agents use. -->

## General Python
- PEP 8, enforced by the configured linter/formatter (default ruff). Max line length = the repo's config.
- Imports: stdlib, third-party, Zope/Plone, local - one per line in Zope packages (`from x import y` each on its own line), sorted.
- Type hints on new public functions where the repo's Python version allows; don't add typing churn to untouched code.
- No bare `except:`; catch the narrowest exception, log with context, re-raise when you can't handle it.
- Logging: `logger = logging.getLogger(__name__)`; no `print`. Never log secrets or personal data.
- No mutable default arguments. f-strings over `%` for new code (unless Py2 support is required).
- Docstrings on public modules/classes/functions explaining WHY, not WHAT.

## Zope specifics
- Register components in ZCML, not via Python side effects. Keep `for=`, `layer=` and `permission=` explicit on views.
- Never use `zope2.Public` / `zope.Public` for views that change state.
- Page templates: escape by default; `structure` only for trusted, sanitised HTML - comment why.
- Avoid relying on implicit acquisition for new code; use explicit lookups (`api.portal.get_tool`, `getToolByName`, adapters).
- Persistent classes: new attributes need class-level defaults so old objects load; renames/moves need an upgrade step or alias. Mutating `dict`/`list` attributes requires `PersistentMapping`/`PersistentList` or `self._p_changed = True`.
- Long-running loops over the catalog: batch, `transaction.savepoint(optimistic=True)` periodically, don't wake up all objects (`getObject`) unnecessarily.
- GenericSetup: bump `metadata.xml` version and add an upgrade step for every profile change.
- Security: use `checkPermission` / declared permissions; plone.protect for CSRF on POST views.

## Tests
- Bug fix => a test that fails before the fix and passes after.
- Use the repo's layer (`INTEGRATION_TESTING`, `FUNCTIONAL_TESTING`) - integration over functional unless browser behaviour is tested.
- Tests must be deterministic: no network, no sleeps, no dependence on ordering.

## Review checklist
- [ ] Meets every acceptance criterion in understanding.md
- [ ] Only changes listed in plan.md
- [ ] Tests added/updated and meaningful
- [ ] ZCML/GenericSetup/upgrade steps consistent
- [ ] No new security exposure (permissions, `structure`, traversal, SQL, shell)
- [ ] No debug code, commented-out code, or TODOs without a ticket key
- [ ] Logging and error handling follow the rules above
