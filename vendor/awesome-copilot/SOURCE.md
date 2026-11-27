# Vendored from github/awesome-copilot

These files are copied unchanged from <https://github.com/github/awesome-copilot>
at commit `93fc8b9ee3ef56b9b5e7261e6ce92d314cb2c1cf` under the MIT license (see `LICENSE`).

They are vendored (not downloaded at install time) so the installer works behind
corporate proxies and so every developer gets the same, reviewed version.

| Type  | Name | Used by our workflow for |
|-------|------|--------------------------|
| skill | `git-commit` | Staging and writing Conventional Commits (wrapped by our `commit-discipline` skill, which adds the Jira-key rules) |
| skill | `security-review` | Reasoning-based security review during the quality gate |
| skill | `pytest-coverage` | Raising coverage when the repo uses pytest |
| skill | `refactor` | Safe, behaviour-preserving refactors during implementation |
| skill | `acquire-codebase-knowledge` | First-time mapping of an unfamiliar repo before impact analysis |
| agent | `Debug Mode Instructions` (`debug.agent.md`) | Root-causing bugs before fixing |
| agent | `SE: Security` (`se-security-reviewer.agent.md`) | Deep security review of risky changes |
| agent | `Critical thinking mode instructions` (`critical-thinking.agent.md`) | Challenging an implementation plan before approval |

To refresh them, run `python scripts/update_vendor.py --ref <commit-or-branch>`,
review the diff, and commit it through a normal MR.
