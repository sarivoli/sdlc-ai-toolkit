# Zope / Python impact checklist

Work through every item; mark N/A explicitly.

## Wiring
- [ ] **ZCML**: `configure.zcml`, `browser/configure.zcml`, `overrides.zcml`, `meta.zcml`.
      Search for the class/interface dotted name AND the registered `name=`.
- [ ] **Interfaces** (`interfaces.py`): adding/removing attributes or methods affects every implementer and every adapter lookup.
- [ ] **Adapters / utilities / subscribers**: who provides, who looks up (`IFoo(obj)`, `getAdapter`, `queryUtility`, `zope.component.getMultiAdapter`), event subscribers (`IObjectModifiedEvent`, `IObjectAddedEvent` ...).
- [ ] **Browser views & viewlets**: class, template, `for=`, `layer=`, `permission=`.
- [ ] **Page templates (ZPT / .pt)**: TAL/METAL macros used elsewhere (`use-macro`, `define-macro`), `tal:define` paths that call the changed code.
- [ ] **Skins / Script (Python) / DTML** (Zope 2 / older Plone): skin layer order, objects acquired by name.
- [ ] **Acquisition**: lookups that rely on implicit acquisition (`context.some_name`) can break silently when names move.

## Data
- [ ] **ZODB persistent classes**: new/removed/renamed attributes, class moves (need `zope.deprecation`/module aliases or `persistent` class rename mapping), `__setstate__` defaults. Existing objects do not run `__init__` again.
- [ ] **Upgrade steps / GenericSetup**: `profiles/default/metadata.xml` version bump + upgrade step needed?
- [ ] **Catalog**: index or metadata column added/changed -> reindex required; estimate catalog size and time.
- [ ] **Registry / properties / portal_setup XML**.
- [ ] **External DB / RDBMS** (SQLAlchemy, z3c.saconfig): schema migrations.

## Security
- [ ] Permissions & roles (`rolemap.xml`, `permission=` in ZCML, `ClassSecurityInfo`, `declareProtected`).
- [ ] Untrusted input reaching `restrictedTraverse`, `eval`, SQL, shell, templates without escaping (`structure` keyword!).
- [ ] CSRF (plone.protect) for state-changing views.

## Compatibility
- [ ] Python 2/3 differences if the repo still supports both (bytes/str, `six`).
- [ ] Public API used by other packages (search all repos + `setup.py` `install_requires` dependants).
- [ ] i18n message ids changed -> translations.
- [ ] Buildout/pinned versions (`versions.cfg`, `constraints.txt`) needing bumps in sibling repos.

## Risk matrix
| | Low blast radius (1 module, covered by tests) | Wide (shared package, many callers) |
|---|---|---|
| **No data/security change** | low | medium |
| **Data, catalog, permission or API change** | medium | high |
