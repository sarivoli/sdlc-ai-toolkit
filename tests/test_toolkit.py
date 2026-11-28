"""Tests for the SDLC toolkit helper CLI and installer.

Run:  python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDLC = ROOT / "scripts" / "sdlc.py"
sys.path.insert(0, str(ROOT / "scripts"))
os.environ["SDLC_TOOLKIT_HOME"] = str(ROOT)  # use config/ and templates/ from the repo
os.environ["SDLC_CHECKS_OFFLINE"] = "1"  # installer runs: no network checks in the post-install checklist
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
            self.assertEqual(set(mcp), {"context7", "atlassian", "gitlab", "gitlab-orbit", "sdlc-ui"})
            self.assertTrue((home / "sdlc-toolkit" / "MANUAL_STEPS.md").exists())
            steps_md = (home / "sdlc-toolkit" / "MANUAL_STEPS.md").read_text(encoding="utf-8")
            self.assertNotIn("still placeholders", steps_md)
            # post-install checklist: printed and saved, Orbit first and mandatory
            self.assertIn("POST-INSTALL CHECKLIST", p.stdout)
            self.assertIn("## Post-install checklist", steps_md)
            for title in ("Orbit code index (MANDATORY", "Git authentication", "Jira authentication"):
                self.assertIn(title, steps_md)
            self.assertLess(steps_md.index("Orbit code index"), steps_md.index("Git authentication"))
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


FAKE_ORBIT = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["workspace", "list"]:
    print("[]")
else:
    print(json.dumps({"args": a, "cwd": os.getcwd(), "data": os.environ.get("ORBIT_DATA_DIR"),
                      "no_gitlab": os.environ.get("ORBIT_NO_GITLAB"), "token": os.environ.get("GITLAB_TOKEN")}))
"""


def fake_orbit_bin(tmp: Path) -> Path:
    b = tmp / "bin"
    b.mkdir()
    (b / "orbit").write_text(FAKE_ORBIT)
    (b / "orbit").chmod(0o755)
    return b


@unittest.skipIf(os.name == "nt", "fake orbit CLI is a POSIX script")
class OrbitMcpTests(unittest.TestCase):
    def rpc(self, messages, tmp: Path, ws: Path):
        env = dict(os.environ, PATH=f"{fake_orbit_bin(tmp)}{os.pathsep}{os.environ['PATH']}",
                   SDLC_TOOLKIT_HOME=str(ROOT), GITLAB_TOKEN="secret")
        lines = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "orbit_mcp.py"), "--workspace", str(ws), "--no-auto-index"],
                           input=lines, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return [json.loads(ln) for ln in p.stdout.splitlines()]

    def test_jsonrpc_and_tools(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ws = tmp / "ws"
            (ws / "repo1" / ".git").mkdir(parents=True)
            call = lambda i, name, args: {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                                          "params": {"name": name, "arguments": args}}
            out = self.rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "bogus"},
                "not json",
                call(4, "orbit_grep", {"query": "mr:rate limit"}),
                call(5, "orbit_context", {"targets": ["https://gitlab.com/g/p/-/merge_requests/1"]}),
                call(6, "orbit_grep", {"query": "hello", "word": True}),
                call(7, "orbit_status", {}),
                {"jsonrpc": "2.0", "id": 8, "method": "ping"},
            ], tmp, ws)
            by_id = {m.get("id"): m for m in out}
            self.assertEqual(len(out), 9)  # the notification gets no reply
            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-03-26")
            self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "gitlab-orbit")
            self.assertEqual({t["name"] for t in by_id[2]["result"]["tools"]},
                             {"orbit_status", "orbit_index", "orbit_grep", "orbit_context", "orbit_sql", "orbit_schema"})
            self.assertEqual(by_id[3]["error"]["code"], -32601)
            self.assertEqual(by_id[None]["error"]["code"], -32700)
            for i in (4, 5):
                self.assertTrue(by_id[i]["result"]["isError"])
                self.assertIn("local only", by_id[i]["result"]["content"][0]["text"])
            g = by_id[6]["result"]
            self.assertFalse(g["isError"])
            sent = json.loads(g["content"][0]["text"])
            self.assertEqual(sent["args"][:2], ["grep", "-w"])
            self.assertIn(str(ws / "repo1"), sent["args"])
            self.assertEqual(sent["args"][-1], "hello")
            self.assertEqual(sent["data"], str(ws / ".sdlc" / "orbit"))
            self.assertEqual(sent["no_gitlab"], "1")
            self.assertIsNone(sent["token"])  # GitLab credentials never reach the CLI
            self.assertIn("Nothing indexed yet", by_id[7]["result"]["content"][0]["text"])
            self.assertEqual(by_id[8]["result"], {})


