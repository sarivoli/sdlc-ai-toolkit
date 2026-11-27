"""Tests for the SDLC toolkit helper CLI and installer.

Run:  python -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDLC = ROOT / "scripts" / "sdlc.py"
sys.path.insert(0, str(ROOT / "scripts"))
os.environ["SDLC_TOOLKIT_HOME"] = str(ROOT)  # use config/ and templates/ from the repo
import sdlc  # noqa: E402


def run(*args, cwd=None, env=None, check=True):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run(list(args), cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise AssertionError(f"{args} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
    return p


def make_repo(path: Path, name: str, origin: Path):
    run("git", "init", "-q", "--bare", "-b", "main", str(origin / f"{name}.git"))
    repo = path / name
    run("git", "init", "-q", "-b", "main", str(repo))
    run("git", "-C", str(repo), "config", "user.email", "dev@example.com")
    run("git", "-C", str(repo), "config", "user.name", "Dev One")
    run("git", "-C", str(repo), "remote", "add", "origin", f"git@gitlab.com:acme/{name}.git")
    # push to a local bare repo but keep a gitlab-looking URL for link building
    run("git", "-C", str(repo), "config", "remote.origin.pushurl", str(origin / f"{name}.git"))
    run("git", "-C", str(repo), "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("")
    run("git", "-C", str(repo), "add", ".")
    run("git", "-C", str(repo), "commit", "-q", "-m", "chore(init): PROJ-1 initial commit")
    run("git", "-C", str(repo), "push", "-q", str(origin / f"{name}.git"), "main")
    run("git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


class TemplateTests(unittest.TestCase):
    def test_vars_each_if_and_guidance(self):
        tpl = "<!-- guidance: drop me -->\n# {{title}}\n{{#each repos}}- {{name}} ({{ticket}})\n{{/each}}{{#if empty}}X{{/if}}{{#if title}}Y{{/if}}"
        out, missing = sdlc.render_text(tpl, {"title": "T", "ticket": "PROJ-1", "repos": [{"name": "a"}, {"name": "b"}], "empty": ""})
        self.assertNotIn("guidance", out)
        self.assertIn("- a (PROJ-1)", out)
        self.assertIn("- b (PROJ-1)", out)
        self.assertIn("Y", out)
        self.assertNotIn("X", out)
        self.assertEqual(missing, set())

    def test_missing_reported(self):
        out, missing = sdlc.render_text("{{a}} {{b}}", {"a": 1})
        self.assertEqual(missing, {"b"})
        self.assertIn("—", out)

    def test_all_templates_parse(self):
        for t in (ROOT / "templates").glob("*.*"):
            if t.name == "README.md":
                continue
            sdlc.render_text(t.read_text(encoding="utf-8"), {})


class CommitRuleTests(unittest.TestCase):
    def setUp(self):
        self.cp = sdlc.load_config()

    def check(self, msg):
        return sdlc.check_commit_message(self.cp, msg)

    def test_good(self):
        self.assertEqual(self.check("fix(catalog): PROJ-12 reindex objects after rename\n\nBecause titles changed.\n\nRefs: PROJ-12"), [])

    def test_missing_key(self):
        self.assertTrue(self.check("fix(catalog): reindex objects after rename\n\nwhy"))

    def test_fix_needs_body(self):
        errs = self.check("fix(catalog): PROJ-12 reindex objects after rename\n\nRefs: PROJ-12")
        self.assertTrue(any("body" in e for e in errs))

    def test_wrong_project(self):
        errs = self.check("docs(readme): OTHER-3 explain install steps")
        self.assertTrue(any("not in allowed" in e for e in errs))

    def test_merge_exempt(self):
        self.assertEqual(self.check("Merge branch 'main' into feat/x"), [])

    def test_protected(self):
        self.assertTrue(sdlc.protected(self.cp, "release/1.2"))
        self.assertFalse(sdlc.protected(self.cp, "fix/PROJ-1-x"))

    def test_work_journal(self):
        import datetime
        with tempfile.TemporaryDirectory() as d:
            jr = str(Path(d) / "w.jsonl")
            env = {"SDLC_JOURNAL": jr}
            run(sys.executable, str(SDLC), "log", "proj-1", "--activity", "impact", "--summary", "Traced callers",
                "--title", "Fix lookup", env=env)
            run(sys.executable, str(SDLC), "log", "proj-1", "--activity", "impact", "--summary", "Traced callers", env=env)
            run(sys.executable, str(SDLC), "log", "PROJ-2", "--activity", "bugfix", "--summary", "Fixed it", env=env)
            self.assertEqual(len(Path(jr).read_text().splitlines()), 2)
            bad = run(sys.executable, str(SDLC), "log", "PROJ-3", "--activity", "nonsense", "--summary", "x",
                      env=env, check=False)
            self.assertNotEqual(bad.returncode, 0)
            out = run(sys.executable, str(SDLC), "report", "--period", "year", "--by", "ticket", env=env).stdout
            self.assertIn("PROJ-1 - Fix lookup", out)
            self.assertIn("2 tickets", out)
        s, e = sdlc.period_range("week", datetime.date(2026, 11, 27))
        self.assertEqual((s, e), (datetime.date(2026, 11, 23), datetime.date(2026, 11, 29)))
        s, e = sdlc.period_range("last-month", datetime.date(2026, 1, 15))
        self.assertEqual((s, e), (datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)))

    def test_branch_convention(self):
        import argparse
        import contextlib
        import io

        def name(**kw):
            a = argparse.Namespace(key="JIVA70-1919", type="feature", title="", user="Kumar", poc=None)
            a.__dict__.update(kw)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sdlc.cmd_branch_name(self.cp, a)
            return buf.getvalue().strip()

        self.assertEqual(name(), "feature/kumar/JIVA70-1919")
        self.assertEqual(name(type="fix"), "bugfix/kumar/JIVA70-1919")
        self.assertEqual(name(type="spike", poc="py3", key="JIVA66-9988"), "spike/py3/JIVA66-9988")
        with self.assertRaises(RuntimeError):
            name(type="spike")

    def test_branch_name(self):
        self.assertEqual(sdlc.slugify("Fix: Catalog won't reindex!"), "fix-catalog-won-t-reindex")


class MultiRepoTests(unittest.TestCase):
    def test_collect_summary_quality_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ws, origin = tmp / "work", tmp / "origin"
            ws.mkdir(); origin.mkdir()
            a = make_repo(ws, "core.app", origin)
            b = make_repo(ws, "core.theme", origin)
            env = {"SDLC_WORKSPACE_ROOT": str(ws), "SDLC_TOOLKIT_HOME": str(ROOT)}
            py = sys.executable

            # hooks
            run(py, str(SDLC), "install-hooks", env=env)
            for repo in (a, b):
                self.assertTrue((repo / ".git" / "hooks" / "commit-msg").exists())
                run("git", "-C", str(repo), "switch", "-q", "-c", "fix/PROJ-7-title-reindex")

            # bad commit rejected by hook
            (a / "pkg" / "x.py").write_text("X = 1\n")
            run("git", "-C", str(a), "add", ".")
            bad = run("git", "-C", str(a), "commit", "-m", "quick fix", check=False)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("Commit rejected", bad.stderr)

            # good commits in two repos
            run("git", "-C", str(a), "commit", "-q", "-m", "fix(catalog): PROJ-7 reindex on title change\n\nTitles were stale.\n\nRefs: PROJ-7")
            (b / "pkg" / "y.py").write_text("Y = 2\n")
            run("git", "-C", str(b), "add", ".")
            run("git", "-C", str(b), "commit", "-q", "-m", "feat(viewlet): PROJ-7 show reindex status\n\nEditors need feedback.\n\nRefs: PROJ-7")
            (b / "pkg" / "z.py").write_text("Z = 3\n")
            run("git", "-C", str(b), "add", ".")
            run("git", "-C", str(b), "commit", "-q", "-m", "test(viewlet): PROJ-7 cover status viewlet")

            p = run(py, str(SDLC), "collect", "PROJ-7", "--json", env=env)
            data = json.loads(p.stdout)
            self.assertEqual(data["repo_count"], 2)
            self.assertEqual(data["commit_count"], 3)
            names = {r["name"]: r for r in data["repos"]}
            self.assertEqual(names["core.theme"]["commit_count"], 2)
            self.assertEqual(names["core.app"]["web_url"], "https://gitlab.com/acme/core.app")
            self.assertFalse(names["core.app"]["pushed"])

            wd = ws / ".sdlc" / "PROJ-7"
            (wd / "narrative.json").write_text(json.dumps({"ticket_title": "Reindex on title change", "risk_level": "low"}))
            (wd / "mrs.json").write_text(json.dumps({"core.app": {"url": "https://gitlab.com/acme/core.app/-/merge_requests/5", "iid": 5}}))
            out = run(py, str(SDLC), "summary", "PROJ-7", env=env).stdout
            self.assertIn("fields not provided", out)
            summary = (wd / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Reindex on title change", summary)
            self.assertIn("[!5](https://gitlab.com/acme/core.app/-/merge_requests/5)", summary)
            self.assertIn("PROJ-7 show reindex status", summary)
            mr_theme = (wd / "mr-core.theme.md").read_text(encoding="utf-8")
            self.assertIn("merge_requests/5", mr_theme)  # sibling link
            self.assertIn("+2 / -0", mr_theme)

            # quality gate with simple, always-available commands
            local = tmp / "home"
            local.mkdir()
            (local / "toolkit.ini").write_text((ROOT / "config" / "toolkit.ini").read_text(encoding="utf-8"))
            (local / "templates").symlink_to(ROOT / "templates") if os.name != "nt" else None
            (local / "toolkit.local.ini").write_text(
                f"[quality]\nlint = {py} -m py_compile {{files}}\nformat_check =\nsecurity =\ntests = {py} -c pass\nrequired = lint, tests\n")
            env_q = dict(env, SDLC_TOOLKIT_HOME=str(local))
            if os.name != "nt":
                q = run(py, str(SDLC), "quality", "PROJ-7", env=env_q)
                self.assertIn("PASS", q.stdout)
                (b / "pkg" / "broken.py").write_text("def (:\n")
                q = run(py, str(SDLC), "quality", "PROJ-7", "--repo", str(b), env=env_q, check=False)
                self.assertEqual(q.returncode, 1)
                rep = json.loads((wd / "quality.json").read_text())
                self.assertEqual(rep["result"], "FAIL")


class MultiEditorTests(unittest.TestCase):
    def test_targets_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp)
            (h / ".codex").mkdir()
            (h / ".codex" / "config.toml").write_text('model = "x"\n[mcp_servers.mine]\nurl = "https://m"\n')
            env = {"HOME": tmp, "USERPROFILE": tmp, "COPILOT_HOME": str(h / ".copilot"), "XDG_CONFIG_HOME": str(h / ".config")}
            cmd = [sys.executable, str(ROOT / "install.py"), "--no-hooks", "--set", "orbit.enabled=no", "--target", "claude,cursor,antigravity,gemini,codex"]
            run(*cmd, env=env)
            run(*cmd, env=env)  # idempotent
            self.assertTrue((h / ".claude/agents/sdlc-orchestrator.md").exists())
            self.assertNotIn("@@SDLC@@", (h / ".claude/agents/sdlc-orchestrator.md").read_text(encoding="utf-8"))
            self.assertTrue((h / ".cursor/skills/impact-analysis/SKILL.md").exists())
            self.assertTrue((h / ".gemini/config/agents/sdlc-orchestrator.md").exists())
            self.assertTrue((h / ".codex/skills/sdlc-orchestrator/SKILL.md").exists())  # agent as skill
            self.assertIn("serverUrl", (h / ".gemini/config/mcp_config.json").read_text())
            self.assertIn("httpUrl", (h / ".gemini/settings.json").read_text())
            toml = (h / ".codex/config.toml").read_text()
            self.assertEqual(toml.count("# >>> sdlc-ai-toolkit mcp >>>"), 1)
            self.assertIn("[mcp_servers.mine]", toml)
            run(*cmd[:2], "--uninstall", env=env)
            self.assertFalse((h / ".claude/agents/sdlc-orchestrator.md").exists())
            self.assertFalse((h / ".codex/skills/sdlc-orchestrator").exists())
            self.assertEqual((h / ".codex/config.toml").read_text().strip().count("sdlc-ai-toolkit"), 0)
            self.assertIn("[mcp_servers.mine]", (h / ".codex/config.toml").read_text())


class InstallerTests(unittest.TestCase):
    def test_install_upgrade_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".copilot"
            ws = Path(tmp) / "work"
            ws.mkdir()
            # a pre-existing user MCP config and a user's own skill with a clashing name
            home.mkdir()
            (home / "mcp-config.json").write_text(json.dumps({"mcpServers": {"context7": {"type": "http", "url": "https://x"}}}))
            (home / "skills" / "refactor").mkdir(parents=True)
            (home / "skills" / "refactor" / "SKILL.md").write_text("---\nname: refactor\ndescription: mine\n---\n")
            env = {"COPILOT_HOME": str(home)}
            p = run(sys.executable, str(ROOT / "install.py"), "--target", "copilot", "--workspace", str(ws),
                    "--set", "jira.site=https://acme.atlassian.net", "--set", "gitlab.group=acme", env=env)
            self.assertIn("ACTION REQUIRED", p.stdout)
            agents = sorted(x.name for x in (home / "agents").glob("*.agent.md"))
            self.assertIn("sdlc-orchestrator.agent.md", agents)
            self.assertIn("debug.agent.md", agents)
            orch = (home / "agents" / "sdlc-orchestrator.agent.md").read_text(encoding="utf-8")
            self.assertNotIn("@@SDLC@@", orch)
            self.assertIn("sdlc-toolkit/scripts/sdlc.py", orch)
            self.assertTrue(orch.startswith("---\nname: SDLC Orchestrator"))
            self.assertIn("mine", (home / "skills" / "refactor" / "SKILL.md").read_text())  # user's skill kept
            for s in ("jira-ticket-digest", "git-commit", "security-review"):
                self.assertTrue((home / "skills" / s / "SKILL.md").exists(), s)
            mcp = json.loads((home / "mcp-config.json").read_text())["mcpServers"]
            self.assertEqual(set(mcp), {"context7", "atlassian", "gitlab", "gitlab-orbit"})
            self.assertTrue((home / "sdlc-toolkit" / "MANUAL_STEPS.md").exists())
            self.assertNotIn("still placeholders", (home / "sdlc-toolkit" / "MANUAL_STEPS.md").read_text(encoding="utf-8"))
            # helper works from the installed location
            run(sys.executable, str(home / "sdlc-toolkit" / "scripts" / "sdlc.py"), "template", "mr-description.md",
                env={"SDLC_TOOLKIT_HOME": str(home / "sdlc-toolkit")})
            # skill names match folder names (required by VS Code)
            for sk in (home / "skills").iterdir():
                text = (sk / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(f"name: {sk.name}", text, sk)
            # re-run (upgrade) is idempotent
            run(sys.executable, str(ROOT / "install.py"), "--target", "copilot", "--workspace", str(ws), env=env)
            # uninstall
            run(sys.executable, str(ROOT / "install.py"), "--uninstall", env=env)
            self.assertFalse((home / "agents" / "sdlc-orchestrator.agent.md").exists())
            self.assertEqual(set(json.loads((home / "mcp-config.json").read_text())["mcpServers"]), {"context7"})
            self.assertTrue((home / "skills" / "refactor" / "SKILL.md").exists())
            self.assertTrue((home / "sdlc-toolkit" / "toolkit.local.ini").exists())


if __name__ == "__main__":
    unittest.main()
