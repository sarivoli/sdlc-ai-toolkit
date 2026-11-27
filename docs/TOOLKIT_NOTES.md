# SDLC AI Toolkit - maintainer notes (reference)

Reviewed 2026-11-27 against v1.0.0. 12 unit tests pass
(`python3 -m unittest discover -s tests`). Not yet installed on this machine
(`~/.copilot/{agents,skills,sdlc-toolkit}` absent).

## What it is
A user-level Copilot (VS Code) add-on for Python/Zope teams using Jira Cloud + GitLab.
Give the **SDLC Orchestrator** agent a ticket key; it runs:
understand -> impact + plan -> **[approve]** -> implement -> quality gate ->
**[review diff]** -> atomic commits per repo -> consolidated summary -> push + GitLab MRs
-> Jira comment/transition -> Teams text. Stdlib-only Python 3.8+.

## Architecture
| Piece | Location | Notes |
|-------|----------|-------|
| Installer | `install.py` | Copies to `~/.copilot/{agents,skills,sdlc-toolkit}`, merges MCP servers into `~/.copilot/mcp-config.json`, installs git hooks, writes `MANUAL_STEPS.md`. Ownership tracked in `~/.copilot/sdlc-toolkit/manifest.json` + `.sdlc-toolkit` marker; never overwrites foreign files. Flags: `--dry-run --uninstall --set sec.key=val --workspace --no-hooks`. |
| Helper CLI | `scripts/sdlc.py` | Deterministic: `config template repos workdir branch-name check-branch check-commit quality collect summary render install-hooks doctor`. Own mini template engine (`{{x}}`, `{{#each}}`, `{{#if}}`, `<!-- guidance -->` stripped). |
| Agents (6) | `agents/*.agent.md` | Orchestrator (handoffs + subagents) -> Ticket Analyst, Impact Analyst, Implementer, Quality Gate, Release Scribe. Reuse vendored `Debug`, `Critical thinking`, `SE: Security`. |
| Skills (10) | `skills/*/SKILL.md` | `sdlc-conventions` (loaded first; safety rules; per-ticket folder), jira-ticket-digest, impact-analysis (+zope checklist), implementation-plan, quality-gate, commit-discipline, multi-repo-summary, gitlab-mr-publisher, jira-progress-update, zope-python-standards. |
| Templates (9) | `templates/` | Every outbound text is rendered from these. Override precedence: repo `.sdlc/templates` > workspace `.sdlc/templates` > installed default. |
| Config | `config/toolkit.ini` | Team defaults; personal overrides in `~/.copilot/sdlc-toolkit/toolkit.local.ini` (written by `--set`/`--workspace`). |
| Vendor | `vendor/awesome-copilot/` | MIT, pinned; refresh via `scripts/update_vendor.py`. |
| Tests | `tests/test_toolkit.py` | |

`@@SDLC@@` / `@@TOOLKIT_HOME@@` in agents/skills are replaced at install time - keep them.
Per-ticket state: `<workspace>/.sdlc/<KEY>/` (understanding.md, impact.md, plan.md,
plan.approved, quality.json/md, commits.json, narrative.json, mrs.json, summary.md,
mr-<repo>.md, teams.md). Orchestrator resumes from existing files.

Safety: confirm before push / create_mr / jira_comment / jira_transition; never merge,
approve, force-push, or commit to protected branches; nothing outside an approved plan.

## Connectivity (current design)
- Atlassian Rovo MCP `https://mcp.atlassian.com/v1/mcp/authv2` and GitLab MCP
  `https://gitlab.com/api/v4/mcp`, both OAuth in browser, server names `atlassian` / `gitlab`
  (agents reference tools as `atlassian/*`, `gitlab/*`).
- Manual steps: VS Code `MCP: List Servers` -> start + sign in each; reload window;
  org policy must allow MCP (Business/Enterprise); `ruff`/`bandit` optional.
- Fallback GitLab: `@zereight/mcp-gitlab` with PAT (documented in USER_MANUAL).

## Fine-tuning backlog (findings from review)
Connectivity
1. **mcp-config.json key mismatch risk**: installer writes `mcpServers` to `~/.copilot/mcp-config.json`
   (Copilot CLI format); VS Code reads `servers` from its profile `mcp.json`. Default
   `write_vscode_profile_mcp = no`, so in VS Code the servers may not appear. Consider default `yes`
   and verify.
2. **Verify endpoints**: Atlassian URL ends in `/authv2` (current public docs use `/v1/mcp`);
   GitLab MCP needs a recent GitLab version/feature flag and for self-managed a different host.
   Confirm both against current docs before rollout.
3. `doctor` only checks that servers exist in the JSON, not that they are reachable/authenticated.
   `check_config` only flags `jira.site` / `gitlab.group` placeholders (not `jira.project_keys`,
   `gitlab.url`, transition names).
4. Verify VS Code actually discovers user-level `~/.copilot/agents` and `~/.copilot/skills` on the
   target VS Code version (else document `chat.agentFilesLocations` / `chat.agentSkillsLocations`).
5. Jira transition names (`In Progress`, `In Review`) are guesses; real workflow names must be set.

Templates
6. `templates/README.md` references nonexistent `scripts/sdlc_summary.py` (should be `scripts/sdlc.py summary`).
7. `USER_MANUAL.md` duplicated at repo root and `docs/` (identical; installer reads `docs/`). Drop one.
8. Templates are generic: no Zope-specific MR checklist beyond a few lines, no changelog/CHANGES.rst
   entry step, no QA hand-off or release-note template, commit scope list is example-only.
9. `consolidated-summary.md`/`teams-update.md` placeholders need `narrative.json` keys; document the
   exact key list per template (currently implicit in `sdlc.py summary`).

Process
10. Decide team values: Jira site/project keys, GitLab group/url, default branches, quality commands,
    zope_flavor, python_version, workspace root.

## Orbit integration
`[orbit]` in toolkit.ini; `sdlc.py orbit` wraps the CLI with
`ORBIT_DATA_DIR=<workspace>/.sdlc/orbit` (per-workspace isolation). Installer
`install_orbit` installs via npm (also finds npm's global bin when not on PATH),
auto-indexes, and adds the `gitlab-orbit` http MCP. Used by the impact-analysis
skill step 0 and the full-stack checklist. See USER_MANUAL section 15.

## Change workflow
Edit templates / `config/toolkit.ini` / agents / skills -> `python3 -m unittest discover -s tests`
-> re-run `python3 install.py` to apply.