@unittest.skipIf(os.name == "nt", "fake orbit CLI is a POSIX script")
class OrbitWorkspaceTests(unittest.TestCase):
    """How orbit_mcp.py finds the workspace folder: client roots, cwd, home guard."""

    def start(self, tmp: Path, *args, cwd=None, env=None):
        e = dict(os.environ, PATH=f"{fake_orbit_bin(tmp)}{os.pathsep}{os.environ['PATH']}", SDLC_TOOLKIT_HOME=str(ROOT),
                 SDLC_ORBIT_MCP_ROOTS_WAIT="3", **(env or {}))
        e.pop("WORKSPACE_FOLDER", None)
        return subprocess.Popen([sys.executable, str(ROOT / "scripts" / "orbit_mcp.py"), "--no-auto-index", *args],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                cwd=str(cwd or tmp), env=e)

    @staticmethod
    def send(p, obj):
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()

    @staticmethod
    def recv(p):
        return json.loads(p.stdout.readline())

    def status(self, p, i=9):
        self.send(p, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "orbit_status", "arguments": {}}})
        m = self.recv(p)
        self.assertEqual(m["id"], i)
        return m["result"]["content"][0]["text"]

    def finish(self, p):
        p.stdin.close()
        self.assertEqual(p.wait(timeout=30), 0)
        p.stdout.close()

    def test_client_roots(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ws, other = tmp / "project", tmp / "other"
            (ws / ".git").mkdir(parents=True)
            (other / ".git").mkdir(parents=True)
            p = self.start(tmp, cwd=other)
            self.send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {"roots": {"listChanged": True}}}})
            self.assertEqual(self.recv(p)["id"], 1)
            self.send(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            # a tool call before the roots answer waits for it
            self.send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "orbit_status", "arguments": {}}})
            req = self.recv(p)
            self.assertEqual(req["method"], "roots/list")
            self.send(p, {"jsonrpc": "2.0", "id": req["id"], "result": {"roots": [{"uri": ws.as_uri(), "name": "project"}]}})
            m = self.recv(p)
            self.assertEqual(m["id"], 2)
            self.assertIn(f"Workspace folder: {ws.resolve()}", m["result"]["content"][0]["text"])
            self.assertTrue((ws / ".sdlc" / "orbit").is_dir())
            # the editor switches folders
            self.send(p, {"jsonrpc": "2.0", "method": "notifications/roots/list_changed"})
            req = self.recv(p)
            self.assertEqual(req["method"], "roots/list")
            self.send(p, {"jsonrpc": "2.0", "id": req["id"], "result": {"roots": [{"uri": other.as_uri()}]}})
            self.assertIn(f"Workspace folder: {other.resolve()}", self.status(p))
            self.finish(p)

    def test_cwd_fallback_without_roots(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ws = tmp / "project"
            (ws / ".git").mkdir(parents=True)
            p = self.start(tmp, cwd=ws, env={"PWD": str(tmp)})  # a stale $PWD from the parent is ignored
            self.send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}})
            self.recv(p)
            self.send(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            self.assertIn(f"Workspace folder: {ws.resolve()}", self.status(p))
            self.finish(p)

    def test_home_dir_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            home = tmp / "home"
            (home / "repo" / ".git").mkdir(parents=True)
            p = self.start(tmp, "--workspace", str(home), env={"HOME": str(home), "USERPROFILE": str(home)})
            self.send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.recv(p)
            self.assertIn("home directory", self.status(p))
            self.send(p, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "orbit_index", "arguments": {}}})
            m = self.recv(p)
            self.assertTrue(m["result"]["isError"])
            self.assertIn("refusing to index", m["result"]["content"][0]["text"])
            self.finish(p)
            self.assertFalse((home / ".sdlc").exists())


