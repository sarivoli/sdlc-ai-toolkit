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
| Agent UI | `scripts/sdlc_ui_mcp.py`, `scripts/a2ui.py`, `scripts/ui/sdlc-ui.html` (built from `ui/`) | Local stdio MCP server `sdlc-ui`: A2UI v1.0 panels as an MCP App (`ui://sdlc/app`). See *Agent UI panels* below. |
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
auto-indexes, and registers `gitlab-orbit` per `[orbit] mcp_mode`:
`local` (default) = `scripts/orbit_mcp.py`, a stdlib stdio MCP server wrapping the
CLI (orbit 1.9.x has no MCP server; `orbit query`/`status` call GitLab, so they are
not exposed and GitLab kinds like `mr:` are refused); `remote` = hosted http
endpoint; `off`. Editor shapes live in `installer_targets.shape_server`; configs
carry no workspace path or `${...}` variable (Copilot rejects unresolved ones),
the server resolves it: --workspace > client roots (`roots/list`) >
$WORKSPACE_FOLDER/$PWD > cwd, never auto-indexing $HOME or `/`. Old hosted or
earlier local `gitlab-orbit` entries are migrated (`is_orbit_legacy`).
`orbit setup` is not run: it adds hooks to ~/.claude/settings.json and uses the
shared ~/.gitlab/orbit graph. Used by the impact-analysis skill step 0 and the
full-stack checklist. See USER_MANUAL section 15.

## Post-install checklist and Orbit gate
`sdlc.py checklist` / `preflight` (functions `orbit_state`, `git_auth_state`,
`jira_auth_state` in `scripts/sdlc.py`). The installer runs `checklist --json`
at the end (`post_install_checklist`), prints it and writes it at the top of
MANUAL_STEPS.md; `--no-auth-checks`, `--dry-run` or `SDLC_CHECKS_OFFLINE=1`
skip the network checks. Git: one `git ls-remote` per remote host with
`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, empty askpass, SSH
`BatchMode` (unless the user set their own ssh command), 15 s timeout; URL
credentials are masked. Jira: the MCP OAuth token lives in the editor and is
not readable, so the item is `[?]` unless `JIRA_API_TOKEN`+`JIRA_EMAIL` are
set (then `/rest/api/3/myself`, 8 s). `preflight` exits 3 when Orbit is
missing, the folder is unindexed / partially indexed / still indexing; every
ticket skill and agent runs it first and stops to ask (rule text in
`sdlc-conventions`). Not gated: `work-journal` (no code reading) and
`zope-python-standards`. The bash/PowerShell bootstraps just exec install.py,
so there is one implementation for all OSes.
Ideas: detect the Atlassian MCP sign-in per editor where the token store is
documented; let `orbit_mcp.py`'s `orbit_status` reuse `orbit_state`.

## Hook inventory
`sdlc.py hooks` (`git_hook_inventory`, `editor_hook_inventory`): toolkit git hooks in
workspace repos + repos in manifest `hooks`, a global `core.hooksPath`, and Claude /
Gemini / Cursor hook entries that mention the toolkit or Orbit. `install-hooks` prints
`[sdlc] hook <installed|updated|unchanged|foreign> <name> <path>`; the installer
(`hooks_report`) overlays those on the inventory and prints / saves it on every run.
`--no-hooks` now keeps the manifest's hooked repos (before, uninstall forgot them).

## Work journal
`[journal]` in toolkit.ini; `sdlc.py log|worklog|report` read/write an append-only
JSONL at `~/.copilot/sdlc-journal/worklog.jsonl` (outside the toolkit home so it survives
uninstall; `SDLC_JOURNAL` env overrides). Agents log via the `work-journal` skill; the
`SDLC Work Journal` agent produces reports. See USER_MANUAL section 16.

## Agent UI panels (A2UI as an MCP App)
- **Why MCP Apps:** no editor renders A2UI natively. MCP Apps (`ui://` HTML
  resources shown in a sandboxed iframe) are supported by VS Code Copilot Chat
  and Cursor, so the server ships its own renderer: `ui/` (Vite + `@a2ui/lit`
  0.16 + `@a2ui/web_core` + `@modelcontextprotocol/ext-apps`) builds one
  self-contained `scripts/ui/sdlc-ui.html` (about 0.9 MB, inlined JS/CSS),
  committed so that users need no Node.js. `scripts/ui/sdlc-ui.json` records
  the versions and SHA-256; the installer and a test check it.
- **Server:** `scripts/sdlc_ui_mcp.py`, stdlib only. Model-facing tools
  `sdlc_ui_confirm`, `sdlc_ui_summary`, `sdlc_ui_plan`, `sdlc_ui_quality`,
  `sdlc_ui_ticket`, `sdlc_ui_install_preview`, `sdlc_ui_install_report`,
  `sdlc_ui_checklist`; app-only `sdlc_ui_checklist_refresh`. Each returns a
  short text for the model plus an `application/a2ui+json` resource
  (`createSurface` with inline components and data model) built by
  `scripts/a2ui.py` from basic-catalog components only.
- **Who gets tools:** `[ui] mode = auto` lists tools only when the client
  declares the `io.modelcontextprotocol/ui` extension or is a known MCP Apps
  host (VS Code, Cursor, ...); terminal CLIs get none and keep text.
- **Buttons:** `sdlc.chat` actions send a reply into the chat (`ui/message`),
  `sdlc.open` opens an http(s) link, other names call app-only tools. No
  panel action approves, pushes or writes: consent stays a chat message.
- **Icons:** sent as Material SVG paths (`Icon {svgPath}`) because the iframe
  CSP blocks icon fonts.
- **Install report:** `install.py` writes `install-report.json` next to
  `MANUAL_STEPS.md`; `--report-json FILE` writes it also in a dry run, which
  `sdlc_ui_install_preview` uses.
- **Rebuild the panel:** `cd ui && npm ci && npm run build` (writes
  `scripts/ui/sdlc-ui.*`). Bump `@a2ui/*` versions in `ui/package.json`.
- **Limits:** the A2UI basic catalog has no table, so tables are rows of
  icon, label and status; colours come from the host theme, not per status.

## Change workflow
Edit templates / `config/toolkit.ini` / agents / skills -> `python3 -m unittest discover -s tests`
-> re-run `python3 install.py` to apply.
- Multi-editor install: `installer_targets.py` (per-editor paths, agent conversion, MCP shapes); `install.sh`/`install.ps1` bootstrap from the public URL; test `MultiEditorTests`.
