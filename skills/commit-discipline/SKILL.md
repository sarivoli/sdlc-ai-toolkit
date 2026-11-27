---
name: commit-discipline
description: Create disciplined, atomic commits for a Jira ticket in every changed repo - team commit format with the ticket key, one logical change per commit, never on protected branches, validated before committing. Builds on the git-commit skill. Use whenever committing work for a ticket.
argument-hint: PROJ-123
---

# Commit discipline

Load `sdlc-conventions`. Use the `git-commit` skill for staging and message
mechanics, with these team rules on top (team rules win on conflict):

1. **Gate first.** Do not commit unless `<workdir>/quality.json` exists with
   `"result": "PASS"` and is newer than the last file change. Otherwise run
   the `quality-gate` skill.
2. **Branch.** In each repo, check `@@SDLC@@ check-branch --repo <path>`. Stay
   on the repo's current branch when `[git] branch_mode = current`. If it is
   protected (or mode is `new`), ask before creating the plan's branch
   (`git switch -c <branch>`). Never commit to protected branches.
3. **Atomic commits.** Follow "Planned commits" in plan.md. Group hunks per
   logical change (`git add -p` style); tests travel with their code. No
   unrelated formatting in feature commits.
4. **Message.** Build it from `@@SDLC@@ template commit-message.txt`, then
   validate: `@@SDLC@@ check-commit --message "<full message>"`. Fix until it
   passes. Body explains WHY; `Refs: <KEY>` footer always present.
5. **Commit** (`git commit -F <tempfile>` to keep formatting). The repo's
   commit-msg hook validates again - if it rejects, fix the message; never
   use `--no-verify`.
6. **No push here.** Pushing belongs to `gitlab-mr-publisher` and needs
   confirmation.
7. When all repos are done, run `@@SDLC@@ collect <KEY>` and show the
   result so the developer sees every commit across repos.
