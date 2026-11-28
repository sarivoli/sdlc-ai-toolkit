#!/usr/bin/env python3
"""Install the SDLC AI Toolkit for the current user.

    python install.py                 install / upgrade (safe to re-run)
    python install.py --dry-run       show what would change
    python install.py --set jira.site=https://acme.atlassian.net --set gitlab.group=acme
    python install.py --workspace ~/work      folder that holds your repos
    python install.py --no-hooks      don't add git hooks to workspace repos
    python install.py --target all    also install into Claude Code, Cursor, Antigravity, Gemini CLI, Codex
    python install.py --uninstall     remove everything this installer added
Or one line: curl -fsSL https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.sh | bash

What it does for GitHub Copilot (user level, so it works in every workspace); other
editors get the same skills/agents/MCP servers in their own folders (see installer_targets.py):
  ~/.copilot/agents/          custom agents  (SDLC Orchestrator + specialists + reused community agents)
  ~/.copilot/skills/          agent skills   (toolkit skills + reused awesome-copilot skills)
  ~/.copilot/sdlc-toolkit/    config, templates, helper CLI, MANUAL_STEPS.md
  ~/.copilot/sdlc-journal/    personal work journal (kept on upgrade and uninstall)
  ~/.copilot/mcp-config.json  'atlassian' and 'gitlab' MCP servers (merged, backup kept)
  <workspace repos>/.git/hooks commit-msg + pre-push hooks (existing hooks are never overwritten)

Standard library only; Python 3.8+; Windows, macOS, Linux.
"""
from __future__ import annotations

import argparse
import configparser
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import installer_targets as T

SRC = Path(__file__).resolve().parent
VERSION = (SRC / "VERSION").read_text(encoding="utf-8").strip() if (SRC / "VERSION").exists() else "dev"
MARKER = ".sdlc-toolkit"
PLACEHOLDERS = {
    ("jira", "site"): "your-company",
    ("gitlab", "group"): "your-group",
}

OK, WARN, INFO = "✅", "⚠️ ", "  ·"


