---
name: zope-python-standards
description: The team's Python and Zope coding standards - style, typing, ZCML, page templates, ZODB persistence, security, tests, logging. Use whenever writing, reviewing or refactoring Python/Zope code, and as the review checklist in the quality gate.
---

# Python & Zope coding standards

Read the team settings first: `@@SDLC@@ config` (see `[quality] zope_flavor`
and `python_version`). Then apply [the standards](./references/standards.md).

When writing code:
- Match the existing style of the file you are editing over any generic rule.
- Prefer the smallest change that satisfies the plan.
- Every behaviour change gets a test in the repo's existing test style
  (zope.testrunner layers / `plone.app.testing` / pytest - don't mix).
- Use the `refactor` skill only for refactors the plan includes.

When reviewing: go through the checklist section of the standards file and
report each finding as `path:line - rule - suggestion`.