@unittest.skipIf(os.name == "nt", "fake orbit CLI is a POSIX script")
class OrbitMigrationTests(unittest.TestCase):
    def test_cloud_entry_replaced_others_kept(self):
        with tempfile.TemporaryDirectory() as t:
            h = Path(t)
            cloud = {"type": "http", "url": "https://gitlab.com/api/v4/orbit/mcp"}
            mine_atl = {"type": "http", "url": "https://my-proxy/atlassian"}
            custom = {"type": "stdio", "command": "foo"}
            vs = h / ".config" / "Code" / "User"
            vs.mkdir(parents=True)
            (vs / "mcp.json").write_text(json.dumps({"servers": {"gitlab-orbit": cloud, "atlassian": mine_atl, "mine": custom}}))
            (h / ".claude").mkdir()
            (h / ".claude.json").write_text(json.dumps({"mcpServers": {"gitlab-orbit": cloud, "mine": custom}}))
            (h / ".codex").mkdir()
            env = {"HOME": t, "USERPROFILE": t, "COPILOT_HOME": str(h / ".copilot"), "XDG_CONFIG_HOME": str(h / ".config"),
                   "PATH": f"{fake_orbit_bin(h)}{os.pathsep}{os.environ['PATH']}"}
            cmd = [sys.executable, str(ROOT / "install.py"), "--no-hooks", "--set", "orbit.auto_index=no",
                   "--target", "copilot,claude,cursor,codex"]
            run(*cmd, env=env)
            script = str(h / ".copilot" / "sdlc-toolkit" / "scripts" / "orbit_mcp.py")
            vsj = json.loads((vs / "mcp.json").read_text())["servers"]
            self.assertEqual(vsj["gitlab-orbit"], {"type": "stdio", "command": sys.executable, "args": [script]})
            self.assertEqual(vsj["atlassian"], mine_atl)  # user's own settings kept
            self.assertEqual(vsj["mine"], custom)
            self.assertIn("gitlab", vsj)
            cl = json.loads((h / ".claude.json").read_text())["mcpServers"]
            self.assertEqual(cl["gitlab-orbit"], {"type": "stdio", "command": sys.executable, "args": [script]})
            self.assertEqual(cl["mine"], custom)
            cli = json.loads((h / ".copilot" / "mcp-config.json").read_text())["mcpServers"]
            self.assertEqual(cli["gitlab-orbit"]["type"], "local")
            self.assertEqual(cli["gitlab-orbit"]["args"], [script])
            cur = json.loads((h / ".cursor" / "mcp.json").read_text())["mcpServers"]
            self.assertEqual(cur["gitlab-orbit"]["args"], [script])
            toml = (h / ".codex" / "config.toml").read_text()
            self.assertIn('[mcp_servers."gitlab-orbit"]', toml)
            self.assertIn(f"args = {json.dumps([script])}", toml)
            self.assertNotIn("api/v4/orbit/mcp", (vs / "mcp.json").read_text() + toml + (h / ".claude.json").read_text())
            before = {p: p.read_text() for p in (vs / "mcp.json", h / ".claude.json", h / ".codex" / "config.toml")}
            run(*cmd, env=env)  # idempotent
            for p, text in before.items():
                self.assertEqual(json.loads(text) if p.suffix == ".json" else text,
                                 json.loads(p.read_text()) if p.suffix == ".json" else p.read_text(), p)
            # an earlier toolkit-written local entry (with an editor variable) is rewritten too
            for p in (vs / "mcp.json", h / ".claude.json"):
                d = json.loads(p.read_text())
                d["servers" if "servers" in d else "mcpServers"]["gitlab-orbit"] = {
                    "type": "stdio", "command": "/usr/bin/python3",
                    "args": ["/old/.copilot/sdlc-toolkit/scripts/orbit_mcp.py", "--workspace", "${workspaceFolder}"]}
                p.write_text(json.dumps(d))
            (h / ".copilot" / "sdlc-toolkit" / "manifest.json").unlink()  # even when we no longer own it
            run(*cmd, env=env)
            self.assertEqual(json.loads((vs / "mcp.json").read_text())["servers"]["gitlab-orbit"]["args"], [script])
            self.assertEqual(json.loads((h / ".claude.json").read_text())["mcpServers"]["gitlab-orbit"]["args"], [script])
            self.assertEqual(json.loads((vs / "mcp.json").read_text())["servers"]["mine"], custom)
            for p in (vs / "mcp.json", h / ".claude.json", h / ".copilot" / "mcp-config.json", h / ".cursor" / "mcp.json",
                      h / ".codex" / "config.toml"):
                self.assertNotIn("${", p.read_text(), p)
            # opt-in remote mode still writes the hosted endpoint
            run(*cmd, "--set", "orbit.mcp_mode=remote", env=env)
            self.assertEqual(json.loads((vs / "mcp.json").read_text())["servers"]["gitlab-orbit"], cloud)


if __name__ == "__main__":
    unittest.main()


FAKE_ORBIT_ROWS = """#!/usr/bin/env python3
import os, sys
if sys.argv[1:3] == ["workspace", "list"]:
    print(os.environ.get("FAKE_ROWS", "[]"))
"""


def git_init(path: Path) -> Path:
    run("git", "init", "-q", str(path))
    return path


