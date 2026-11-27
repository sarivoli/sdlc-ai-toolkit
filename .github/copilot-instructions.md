# Instructions for AI coding agents working in this repository

This repository is the **SDLC AI Toolkit**: agents, skills, templates and
a helper CLI that a developer installs into their own GitHub Copilot setup.

## If the user asks to install, set up, upgrade or "make this available"

1. Run the installer from the repository root:
   - macOS/Linux: `python3 install.py`
   - Windows: `py -3 install.py` (or `python install.py`)
   If the user told you their Jira site, project keys, GitLab group or the
   folder that holds their repos, pass them:
   `python3 install.py --set jira.site=https://<site>.atlassian.net --set jira.project_keys=PROJ --set gitlab.group=<group> --workspace <folder>`
2. Do not edit files in `~/.copilot` by hand; the installer owns them.
3. When it finishes, show the user the **"ACTION REQUIRED - manual steps"**
   section of the output verbatim as a numbered list, and tell them the same
   report is saved at `~/.copilot/sdlc-toolkit/MANUAL_STEPS.md`.
4. Offer to open `docs/USER_MANUAL.md`.

## If the user asks to uninstall
Run `python3 install.py --uninstall` (Windows: `py -3 install.py --uninstall`).

## If the user asks to change the workflow
- Output formats -> edit files in `templates/` (see `templates/README.md`).
- Team rules (commit format, Jira update frequency, quality commands) -> `config/toolkit.ini`.
- Coding standards -> `skills/zope-python-standards/references/standards.md`.
- Agent behaviour -> `agents/*.agent.md`; procedures -> `skills/*/SKILL.md`.
- Keep `@@SDLC@@` placeholders as they are: the installer replaces them.
- Run `python3 -m unittest discover -s tests` after changes.
- Ask the user to re-run the installer to apply changes.