class Installer:
    def __init__(self, args):
        self.args = args
        self.dry = args.dry_run
        self.copilot_home = Path(args.copilot_home or os.environ.get("COPILOT_HOME") or Path.home() / ".copilot").expanduser()
        self.home = self.copilot_home / "sdlc-toolkit"
        self.manifest_path = self.home / "manifest.json"
        self.old_manifest = self._read_json(self.manifest_path)
        self.manifest = {"version": VERSION, "installed_at": _dt.datetime.now().isoformat(timespec="seconds"),
                         "skills": [], "agents": [], "mcp_servers": [], "vscode_mcp_servers": [], "hooks": []}
        self.targets = self._resolve_targets(getattr(args, "target", None) or "auto")
        self.done: list[str] = []
        self.manual: list[str] = []
        self.notes: list[str] = []

    @staticmethod
    def _resolve_targets(spec: str) -> list:
        spec = spec.strip().lower()
        if spec == "auto":
            return T.detect()
        if spec == "all":
            return list(T.ALL)
        names = [s.strip() for s in spec.split(",") if s.strip()]
        bad = [n for n in names if n not in T.TARGETS]
        if bad:
            sys.exit(f"Unknown --target {', '.join(bad)}. Choose from: auto, all, {', '.join(T.ALL)}")
        return names

    # ------------------------------------------------------------ utils
    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, path: Path, text: str):
        if self.dry:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def _backup(self, path: Path):
        if path.exists() and not self.dry:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, path.with_name(path.name + f".bak-{stamp}"))

    def _owned(self, kind: str, name: str) -> bool:
        return name in self.old_manifest.get(kind, [])

    # ------------------------------------------------------------ steps
    def check_prereqs(self):
        if sys.version_info < (3, 8):
            sys.exit("Python 3.8+ is required.")
        self.done.append(f"Python {sys.version.split()[0]}")
        if not shutil.which("git"):
            self.manual.append("Install Git and make sure `git` is on PATH, then re-run the installer.")
        code = shutil.which("code") or shutil.which("code-insiders")
        if code:
            try:
                ver = subprocess.run([code, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, timeout=20).stdout.split()[0]
                self.done.append(f"VS Code {ver} found")
            except Exception:
                pass
        else:
            self.notes.append("VS Code CLI (`code`) not on PATH - fine, but make sure VS Code is up to date "
                              "(custom agents + agent skills need a recent version with GitHub Copilot Chat).")

    def sdlc_command(self) -> str:
        script = (self.home / "scripts" / "sdlc.py").as_posix()
        if os.name == "nt":
            launcher = "py -3" if shutil.which("py") else "python"
        else:
            exe = sys.executable
            launcher = exe if exe and " " not in exe else "python3"
        return f'{launcher} "{script}"'

    def substitute(self, text: str) -> str:
        return text.replace("@@SDLC@@", self.sdlc_command()).replace("@@TOOLKIT_HOME@@", self.home.as_posix())

    def install_core(self):
        for sub in ("templates", "scripts"):
            dst = self.home / sub
            if not self.dry:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(SRC / sub, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self._write(self.home / "toolkit.ini", (SRC / "config" / "toolkit.ini").read_text(encoding="utf-8"))
        self._write(self.home / "VERSION", VERSION + "\n")
        self._write(self.home / "USER_MANUAL.md", (SRC / "docs" / "USER_MANUAL.md").read_text(encoding="utf-8"))
        self.done.append(f"Config, templates and helper CLI -> {self.home}")

    def apply_overrides(self):
        local = self.home / "toolkit.local.ini"
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        if local.exists():
            cp.read(local, encoding="utf-8")
        changed = False
        for item in self.args.set or []:
            if "=" not in item or "." not in item.split("=", 1)[0]:
                sys.exit(f"--set expects section.key=value, got: {item}")
            k, v = item.split("=", 1)
            section, key = k.split(".", 1)
            if not cp.has_section(section):
                cp.add_section(section)
            cp.set(section, key, v)
            changed = True
        if self.args.workspace:
            if not cp.has_section("workspace"):
                cp.add_section("workspace")
            cp.set("workspace", "root", str(Path(self.args.workspace).expanduser().resolve()))
            changed = True
        if changed and not self.dry:
            local.parent.mkdir(parents=True, exist_ok=True)
            with local.open("w", encoding="utf-8") as fh:
                fh.write("; Personal overrides for the SDLC toolkit (written by install.py --set / --workspace)\n")
                cp.write(fh)
            self.done.append(f"Personal overrides saved to {local}")

    def effective_config(self) -> configparser.ConfigParser:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(" ;",))
        cp.optionxform = str
        files = [SRC / "config" / "toolkit.ini", self.home / "toolkit.local.ini"]
        cp.read([str(f) for f in files if f.exists()], encoding="utf-8")
        return cp

    def check_config(self, cp):
        missing = []
        for (section, key), placeholder in PLACEHOLDERS.items():
            if placeholder in cp.get(section, key, fallback=placeholder):
                missing.append(f"{section}.{key}")
        if missing:
            self.manual.append(
                "Set your team values (still placeholders: " + ", ".join(missing) + "). Either ask your team lead to edit "
                "`config/toolkit.ini` in the toolkit repo (recommended, applies to everyone), or for yourself run:\n"
                "      python install.py --set jira.site=https://<your-site>.atlassian.net --set jira.project_keys=PROJ "
                "--set gitlab.group=<your-group>")
        root = Path(cp.get("workspace", "root", fallback="~/work")).expanduser()
        if not root.exists():
            self.manual.append(f"Workspace folder `{root}` does not exist. Point it at the folder that contains your repos:\n"
                               "      python install.py --workspace <path-to-folder-with-your-repos>")
        return root

    def install_tree(self, kind: str, src_dir: Path, dst_dir: Path, pattern: str):
        installed = []
        for src in sorted(src_dir.glob(pattern)):
            name = src.name
            dst = dst_dir / name
            if dst.exists() and not self._owned(kind, name):
                is_ours = (dst / MARKER).exists() if dst.is_dir() else MARKER in dst.read_text(encoding="utf-8", errors="ignore")[:400]
                if not is_ours:
                    self.notes.append(f"{kind[:-1]} `{name}` already exists in {dst_dir} and was not installed by the toolkit - kept yours.")
                    continue
            if not self.dry:
                dst_dir.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                    for md in dst.rglob("*.md"):
                        md.write_text(self.substitute(md.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
                    (dst / MARKER).write_text(f"installed by sdlc-ai-toolkit {VERSION}\n", encoding="utf-8")
                else:
                    text = self.substitute(src.read_text(encoding="utf-8"))
                    if text.startswith("---"):
                        end = text.find("\n---", 3)
                        text = text[: end + 4] + f"\n<!-- {MARKER} {VERSION} -->" + text[end + 4:]
                    dst.write_text(text, encoding="utf-8", newline="\n")
            installed.append(name)
        return installed

    def install_skills_agents(self):
        skills_dir = self.copilot_home / "skills"
        agents_dir = self.copilot_home / "agents"
        own_s = self.install_tree("skills", SRC / "skills", skills_dir, "*")
        ven_s = self.install_tree("skills", SRC / "vendor" / "awesome-copilot" / "skills", skills_dir, "*")
        own_a = self.install_tree("agents", SRC / "agents", agents_dir, "*.agent.md")
        ven_a = self.install_tree("agents", SRC / "vendor" / "awesome-copilot" / "agents", agents_dir, "*.agent.md")
        self.manifest["skills"] = own_s + ven_s
        self.manifest["agents"] = own_a + ven_a
        self.done.append(f"{len(own_s)} toolkit skills + {len(ven_s)} reused awesome-copilot skills -> {skills_dir}")
        self.done.append(f"{len(own_a)} toolkit agents + {len(ven_a)} reused awesome-copilot agents -> {agents_dir}")
        # remove things a previous version installed that no longer exist
        for kind, d in (("skills", skills_dir), ("agents", agents_dir)):
            for name in set(self.old_manifest.get(kind, [])) - set(self.manifest[kind]):
                p = d / name
                if p.exists() and not self.dry:
                    shutil.rmtree(p) if p.is_dir() else p.unlink()

    def orbit_mode(self, cp) -> str:
        """local (default): stdio server on this machine; remote: hosted GitLab endpoint; off."""
        if cp.get("orbit", "enabled", fallback="yes").lower() not in ("yes", "true", "1"):
            return "off"
        if cp.get("orbit", "mcp_endpoint", fallback="yes").lower() not in ("yes", "true", "1"):
            return "off"
        mode = cp.get("orbit", "mcp_mode", fallback="local").strip().lower()
        return mode if mode in ("local", "remote", "off") else "local"

    def orbit_local_server(self) -> dict:
        python = sys.executable or ("py" if sys.platform == "win32" else "python3")
        return {"type": "stdio", "command": python, "args": [str(self.home / "scripts" / "orbit_mcp.py")]}

    def mcp_servers(self, cp) -> dict:
        servers = self._base_mcp(cp)
        mode = self.orbit_mode(cp)
        if mode == "local":
            servers["gitlab-orbit"] = self.orbit_local_server()
        elif mode == "remote":
            servers["gitlab-orbit"] = {"type": "http", "url": cp.get("orbit", "mcp_url", fallback=T.ORBIT_CLOUD_URL)}
        return servers

    def _base_mcp(self, cp) -> dict:
        return {
            "atlassian": {"type": "http", "url": cp.get("mcp", "atlassian_url", fallback="https://mcp.atlassian.com/v1/mcp/authv2")},
            "gitlab": {"type": "http", "url": cp.get("mcp", "gitlab_url", fallback="https://gitlab.com/api/v4/mcp")},
        }

    def merge_mcp(self, path: Path, top_key: str, servers: dict, manifest_key: str):
        data = self._read_json(path) if path.exists() else {}
        if path.exists() and not data and path.read_text(encoding="utf-8", errors="ignore").strip():
            self.manual.append(f"{path} is not plain JSON (comments?). Add these servers by hand under \"{top_key}\":\n"
                               + json.dumps(servers, indent=2))
            return
        block = data.setdefault(top_key, {})
        added = []
        for name, conf in servers.items():
            if name in block and block[name] != conf and name not in self.old_manifest.get(manifest_key, []) \
                    and not T.is_orbit_cloud(name, block[name], conf):
                self.notes.append(f"MCP server `{name}` already exists in {path} with different settings - kept yours. "
                                  f"The agents expect a server named `{name}` ({T.describe(conf)}).")
                continue
            if name in block and T.is_orbit_cloud(name, block[name], conf):
                self.notes.append(f"`{name}` in {path} switched from the hosted GitLab endpoint to the local Orbit server.")
            url = T.server_url(conf)
            for other, oconf in block.items():
                if url and other != name and isinstance(oconf, dict) and T.server_url(oconf) == url:
                    self.notes.append(f"You also have `{other}` pointing at {url}. You can remove it to avoid duplicate tools.")
            block[name] = conf
            added.append(name)
        self._backup(path)
        self._write(path, json.dumps(data, indent=2) + "\n")
        self.manifest[manifest_key] = added
        if added:
            self.done.append(f"MCP servers {', '.join(added)} -> {path}")

    def vscode_user_dir(self) -> Path | None:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        for product in ("Code", "Code - Insiders"):
            d = base / product / "User"
            if d.exists():
                return d
        return None

    def install_mcp(self, cp):
        servers = self.mcp_servers(cp)
        self.merge_mcp(self.copilot_home / "mcp-config.json", "mcpServers",
                       {n: T.shape_server(c, "copilot-cli") for n, c in servers.items()}, "mcp_servers")
        if cp.get("mcp", "write_vscode_profile_mcp", fallback="no").lower() in ("yes", "true", "1"):
            d = self.vscode_user_dir()
            if d:
                self.merge_mcp(d / "mcp.json", "servers",
                               {n: T.shape_server(c, "typed", T.VSCODE_WORKSPACE_VAR) for n, c in servers.items()},
                               "vscode_mcp_servers")
            else:
                self.notes.append("VS Code user folder not found; skipped profile mcp.json.")
        self.manual.append(
            "Sign in to Jira and GitLab once (OAuth in your browser):\n"
            "      VS Code > Command Palette > `MCP: List Servers` > `atlassian` > Start Server > approve in browser.\n"
            "      Repeat for `gitlab`. Trust the servers if VS Code asks. (`gitlab-orbit` is local and needs no sign-in.)\n"
            "      If they don't appear: run `MCP: Open User Configuration` and add under \"servers\":\n"
            + "\n".join("      " + ln for ln in json.dumps(
                {n: T.shape_server(c, "typed", T.VSCODE_WORKSPACE_VAR) for n, c in servers.items()}, indent=2).splitlines()))

    # ------------------------------------------------------------ other editors
    def _is_ours(self, dst: Path, owned: list) -> bool:
        if dst.name in owned:
            return True
        if dst.is_dir():
            return (dst / MARKER).exists()
        return MARKER in dst.read_text(encoding="utf-8", errors="ignore")[:600]

    def install_other_targets(self, cp):
        servers = self.mcp_servers(cp)
        own_agents = sorted((SRC / "agents").glob("*.agent.md"))
        ven_agents = sorted((SRC / "vendor" / "awesome-copilot" / "agents").glob("*.agent.md"))
        names = T.name_map(own_agents + ven_agents)
        skill_roots = [SRC / "skills", SRC / "vendor" / "awesome-copilot" / "skills"]
        self.manifest["targets"] = {}
        for tgt in self.targets:
            if tgt == "copilot":
                continue
            spec = T.TARGETS[tgt]
            old = self.old_manifest.get("targets", {}).get(tgt, {})
            rec = {"skills": [], "agents": []}
            sk_dir = spec["skills"]
            adir_mode, adir = spec["agents"]

            def put_skill(name: str, writer):
                dst = sk_dir / name
                if dst.exists() and not self._is_ours(dst, old.get("skills", [])):
                    self.notes.append(f"[{tgt}] skill `{name}` already exists and is not ours - kept yours.")
                    return
                if not self.dry:
                    if dst.exists():
                        shutil.rmtree(dst)
                    writer(dst)
                    (dst / MARKER).write_text(f"installed by sdlc-ai-toolkit {VERSION}\n", encoding="utf-8")
                rec["skills"].append(name)

            def copy_skill(src: Path):
                def w(dst: Path):
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                    for md in dst.rglob("*.md"):
                        md.write_text(self.substitute(md.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
                return w

            for root_dir in skill_roots:
                for src in sorted(root_dir.glob("*")):
                    if src.is_dir() and (src / "SKILL.md").exists():
                        put_skill(src.name, copy_skill(src))
            if adir_mode == "md":
                for src in own_agents + ven_agents:
                    sl, text = T.convert_agent(src, names, self.substitute(src.read_text(encoding="utf-8")))
                    dst = adir / f"{sl}.md"
                    if dst.exists() and not self._is_ours(dst, old.get("agents", [])):
                        self.notes.append(f"[{tgt}] agent `{sl}` already exists and is not ours - kept yours.")
                        continue
                    self._write(dst, text.rstrip("\n") + f"\n\n<!-- {MARKER} {VERSION} -->\n")
                    rec["agents"].append(dst.name)
            elif adir_mode == "skills":
                for src in own_agents:
                    sl, text = T.convert_agent(src, names, self.substitute(src.read_text(encoding="utf-8")))
                    put_skill(sl, lambda dst, text=text: (dst.mkdir(parents=True), (dst / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")))
            for kind, d in (("skills", sk_dir), ("agents", adir)):
                if d is None:
                    continue
                for name in set(old.get(kind, [])) - set(rec[kind]):
                    p = d / name
                    if p.exists() and not self.dry:
                        shutil.rmtree(p) if p.is_dir() else p.unlink()
            path, key, shape = spec["mcp"]
            if shape == "toml":
                self._toml_mcp(path, servers, rec)
            else:
                self.merge_mcp(path, key, {n: T.shape_server(c, shape, spec.get("workspace_var")) for n, c in servers.items()},
                               f"mcp:{tgt}")
            self.manifest["targets"][tgt] = rec
            self.done.append(f"{spec['label']}: {len(rec['skills'])} skills, {len(rec['agents'])} agents -> {sk_dir.parent}")
            self.manual.append(f"{spec['label']}: {spec['reload']}")

    def _toml_mcp(self, path: Path, servers: dict, rec: dict):
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        new = T.toml_upsert(text, servers)
        if new != text:
            self._backup(path)
            self._write(path, new)
        mine = [n for n in servers if f'[mcp_servers."{n}"]' in new]
        self.manifest["mcp:codex"] = mine
        if mine:
            self.done.append(f"MCP servers {', '.join(mine)} -> {path}")

    def install_orbit(self, cp, root: Path):
        if cp.get("orbit", "enabled", fallback="yes").lower() not in ("yes", "true", "1"):
            return
        if self._orbit_cli():
            self.done.append(f"GitLab Orbit CLI already installed ({' '.join(self._orbit_cli())})")
        elif self.dry:
            self.done.append("(dry run) would install GitLab Orbit CLI: npm install -g @gitlab/orbit")
        else:
            npm = shutil.which("npm")
            ok = False
            if npm and cp.get("orbit", "install_method", fallback="npm") == "npm":
                ok = subprocess.run([npm, "install", "-g", "@gitlab/orbit"], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True).returncode == 0
            if ok:
                self.done.append("GitLab Orbit CLI installed (npm @gitlab/orbit)")
            else:
                self.manual.append(
                    "Install the GitLab Orbit CLI (impact analysis uses its code graph):\n"
                    "      npm install -g @gitlab/orbit      (needs Node.js)\n"
                    '      or: curl -fsSL "https://gitlab.com/gitlab-org/orbit/knowledge-graph/-/raw/main/install.sh" | bash')
        if cp.get("orbit", "auto_index", fallback="yes").lower() in ("yes", "true", "1") and not self.dry \
                and root.exists():
            env = dict(os.environ, SDLC_TOOLKIT_HOME=str(self.home), SDLC_WORKSPACE_ROOT=str(root))
            proc = subprocess.run([sys.executable, str(self.home / "scripts" / "sdlc.py"), "orbit", "index", "--", "--async"],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, encoding="utf-8")
            self.done.append(f"Orbit graph for workspace folder {root}: " + ("indexing started" if proc.returncode == 0 else "index not started (run `sdlc orbit index`)"))
        mode = self.orbit_mode(cp)
        if mode == "local":
            self.manual.append(
                "GitLab Orbit runs locally (no GitLab sign-in needed for it): the `gitlab-orbit` MCP server is "
                f"`{self.home.as_posix()}/scripts/orbit_mcp.py`, which serves the code graph of the folder your editor has open "
                "(stored in <folder>/.sdlc/orbit) and starts indexing it the first time. To check: VS Code > Command Palette > "
                "`MCP: List Servers` > `gitlab-orbit` > Start Server, then ask Copilot to call `orbit_status`. "
                f"To index another folder by hand run there: `{self.sdlc_command()} orbit index`.")
        elif mode == "remote":
            self.manual.append(
                "Orbit graphs are per workspace folder (stored in <folder>/.sdlc/orbit). When you open another folder, "
                f"run once there: `{self.sdlc_command()} orbit index`. The hosted `gitlab-orbit` MCP server needs Orbit turned on "
                "for your GitLab group and an OAuth sign-in on first use.")

    def _orbit_cli(self):
        sys.path.insert(0, str(SRC / "scripts"))
        try:
            import sdlc
            return sdlc.orbit_command()
        except Exception:
            return [p for p in (shutil.which("orbit"),) if p] or None
        finally:
            sys.path.pop(0)

    def install_hooks(self, root: Path):
        if self.args.no_hooks:
            self.notes.append("Git hooks skipped (--no-hooks). Add later: " + self.sdlc_command() + " install-hooks")
            return
        if not root.exists() or self.dry:
            return
        env = dict(os.environ, SDLC_TOOLKIT_HOME=str(self.home))
        proc = subprocess.run([sys.executable, str(self.home / "scripts" / "sdlc.py"), "install-hooks"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, encoding="utf-8")
        repos = [ln for ln in proc.stdout.splitlines() if ln.startswith("[sdlc] hooks installed")]
        for ln in proc.stdout.splitlines():
            if ln.startswith("[sdlc] MANUAL:"):
                self.manual.append(ln.replace("[sdlc] MANUAL:", "Git hooks -").strip())
        self.manifest["hooks"] = [ln.split(" in ", 1)[1] for ln in repos]
        self.done.append(f"commit-msg + pre-push hooks in {len(repos)} repo(s) under {root}")
        if not repos:
            self.notes.append(f"No git repos found under {root}. Clone your repos there, then run: {self.sdlc_command()} install-hooks")

    def optional_tools(self):
        missing = [t for t in ("ruff", "bandit") if not shutil.which(t)]
        if missing:
            self.manual.append(f"Optional but recommended - install the quality tools the gate uses: "
                               f"`pip install {' '.join(missing)}` (or add them to your buildout / dev requirements). "
                               "Missing tools are reported as 'missing', never as passed.")

    def finish(self):
        if "copilot" in self.targets:
          self.manual.append("Reload VS Code (`Developer: Reload Window`). In Copilot Chat open the agent picker: you should see "
                           "**SDLC Orchestrator**. Type `/` to see the skills (e.g. `/jira-ticket-digest`).")
        if "copilot" in self.targets:
          self.manual.append("Copilot Business/Enterprise: your org admin must allow **MCP servers in Copilot** (and agent mode) "
                           "in GitHub organization Copilot policies, otherwise the Jira/GitLab tools stay disabled.")
        self.manual.append(f"Check everything at any time: `{self.sdlc_command()} doctor`")
        report = ["# SDLC AI Toolkit - installation report", "",
                  f"Version {VERSION} · {self.manifest['installed_at']}", "", "## Done", ""]
        report += [f"- {d}" for d in self.done]
        report += ["", "## Manual steps (do these now)", ""]
        report += [f"{i}. {m}" for i, m in enumerate(self.manual, 1)]
        if self.notes:
            report += ["", "## Notes", ""] + [f"- {n}" for n in self.notes]
        report += ["", f"User manual: {(self.home / 'USER_MANUAL.md').as_posix()}", ""]
        text = "\n".join(report)
        self._write(self.home / "MANUAL_STEPS.md", text)
        self._write(self.manifest_path, json.dumps(self.manifest, indent=2) + "\n")
        print("\n" + "=" * 72)
        print(f"  SDLC AI Toolkit {VERSION} {'(dry run - nothing written)' if self.dry else 'installed'}")
        print("=" * 72)
        for d in self.done:
            print(f" {OK} {d}")
        print("\n  ACTION REQUIRED - manual steps:")
        for i, m in enumerate(self.manual, 1):
            print(f"  {WARN}{i}. {m}")
        for n in self.notes:
            print(f" {INFO} {n}")
        print(f"\n  This report is saved at {(self.home / 'MANUAL_STEPS.md').as_posix()}")

    def run(self):
        self.check_prereqs()
        self.install_core()
        self.apply_overrides()
        cp = self.effective_config()
        root = self.check_config(cp)
        if "copilot" in self.targets:
            self.install_skills_agents()
            self.install_mcp(cp)
        self.install_other_targets(cp)
        self.install_orbit(cp, root)
        self.install_hooks(root)
        self.optional_tools()
        self.finish()

    # ------------------------------------------------------------ uninstall
    def uninstall(self):
        m = self.old_manifest
        if not m:
            print("Nothing to uninstall (no manifest found).")
            return
        for kind in ("skills", "agents"):
            for name in m.get(kind, []):
                p = self.copilot_home / kind / name
                if p.exists():
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
        for tgt, rec in m.get("targets", {}).items():
            spec = T.TARGETS.get(tgt)
            if not spec:
                continue
            for kind, d in (("skills", spec["skills"]), ("agents", spec["agents"][1])):
                for name in rec.get(kind, []):
                    p = d / name if d else None
                    if p and p.exists():
                        shutil.rmtree(p) if p.is_dir() else p.unlink()
            path, key, shape = spec["mcp"]
            if shape == "toml":
                if path.exists():
                    path.write_text(T.toml_strip(path.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                data = self._read_json(path)
                if data.get(key):
                    for name in m.get(f"mcp:{tgt}", []):
                        data[key].pop(name, None)
                    self._backup(path)
                    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        for path, key, mk in ((self.copilot_home / "mcp-config.json", "mcpServers", "mcp_servers"),
                              ((self.vscode_user_dir() or Path("/nonexistent")) / "mcp.json", "servers", "vscode_mcp_servers")):
            data = self._read_json(path)
            if data.get(key):
                for name in m.get(mk, []):
                    data[key].pop(name, None)
                self._backup(path)
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        for repo in m.get("hooks", []):
            hooks = Path(repo) / ".git" / "hooks"
            for name in ("commit-msg", "pre-push"):
                h = hooks / name
                if h.exists() and "sdlc-ai-toolkit" in h.read_text(encoding="utf-8", errors="ignore"):
                    h.unlink()
        local = self.home / "toolkit.local.ini"
        keep = local.read_text(encoding="utf-8") if local.exists() else None
        shutil.rmtree(self.home, ignore_errors=True)
        if keep:
            self.home.mkdir(parents=True, exist_ok=True)
            local.write_text(keep, encoding="utf-8")
        print("SDLC AI Toolkit removed (your toolkit.local.ini was kept). Restart your editor(s).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--set", action="append", metavar="SECTION.KEY=VALUE", help="personal config override (repeatable)")
    ap.add_argument("--workspace", help="folder containing your repos")
    ap.add_argument("--no-hooks", action="store_true")
    ap.add_argument("--target", default="auto", metavar="EDITORS",
                    help="editors to install into: auto (default: Copilot + every editor found), all, or a comma list of "
                         + ", ".join(T.ALL))
    ap.add_argument("--copilot-home", help=argparse.SUPPRESS)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    inst = Installer(args)
    inst.uninstall() if args.uninstall else inst.run()


if __name__ == "__main__":
    main()