class OrbitPreflightTests(unittest.TestCase):
    def setUp(self):
        self.cp = sdlc.load_config()

    def test_not_installed_stops_with_install_command(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(sdlc, "orbit_command", return_value=None):
            st = sdlc.orbit_state(self.cp, Path(t))
            self.assertFalse(st["ok"])
            self.assertEqual(st["state"], "not-installed")
            self.assertIn("npm install -g @gitlab/orbit", "\n".join(st["steps"]))
            self.assertIn("orbit index", "\n".join(st["steps"]))
            args = mock.Mock(folder=t, json=False)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(sdlc.cmd_preflight(self.cp, args), 3)
            self.assertIn("PREFLIGHT STOP", buf.getvalue())

    def test_disabled_passes(self):
        cp = sdlc.load_config()
        cp.set("orbit", "enabled", "no")
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(sdlc.orbit_state(cp, Path(t))["ok"])

    def test_home_dir_is_not_a_workspace(self):
        with mock.patch.object(sdlc, "orbit_command", return_value=["orbit"]):
            st = sdlc.orbit_state(self.cp, Path.home().resolve())
        self.assertEqual(st["state"], "no-folder")
        self.assertFalse(st["ok"])

    @unittest.skipIf(os.name == "nt", "fake orbit CLI is a POSIX script")
    def test_index_states_via_cli(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            b = tmp / "bin"
            b.mkdir()
            (b / "orbit").write_text(FAKE_ORBIT_ROWS)
            (b / "orbit").chmod(0o755)
            ws = tmp / "ws"
            r1 = git_init(ws / "r1")

            def pre(rows=None):
                env = {"PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "SDLC_TOOLKIT_HOME": str(ROOT)}
                if rows is not None:
                    env["FAKE_ROWS"] = json.dumps(rows)
                return run(sys.executable, str(SDLC), "preflight", "--folder", str(ws), env=env, check=False)

            p = pre()
            self.assertEqual(p.returncode, 3, p.stdout)
            self.assertIn("PREFLIGHT STOP", p.stdout)
            self.assertIn("not indexed", p.stdout)
            self.assertIn(f'orbit index --folder "{ws.resolve().as_posix()}"', p.stdout)
            self.assertFalse((ws / ".sdlc").exists())  # the check never creates the graph folder
            (ws / ".sdlc" / "orbit").mkdir(parents=True)
            (ws / ".sdlc" / "orbit" / "graph.db").write_text("x")
            ok = [{"repo_path": str(r1), "status": "indexed"}]
            p = pre(ok)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertIn("preflight OK", p.stdout)
            p = pre([{"repo_path": str(r1), "status": "indexing"}])
            self.assertEqual(p.returncode, 3)
            self.assertIn("still indexing", p.stdout)
            git_init(ws / "r2")
            p = pre(ok)
            self.assertEqual(p.returncode, 3)
            self.assertIn("r2", p.stdout)


class AuthCheckTests(unittest.TestCase):
    def setUp(self):
        self.cp = sdlc.load_config()

    def test_redact(self):
        self.assertEqual(sdlc.redact("fatal: https://bob:glpat-123@gitlab.com/x.git"), "fatal: https://***@gitlab.com/x.git")

    def test_remote_host(self):
        self.assertEqual(sdlc._remote_host("git@gitlab.com:acme/x.git"), ("ssh", "gitlab.com"))
        self.assertEqual(sdlc._remote_host("https://u:t@GitLab.example.com/acme/x.git"), ("https", "gitlab.example.com"))
        self.assertEqual(sdlc._remote_host("/srv/git/x.git"), ("file", ""))
        self.assertEqual(sdlc._remote_host("C:\\repos\\x.git"), ("file", ""))

    def test_git_ok_and_failure_without_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run("git", "init", "-q", "--bare", str(tmp / "origin.git"))
            ws = tmp / "ws"
            good = git_init(ws / "good")
            run("git", "-C", str(good), "remote", "add", "origin", str(tmp / "origin.git"))
            st = sdlc.git_auth_state(self.cp, ws, offline=False, timeout=10)
            self.assertTrue(st["ok"], st)
            bad = git_init(ws / "bad")
            run("git", "-C", str(bad), "remote", "add", "origin", "https://bob:s3cr3t-token@127.0.0.1:9/acme/x.git")
            st = sdlc.git_auth_state(self.cp, ws, offline=False, timeout=10)
            self.assertFalse(st["ok"])
            self.assertEqual(st["state"], "pending")
            self.assertNotIn("s3cr3t-token", json.dumps(st))
            self.assertIn("credential.helper", "\n".join(st["steps"]))
            self.assertEqual(sdlc.git_auth_state(self.cp, ws, offline=True)["state"], "unverified")

    def test_jira(self):
        cp = sdlc.load_config()
        self.assertEqual(sdlc.jira_auth_state(cp)["state"], "pending")  # placeholder site
        cp.set("jira", "site", "https://acme.atlassian.net")
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("JIRA_", "ATLASSIAN_"))}
        with mock.patch.dict(os.environ, clean, clear=True):
            st = sdlc.jira_auth_state(cp)
            self.assertEqual(st["state"], "unverified")
            self.assertIn("atlassian", "\n".join(st["steps"]))
        seen = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"displayName": "Dev One"}'

        def opener(req, timeout):
            seen["url"], seen["auth"], seen["timeout"] = req.full_url, req.get_header("Authorization"), timeout
            return Resp()

        env = dict(clean, JIRA_API_TOKEN="tok-SECRET", JIRA_EMAIL="dev@example.com")
        with mock.patch.dict(os.environ, env, clear=True):
            st = sdlc.jira_auth_state(cp, opener=opener)
            self.assertEqual(st["state"], "done")
            self.assertIn("Dev One", st["summary"])
            self.assertEqual(seen["url"], "https://acme.atlassian.net/rest/api/3/myself")
            self.assertTrue(seen["auth"].startswith("Basic "))
            self.assertLessEqual(seen["timeout"], 10)

            def refuse(req, timeout):
                import urllib.error
                raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

            st = sdlc.jira_auth_state(cp, opener=refuse)
            self.assertEqual(st["state"], "pending")
            self.assertIn("401", st["summary"])
            self.assertNotIn("tok-SECRET", json.dumps(st))

    def test_checklist_has_three_items_orbit_first(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(sdlc, "orbit_command", return_value=None):
            items = sdlc.checklist(self.cp, Path(t), offline=True)
        self.assertEqual([i["name"] for i in items], ["orbit", "git", "jira"])
        self.assertIn("MANDATORY", items[0]["title"])
        text = sdlc.render_checklist(items)
        self.assertIn("[ ] **Orbit code index", text)


class TicketWorkflowGateTests(unittest.TestCase):
    """Every ticket-driven skill and agent runs the Orbit preflight first."""
    GATED = ["skills/jira-ticket-digest/SKILL.md", "skills/impact-analysis/SKILL.md", "skills/implementation-plan/SKILL.md",
             "skills/quality-gate/SKILL.md", "skills/commit-discipline/SKILL.md", "skills/multi-repo-summary/SKILL.md",
             "skills/gitlab-mr-publisher/SKILL.md", "skills/jira-progress-update/SKILL.md",
             "agents/sdlc-orchestrator.agent.md", "agents/sdlc-ticket-analyst.agent.md",
             "agents/sdlc-impact-analyst.agent.md", "agents/sdlc-implementer.agent.md",
             "agents/sdlc-quality-gate.agent.md", "agents/sdlc-release-scribe.agent.md"]

    def test_gated(self):
        for f in self.GATED:
            text = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("@@SDLC@@ preflight", text, f)
            self.assertIn("save tokens", text, f)
        conv = (ROOT / "skills/sdlc-conventions/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Exit 3 (STOP)", conv)
        self.assertIn("Never choose this yourself", conv)


class HookInventoryTests(unittest.TestCase):
    def setUp(self):
        self.cp = sdlc.load_config()

    def sdlc_cli(self, ws: Path, *args):
        return run(sys.executable, str(SDLC), *args, env={"SDLC_TOOLKIT_HOME": str(ROOT), "SDLC_WORKSPACE_ROOT": str(ws)},
                   check=False)

    def test_statuses(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "ws"
            a, b, c = git_init(ws / "a"), git_init(ws / "b"), git_init(ws / "c")
            (b / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
            (b / ".git" / "hooks" / "commit-msg").write_text("#!/bin/sh\necho mine\n")
            run("git", "-C", str(c), "config", "core.hooksPath", ".husky")
            p = self.sdlc_cli(ws, "install-hooks")
            self.assertIn(f"[sdlc] hook installed commit-msg {sdlc._posix(a / '.git' / 'hooks' / 'commit-msg')}", p.stdout)
            self.assertIn("[sdlc] hook foreign commit-msg", p.stdout)
            self.assertIn("[sdlc] hook unchanged pre-push", self.sdlc_cli(ws, "install-hooks").stdout)
            rows = {(Path(r["repo"]).name, r["name"]): r for r in sdlc.git_hook_inventory(self.cp, [a, b, c])}
            self.assertEqual(rows[("a", "commit-msg")]["status"], "installed")
            self.assertEqual(rows[("a", "commit-msg")]["event"], sdlc.HOOK_EVENTS["commit-msg"])
            self.assertEqual(rows[("b", "commit-msg")]["status"], "foreign")
            self.assertEqual(rows[("b", "pre-push")]["status"], "installed")
            self.assertEqual(rows[("c", "pre-push")]["status"], "skipped")
            # a toolkit hook pointing at a removed helper is outdated, and install-hooks updates it
            (a / ".git" / "hooks" / "pre-push").write_text(f'#!/bin/sh\n# {sdlc.HOOK_MARKER}\n"python3" "/gone/sdlc.py" x\n')
            self.assertEqual({r["name"]: r["status"] for r in sdlc.git_hook_inventory(self.cp, [a])}["pre-push"], "outdated")
            self.assertIn("[sdlc] hook updated pre-push", self.sdlc_cli(ws, "install-hooks").stdout)
            (a / ".git" / "hooks" / "commit-msg").unlink()
            p = self.sdlc_cli(ws, "hooks", "--json")
            self.assertEqual(p.returncode, 1)  # something is missing
            got = {(Path(r["repo"]).name, r["name"]): r["status"] for r in json.loads(p.stdout)}
            self.assertEqual(got[("a", "commit-msg")], "missing")
            text = self.sdlc_cli(ws, "hooks", "--markdown").stdout
            self.assertIn("| Hook | Type | Trigger | Status | Path |", text)
            self.assertIn("no global git hooks, editor/agent hooks, shell hooks or scheduled jobs", text)

    def test_editor_hooks_listed_without_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(t)
            (home / ".claude").mkdir()
            (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {
                "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "orbit hook session-start"}]}],
                "PreToolUse": [{"hooks": [{"type": "command", "command": "my-linter --fix"}]}]}}))
            rows = sdlc.editor_hook_inventory(home)
            self.assertEqual(len(rows), 1)  # unrelated hooks are not listed
            self.assertEqual(rows[0]["event"], "SessionStart")
            self.assertEqual(rows[0]["status"], "external")
            self.assertEqual(rows[0]["type"], "editor hook (Claude Code)")


class InstallerHookReportTests(unittest.TestCase):
    def test_fresh_install_then_update(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ws = tmp / "work"
            repo = git_init(ws / "app")
            env = {"COPILOT_HOME": str(tmp / ".copilot"), "XDG_CONFIG_HOME": str(tmp / ".config")}
            cmd = [sys.executable, str(ROOT / "install.py"), "--target", "copilot", "--workspace", str(ws),
                   "--set", "orbit.enabled=no"]
            p = run(*cmd, env=env)
            self.assertIn("HOOKS ON THIS SYSTEM", p.stdout)
            self.assertIn("[installed] commit-msg (git hook)", p.stdout)
            md = (tmp / ".copilot" / "sdlc-toolkit" / "MANUAL_STEPS.md").read_text(encoding="utf-8")
            self.assertIn("## Hooks on this system", md)
            self.assertIn(sdlc._posix(repo / ".git" / "hooks" / "pre-push"), md)
            self.assertLess(md.index("## Post-install checklist"), md.index("## Hooks on this system"))
            p = run(*cmd, env=env)  # update / re-install
            self.assertIn("[unchanged] pre-push (git hook)", p.stdout)
            p = run(*cmd, "--no-hooks", env=env)
            self.assertIn("[installed] commit-msg (git hook)", p.stdout)  # still on disk, reported as such
            m = json.loads((tmp / ".copilot" / "sdlc-toolkit" / "manifest.json").read_text())
            self.assertEqual(m["hooks"], [str(repo)])  # --no-hooks keeps track of hooks installed earlier


class AgentUiTests(unittest.TestCase):
    """scripts/sdlc_ui_mcp.py: A2UI panels served as an MCP App, and the installer wiring."""
    UI_CAPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}

    def rpc(self, messages, cwd: Path, env=None):
        e = dict(os.environ, SDLC_TOOLKIT_HOME=str(ROOT), SDLC_UI_STATUS_FILE=str(cwd / "ui-status.json"), **(env or {}))
        lines = "".join(json.dumps(m) + "\n" for m in messages)
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "sdlc_ui_mcp.py")], input=lines, cwd=str(cwd),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=e, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return {m.get("id"): m for m in (json.loads(ln) for ln in p.stdout.splitlines())}

    @staticmethod
    def init(caps=None, name="test-host"):
        return {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": caps or {}, "clientInfo": {"name": name}}}

    @staticmethod
    def call(i, name, args):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def payload(self, result) -> list:
        self.assertFalse(result.get("isError"), result)
        res = [c for c in result["content"] if c["type"] == "resource"]
        self.assertEqual(res[0]["resource"]["mimeType"], "application/a2ui+json")
        msgs = json.loads(res[0]["resource"]["text"])
        import a2ui
        self.assertEqual(a2ui.check(msgs), [])
        self.assertEqual(msgs[0]["version"], "1.0")
        return msgs

    @staticmethod
    def actions(msgs) -> list:
        return [c["action"]["event"] for c in msgs[0]["createSurface"]["components"] if c["component"] == "Button"]

    def test_terminal_clients_get_no_tools(self):
        with tempfile.TemporaryDirectory() as t:
            out = self.rpc([self.init(name="claude-code"), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                            self.call(2, "sdlc_ui_summary", {"title": "x", "status": "done"})], Path(t))
            self.assertEqual(out[1]["result"]["tools"], [])
            self.assertEqual(out[2]["error"]["code"], -32602)

    def test_tools_resource_and_screens(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t)
            wd = ws / ".sdlc" / "PROJ-7"
            wd.mkdir(parents=True)
            (wd / "plan.md").write_text("# Plan\n\n1. change login.py\n", encoding="utf-8")
            (wd / "impact.md").write_text("# Impact\n", encoding="utf-8")
            (wd / "quality.json").write_text(json.dumps({"ticket_key": "PROJ-7", "result": "FAIL", "repos": [
                {"name": "app", "result": "FAIL", "changed_files": ["a.py"], "checks": [
                    {"check": "lint", "command": "ruff", "status": "fail", "details": "E501", "required": True},
                    {"check": "tests", "command": "pytest", "status": "pass", "details": "ok"}]}]}), encoding="utf-8")
            out = self.rpc([
                self.init(self.UI_CAPS),
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": "ui://sdlc/app"}},
                self.call(3, "sdlc_ui_confirm", {"title": "Push", "action": "push", "preview": "git push",
                                                 "allow_comment": True}),
                self.call(4, "sdlc_ui_summary", {"title": "Done", "status": "done", "items": [{"label": "a", "state": "warn"}],
                                                 "links": [{"label": "ok", "url": "https://x.example/1"},
                                                           {"label": "bad", "url": "javascript:alert(1)"}],
                                                 "next_steps": [{"label": "Next", "reply": "continue"}]}),
                self.call(5, "sdlc_ui_plan", {"ticket": "PROJ-7"}),
                self.call(6, "sdlc_ui_quality", {"ticket": "PROJ-7"}),
                self.call(7, "sdlc_ui_ticket", {"ticket": "PROJ-7"}),
                self.call(8, "sdlc_ui_plan", {"ticket": "../etc"}),
                self.call(9, "sdlc_ui_quality", {"ticket": "PROJ-8"}),
            ], ws, {"SDLC_WORKSPACE_ROOT": str(ws)})
            self.assertEqual(out[0]["result"]["serverInfo"]["name"], "sdlc-ui")
            tools = {t["name"]: t for t in out[1]["result"]["tools"]}
            self.assertIn("sdlc_ui_confirm", tools)
            self.assertEqual(tools["sdlc_ui_plan"]["_meta"]["ui"]["resourceUri"], "ui://sdlc/app")
            self.assertEqual(tools["sdlc_ui_checklist_refresh"]["_meta"]["ui"]["visibility"], ["app"])
            html = out[2]["result"]["contents"][0]
            self.assertEqual(html["mimeType"], "text/html;profile=mcp-app")
            self.assertIn("<script", html["text"])
            ev = self.actions(self.payload(out[3]["result"]))
            self.assertEqual([e["context"]["text"] for e in ev], ["no", "changes", "yes"])  # buttons only reply in chat
            self.assertTrue(all(e["name"] == "sdlc.chat" for e in ev))
            self.assertIn("Wait for the developer", out[3]["result"]["content"][0]["text"])
            ev = self.actions(self.payload(out[4]["result"]))
            self.assertEqual([e["name"] for e in ev], ["sdlc.open", "sdlc.chat"])  # javascript: link dropped
            ev = self.actions(self.payload(out[5]["result"]))
            self.assertEqual(ev[-1]["context"]["text"], "approve")
            self.assertFalse((wd / "plan.approved").exists())  # a panel never approves by itself
            self.assertIn("FAIL", out[6]["result"]["content"][0]["text"])
            self.payload(out[6]["result"])
            self.assertIn("3/8 stages done; next: Ticket understood", out[7]["result"]["content"][0]["text"])
            self.assertTrue(out[8]["result"]["isError"])
            self.assertTrue(out[9]["result"]["isError"])
            st = json.loads((ws / "ui-status.json").read_text(encoding="utf-8"))  # read by `sdlc doctor`
            self.assertEqual((st["client"], st["panels"], st["ui_extension_declared"]), ("test-host", True, True))
            self.assertTrue(st["panel_loaded_by_client"])
            self.assertEqual((st["last_tool"], st["last_tool_ok"]), ("sdlc_ui_quality", False))  # the PROJ-8 error
            self.assertIn("No quality report", st["last_error"])

    def test_render_fallback_for_hosts_that_drop_the_result(self):
        """Copilot CLI agent host: panel shown, tool result not forwarded. The panel asks sdlc_ui_render."""
        with tempfile.TemporaryDirectory() as t:
            args = {"title": "Work log", "status": "info", "items": [{"label": "PROJ-1", "state": "done"}]}
            out = self.rpc([
                self.init(self.UI_CAPS),
                self.call(1, "sdlc_ui_summary", args),
                self.call(2, "sdlc_ui_render", {"tool": "sdlc_ui_summary", "arguments": args}),
                self.call(3, "sdlc_ui_render", {"arguments": {"title": "Push", "action": "push"}}),  # guessed: confirm
                self.call(4, "sdlc_ui_render", {}),  # nothing forwarded at all: the panel built last
                self.call(5, "sdlc_ui_render", {"tool": "sdlc_ui_render"}),
            ], Path(t))
            first = self.payload(out[1]["result"])
            self.assertEqual(out[1]["result"]["_meta"]["sdlc-ui/a2ui"], first)  # for hosts that drop resources
            again = self.payload(out[2]["result"])
            self.assertEqual(again[0]["createSurface"]["components"], first[0]["createSurface"]["components"])
            self.assertIn("Confirmation panel", out[3]["result"]["content"][0]["text"])
            last = self.payload(out[4]["result"])
            self.assertIn("confirm", last[0]["createSurface"]["surfaceId"])
            self.assertTrue(out[5]["result"]["isError"])

    def test_known_editor_without_declared_extension(self):
        with tempfile.TemporaryDirectory() as t:
            out = self.rpc([self.init(name="Visual Studio Code"), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}], Path(t))
            self.assertTrue(out[1]["result"]["tools"])

    def test_bundle_matches_manifest(self):
        import hashlib
        meta = json.loads((ROOT / "scripts" / "ui" / "sdlc-ui.json").read_text(encoding="utf-8"))
        data = (ROOT / "scripts" / "ui" / "sdlc-ui.html").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"])
        self.assertEqual(meta["a2ui"]["protocol"], "1.0")

    def test_installer_registers_server_and_writes_report(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "work").mkdir()
            env = {"HOME": t, "USERPROFILE": t, "COPILOT_HOME": str(tmp / ".copilot"), "XDG_CONFIG_HOME": str(tmp / ".config")}
            cmd = [sys.executable, str(ROOT / "install.py"), "--no-hooks", "--set", "orbit.enabled=no",
                   "--workspace", str(tmp / "work"), "--target", "copilot,claude,codex"]
            run(*cmd, "--dry-run", "--report-json", str(tmp / "preview.json"), env=env)
            preview = json.loads((tmp / "preview.json").read_text(encoding="utf-8"))
            self.assertTrue(preview["dry_run"])
            self.assertTrue(any("Agent UI panels" in d for d in preview["done"]))
            self.assertFalse((tmp / ".copilot" / "sdlc-toolkit").exists())  # dry run wrote nothing else
            run(*cmd, env=env)
            home = tmp / ".copilot" / "sdlc-toolkit"
            self.assertTrue((home / "scripts" / "ui" / "sdlc-ui.html").exists())
            rep = json.loads((home / "install-report.json").read_text(encoding="utf-8"))
            self.assertFalse(rep["dry_run"])
            self.assertEqual(json.loads((home / "manifest.json").read_text())["source"], str(ROOT))
            ui = json.loads((tmp / ".claude.json").read_text())["mcpServers"]["sdlc-ui"]
            self.assertTrue(ui["args"][0].endswith("sdlc_ui_mcp.py"))
            self.assertIn('[mcp_servers."sdlc-ui"]', (tmp / ".codex" / "config.toml").read_text())
            run(*cmd, "--set", "ui.mode=off", env=env)
            self.assertNotIn("sdlc-ui", json.loads((tmp / ".claude.json").read_text())["mcpServers"])
