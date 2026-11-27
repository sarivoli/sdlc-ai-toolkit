---
description: Install or upgrade the SDLC AI Toolkit on this machine and list the manual steps
agent: agent
---
Install the SDLC AI Toolkit from this repository for me.

1. Ask me (in one question) for anything you need that I haven't told you: my Jira site URL, Jira project keys, GitLab group, and the folder that contains my repos. If I say "use the defaults", skip this.
2. Ask which AI editors I use (default: auto-detect; `--target all` for every supported one: copilot, claude, cursor, antigravity, gemini, codex). Run the installer from the repo root with the right Python for my OS (`python3 install.py` on macOS/Linux, `py -3 install.py` on Windows), passing `--set` / `--workspace` for the values I gave.
3. Show me the "ACTION REQUIRED - manual steps" list exactly as printed, numbered.
4. Run the helper's `doctor` command that the installer printed and summarise anything still marked ⚠.
