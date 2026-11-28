#!/usr/bin/env python3
"""SDLC AI Toolkit helper CLI.

Deterministic helpers used by the Copilot agents and skills, so that the
parts that must be exact (commit rules, commit lists across repos, quality
checks, template rendering) never depend on the model's memory.

Standard library only. Python 3.8+. Works on Windows, macOS and Linux.

    python sdlc.py config                      effective configuration
    python sdlc.py template NAME [--repo P]    resolve + print a template
    python sdlc.py repos                       git repos in the workspace
    python sdlc.py workdir KEY                 per-ticket notes folder
    python sdlc.py branch-name KEY --type bugfix [--user kumar | --poc py3]
    python sdlc.py check-branch [--repo P]     refuse protected branches
    python sdlc.py check-commit (--message M | --message-file F)
    python sdlc.py quality KEY [--repo P ...]  run the quality gate
    python sdlc.py collect KEY [--repo P ...]  commits for KEY in all repos
    python sdlc.py summary KEY                 render summary / MR / Teams text
    python sdlc.py render TEMPLATE --data F    render any template with JSON
    python sdlc.py install-hooks [--repo P ...]
    python sdlc.py hooks [--json|--markdown]   every hook the toolkit installs / that affects it, with status
    python sdlc.py orbit index|list|status|grep|context   GitLab Orbit code graph for THIS workspace folder
    python sdlc.py log KEY --activity A --summary "..."   record work in the personal work journal
    python sdlc.py worklog [--ticket K] [--period week]    list journal entries
    python sdlc.py report --period week|month|year         work report from the journal
    python sdlc.py preflight [--folder F]      gate for ticket work: Orbit installed + folder indexed (exit 3 = stop)
    python sdlc.py checklist [--offline]       post-install checklist: Orbit index, git auth, Jira auth
    python sdlc.py doctor                      check the installation
"""
from __future__ import annotations

import argparse
import configparser
import datetime as _dt
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLKIT_HOME = Path(os.environ.get("SDLC_TOOLKIT_HOME", HERE.parent)).expanduser()
HOOK_MARKER = "sdlc-ai-toolkit"

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------


def _config_files() -> list[Path]:
    files = [TOOLKIT_HOME / "toolkit.ini", TOOLKIT_HOME / "config" / "toolkit.ini"]
    files = [f for f in files if f.exists()][:1]
    local = TOOLKIT_HOME / "toolkit.local.ini"
    if local.exists():
        files.append(local)
    return files


def load_config() -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(" ;",))
    cp.optionxform = str  # keep key case
    read = cp.read([str(f) for f in _config_files()], encoding="utf-8")
    if not read:
        sys.exit(f"sdlc: no toolkit.ini found under {TOOLKIT_HOME}. Run install.py first.")
    return cp


def cfg(cp, section, key, default=""):
    try:
        return cp.get(section, key).strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def cfg_list(cp, section, key):
    return [x.strip() for x in cfg(cp, section, key).split(",") if x.strip()]


def cfg_bool(cp, section, key, default=False):
    v = cfg(cp, section, key, "yes" if default else "no").lower()
    return v in ("1", "yes", "true", "on")


def workspace_root(cp) -> Path:
    env = os.environ.get("SDLC_WORKSPACE_ROOT")
    root = env or cfg(cp, "workspace", "root", ".") or "."
    return Path(root).expanduser().resolve()


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def discover_repos(cp, explicit: list[str] | None = None) -> list[Path]:
    if explicit:
        repos = []
        for p in explicit:
            path = Path(p).expanduser().resolve()
            if not is_repo(path):
                top = git(path, "rev-parse", "--show-toplevel", check=False)
                if not top:
                    sys.exit(f"sdlc: {p} is not inside a git repository")
                path = Path(top)
            repos.append(path)
        return sorted(set(repos))
    root = workspace_root(cp)
    depth = int(cfg(cp, "workspace", "repo_search_depth", "3") or 3)
    found: list[Path] = []
    skip = {"node_modules", ".venv", "venv", "eggs", "parts", "__pycache__", ".tox", "develop-eggs"}

    def walk(p: Path, d: int):
        if is_repo(p):
            found.append(p)
            # nested checkouts (e.g. mr.developer src/) are repos too
        if d >= depth:
            return
        try:
            for child in sorted(p.iterdir()):
                if child.is_dir() and child.name not in skip and not child.name.startswith("."):
                    walk(child, d + 1)
        except (PermissionError, OSError):
            pass

    if root.exists():
        walk(root, 0)
    return found


def remote_web_url(repo: Path) -> str:
    url = git(repo, "remote", "get-url", "origin", check=False)
    if not url:
        return ""
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$", url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    m = re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    return url


def project_path(web_url: str) -> str:
    m = re.match(r"^https://[^/]+/(.+)$", web_url)
    return m.group(1) if m else ""


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False) or "HEAD"


def base_ref(repo: Path, target: str) -> str:
    for ref in (f"origin/{target}", target):
        if git_ok(repo, "rev-parse", "--verify", "--quiet", ref):
            return ref
    return ""


def merge_base(repo: Path, target: str) -> str:
    ref = base_ref(repo, target)
    if not ref:
        return ""
    return git(repo, "merge-base", ref, "HEAD", check=False)


def target_branch(cp, repo: Path) -> str:
    default = cfg(cp, "gitlab", "default_target_branch", "main")
    if base_ref(repo, default):
        return default
    head = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
    if head.startswith("origin/"):
        return head[len("origin/"):]
    for cand in ("main", "master", "develop"):
        if base_ref(repo, cand):
            return cand
    return default


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

_GUIDANCE = re.compile(r"<!--\s*guidance:.*?-->\s*\n?", re.S)
_TOKEN = re.compile(r"\{\{\s*([#/]?)(each|if)?\s*([A-Za-z0-9_.]+)?\s*\}\}")


def resolve_template(cp, name: str, repo: str | None = None) -> Path:
    candidates = []
    if repo:
        candidates.append(Path(repo).expanduser().resolve() / ".sdlc" / "templates" / name)
    candidates.append(workspace_root(cp) / ".sdlc" / "templates" / name)
    candidates.append(TOOLKIT_HOME / "templates" / name)
    for c in candidates:
        if c.exists():
            return c
    sys.exit(f"sdlc: template '{name}' not found (looked in: {', '.join(map(str, candidates))})")


def _lookup(stack: list, key: str):
    for ctx in reversed(stack):
        cur = ctx
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur, True
    return None, False


def _parse(text: str):
    """Parse into a tree of ('text', s) | ('var', k) | ('each'|'if', k, children)."""
    root: list = []
    stack = [("root", None, root)]
    pos = 0
    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            stack[-1][2].append(("text", text[pos:m.start()]))
        sigil, block, key = m.group(1), m.group(2), m.group(3)
        if sigil == "#" and block:
            node = (block, key, [])
            stack[-1][2].append(node)
            stack.append(node)
        elif sigil == "/" and block:
            if len(stack) == 1 or stack[-1][0] != block:
                raise ValueError(f"template: unexpected {{{{/{block}}}}}")
            stack.pop()
        elif key:
            stack[-1][2].append(("var", key))
        pos = m.end()
    stack[-1][2].append(("text", text[pos:]))
    if len(stack) != 1:
        raise ValueError(f"template: unclosed {{{{#{stack[-1][0]} {stack[-1][1]}}}}}")
    return root


def _render_nodes(nodes, stack, missing: set) -> str:
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            out.append(node[1])
        elif kind == "var":
            val, found = _lookup(stack, node[1])
            if not found or val is None or val == "":
                missing.add(node[1])
                out.append("—")
            elif isinstance(val, list):
                out.append("\n".join(f"- {v}" if not str(v).startswith(("-", "|", "1.")) else str(v) for v in val))
            else:
                out.append(str(val))
        elif kind == "each":
            items, _ = _lookup(stack, node[1])
            for item in items or []:
                ctx = item if isinstance(item, dict) else {"this": item}
                out.append(_render_nodes(node[2], stack + [ctx], missing))
        elif kind == "if":
            val, _ = _lookup(stack, node[1])
            if val:
                out.append(_render_nodes(node[2], stack, missing))
    return "".join(out)


_STANDALONE = re.compile(r"^[ \t]*(\{\{\s*[#/](?:each|if)\b[^}]*\}\})[ \t]*\r?\n", re.M)


def render_text(template: str, data: dict) -> tuple[str, set]:
    template = _GUIDANCE.sub("", template)
    template = _STANDALONE.sub(r"\1", template)
    missing: set = set()
    text = _render_nodes(_parse(template), [data], missing)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text, missing


# --------------------------------------------------------------------------
# commit rules
# --------------------------------------------------------------------------

EXEMPT_PREFIXES = ("Merge ", "Revert \"", "fixup! ", "squash! ", "amend! ")


def check_commit_message(cp, message: str) -> list[str]:
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ["commit message is empty"]
    subject = lines[0].rstrip()
    if subject.startswith(EXEMPT_PREFIXES):
        return []
    errors = []
    regex = cfg(cp, "git", "commit_regex")
    if regex and not re.match(regex, subject):
        types = cfg(cp, "git", "commit_types")
        errors.append(
            "subject does not match the team format.\n"
            f"      expected: <type>(<scope>): <TICKET-KEY> <summary>   types: {types}\n"
            f"      example : fix(catalog): PROJ-123 reindex objects after title change\n"
            f"      got     : {subject}"
        )
    max_len = int(cfg(cp, "git", "max_subject_length", "72") or 72)
    if len(subject) > max_len:
        errors.append(f"subject is {len(subject)} chars; max is {max_len}")
    if subject.endswith("."):
        errors.append("subject must not end with a period")
    keys = cfg_list(cp, "jira", "project_keys")
    found = re.findall(cfg(cp, "jira", "ticket_regex", r"[A-Z][A-Z0-9]+-[0-9]+"), subject)
    if keys and found and not any(k.split("-")[0] in keys for k in found):
        errors.append(f"ticket key {found[0]} is not in allowed projects: {', '.join(keys)}")
    m = re.match(r"^(\w+)", subject)
    ctype = m.group(1) if m else ""
    if ctype in cfg_list(cp, "git", "require_body_for"):
        body = [ln for ln in lines[1:] if ln.strip() and not ln.lower().startswith(("refs:", "co-authored-by:", "signed-off-by:"))]
        if not body:
            errors.append(f"'{ctype}' commits need a body explaining WHY (blank line after the subject, then the reason)")
    if len(lines) > 1 and lines[1].strip():
        errors.append("leave a blank line between the subject and the body")
    return errors


def protected(cp, branch: str) -> bool:
    return any(fnmatch.fnmatch(branch, pat) for pat in cfg_list(cp, "git", "protected_branches"))


def slugify(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "change"


# --------------------------------------------------------------------------
# quality gate
# --------------------------------------------------------------------------


def changed_files(cp, repo: Path) -> list[str]:
    files: set[str] = set()
    mb = merge_base(repo, target_branch(cp, repo))
    if mb:
        files.update(git(repo, "diff", "--name-only", "--diff-filter=ACMR", mb, "HEAD", check=False).splitlines())
    files.update(git(repo, "diff", "--name-only", "--diff-filter=ACMR", "HEAD", check=False).splitlines())
    files.update(git(repo, "ls-files", "--others", "--exclude-standard", check=False).splitlines())
    return sorted(f for f in files if f and (repo / f).exists())


def detect_test_command(repo: Path) -> str:
    for cand in ("bin/test", "bin/test.exe", "bin/test-script.py"):
        if (repo / cand).exists():
            return str(Path(cand))
    if shutil.which("zope-testrunner"):
        test_path = "src" if (repo / "src").is_dir() else "."
        return f"zope-testrunner --test-path {test_path}"
    if shutil.which("pytest") or (repo / "pytest.ini").exists() or (repo / "conftest.py").exists():
        return f"{sys.executable} -m pytest -q"
    return ""


def run_check(repo: Path, name: str, template: str, py_files: list[str]) -> dict:
    if not template:
        return {"check": name, "command": "", "status": "skipped", "details": "not configured"}
    if "{files}" in template and not py_files:
        return {"check": name, "command": template, "status": "skipped", "details": "no changed Python files"}
    packages = sorted({f.split("/")[0] for f in py_files})
    parts = []
    for tok in shlex.split(template, posix=os.name != "nt"):
        if tok == "{files}":
            parts.extend(py_files)
        elif tok == "{paths}":
            parts.extend(packages)
        else:
            parts.append(tok)
    exe = parts[0]
    if not (repo / exe).exists() and not shutil.which(exe):
        return {"check": name, "command": template, "status": "missing", "details": f"'{exe}' is not installed"}
    try:
        proc = subprocess.run(
            parts, cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return {"check": name, "command": template, "status": "fail", "details": "timed out after 30 min"}
    except OSError as exc:
        return {"check": name, "command": template, "status": "missing", "details": str(exc)}
    out = proc.stdout.strip().splitlines()
    tail = "\n".join(out[-40:])
    return {
        "check": name,
        "command": " ".join(parts[:6]) + (" …" if len(parts) > 6 else ""),
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "details": tail,
    }


def cmd_quality(cp, args) -> int:
    key = args.key
    repos = discover_repos(cp, args.repo) if args.repo else [r for r in discover_repos(cp) if changed_files(cp, r)]
    if not repos:
        print("sdlc: no repositories with changes found", file=sys.stderr)
        return 2
    required = set(cfg_list(cp, "quality", "required"))
    checks = ["lint", "format_check", "typecheck", "security", "tests"]
    report = {"ticket_key": key, "timestamp": _dt.datetime.now().isoformat(timespec="seconds"), "repos": []}
    overall = True
    for repo in repos:
        files = changed_files(cp, repo)
        py = [f for f in files if f.endswith(".py")]
        other = [f for f in files if f.endswith((".zcml", ".pt", ".zpt", ".xml", ".cfg"))]
        results = []
        for name in checks:
            template = cfg(cp, "quality", name)
            if name == "tests" and not template:
                template = detect_test_command(repo)
                if not template:
                    results.append({"check": "tests", "command": "", "status": "missing", "details": "no test runner found"})
                    continue
                res = run_check(repo, name, template.replace("{files}", ""), py or ["_"])
            else:
                res = run_check(repo, name, template, py)
            res["required"] = name in required
            results.append(res)
        repo_ok = all(not (r["required"] and r["status"] in ("fail", "missing")) for r in results)
        overall &= repo_ok
        report["repos"].append({
            "name": repo.name, "path": str(repo), "changed_files": files,
            "python_files": py, "config_or_template_files": other,
            "result": "PASS" if repo_ok else "FAIL", "checks": results,
        })
    report["result"] = "PASS" if overall else "FAIL"
    wd = ensure_workdir(cp, key)
    (wd / "quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    icon = {"pass": "✅ pass", "fail": "❌ fail", "skipped": "⏭ skipped", "missing": "⚠ missing"}
    data = {"ticket_key": key, "result": ("✅ PASS" if overall else "❌ FAIL"), "timestamp": report["timestamp"], "repos": []}
    for r in report["repos"]:
        rows = []
        for c in r["checks"]:
            detail = (c["details"].splitlines() or [""])[-1][:120].replace("|", "\\|")
            req = " (required)" if c.get("required") else ""
            rows.append(f"| {c['check']}{req} | `{c['command'] or '-'}` | {icon.get(c['status'], c['status'])} | {detail} |")
        data["repos"].append({"name": r["name"], "check_rows": "\n".join(rows)})
    fails = [f"- **{r['name']} / {c['check']}**: exit {c.get('exit_code', '-')}\n\n```\n{c['details'][-1500:]}\n```"
             for r in report["repos"] for c in r["checks"] if c["status"] == "fail"]
    data["findings"] = "\n".join(fails)
    text, _ = render_text(resolve_template(cp, "quality-report.md").read_text(encoding="utf-8"), data)
    (wd / "quality.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\n[sdlc] report written to {wd / 'quality.md'} and quality.json")
    return 0 if overall else 1


# --------------------------------------------------------------------------
# collect + summary
# --------------------------------------------------------------------------


def ensure_workdir(cp, key: str) -> Path:
    wd = workspace_root(cp) / cfg(cp, "workspace", "work_dir", ".sdlc") / key
    wd.mkdir(parents=True, exist_ok=True)
    return wd


def collect(cp, key: str, explicit: list[str] | None) -> dict:
    data = {"ticket_key": key, "generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "repos": []}
    for repo in discover_repos(cp, explicit):
        target = target_branch(cp, repo)
        base = base_ref(repo, target)
        rng = f"{base}..HEAD" if base else "HEAD"
        raw = git(repo, "log", rng, "--no-merges", f"--grep={key}", "--regexp-ignore-case",
                  "--format=%H%x1f%h%x1f%s%x1f%an%x1f%aI%x1e", check=False)
        commits = []
        files: set[str] = set()
        ins = dels = 0
        for rec in [r.strip() for r in raw.split("\x1e") if r.strip()]:
            sha, short, subject, author, date = rec.split("\x1f")
            stat = git(repo, "show", "--numstat", "--format=", sha, check=False)
            cfiles = []
            for line in stat.splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    a, d, f = parts
                    ins += int(a) if a.isdigit() else 0
                    dels += int(d) if d.isdigit() else 0
                    cfiles.append(f)
            files.update(cfiles)
            commits.append({"sha": sha, "short_sha": short, "subject": subject, "author": author,
                            "date": date, "files": cfiles})
        if not commits:
            continue
        commits.reverse()  # oldest first
        branch = current_branch(repo)
        web = remote_web_url(repo)
        upstream = git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch}", check=False)
        data["repos"].append({
            "name": repo.name, "path": str(repo), "branch": branch, "target": target,
            "web_url": web, "project_path": project_path(web),
            "pushed": bool(upstream) and upstream == git(repo, "rev-parse", "HEAD"),
            "commit_count": len(commits), "commits": commits,
            "files_changed": len(files), "files": sorted(files),
            "insertions": ins, "deletions": dels,
        })
    data["repo_count"] = len(data["repos"])
    data["commit_count"] = sum(r["commit_count"] for r in data["repos"])
    data["files_total"] = sum(r["files_changed"] for r in data["repos"])
    data["insertions_total"] = sum(r["insertions"] for r in data["repos"])
    data["deletions_total"] = sum(r["deletions"] for r in data["repos"])
    return data


def cmd_collect(cp, args) -> int:
    data = collect(cp, args.key, args.repo)
    wd = ensure_workdir(cp, args.key)
    (wd / "commits.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2) if args.json else _collect_text(data))
    print(f"\n[sdlc] written {wd / 'commits.json'}", file=sys.stderr)
    return 0 if data["repos"] else 3


def _collect_text(data: dict) -> str:
    if not data["repos"]:
        return f"No commits mentioning {data['ticket_key']} found on the current branches."
    out = [f"{data['ticket_key']}: {data['commit_count']} commit(s) in {data['repo_count']} repo(s)"]
    for r in data["repos"]:
        flag = "pushed" if r["pushed"] else "NOT pushed"
        out.append(f"\n{r['name']}  {r['branch']} -> {r['target']}  ({flag}, {r['files_changed']} files, +{r['insertions']}/-{r['deletions']})")
        out += [f"  {c['short_sha']} {c['subject']}" for c in r["commits"]]
    return "\n".join(out)


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"sdlc: {path} is not valid JSON: {exc}")
    return {}


def cmd_summary(cp, args) -> int:
    key = args.key
    wd = ensure_workdir(cp, key)
    commits = _load_json(wd / "commits.json") or collect(cp, key, None)
    narrative = _load_json(wd / "narrative.json")
    mrs = _load_json(wd / "mrs.json")
    site = cfg(cp, "jira", "site").rstrip("/")
    base = {
        "ticket_key": key,
        "ticket_url": f"{site}/browse/{key}" if site else key,
        "date": _dt.date.today().isoformat(),
        "timestamp": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "developer": narrative.get("developer") or git(Path.cwd(), "config", "user.name", check=False) or os.environ.get("USER", ""),
    }
    data = {**commits, **base, **narrative}
    for r in data.get("repos", []):
        mr = mrs.get(r["name"], {})
        r["mr_url"] = mr.get("url", "")
        r["mr_link"] = f"[!{mr.get('iid', '')}]({mr['url']})" if mr.get("url") else "_not created yet_"
    outputs = {}
    all_missing: set = set()
    summary, miss = render_text(resolve_template(cp, "consolidated-summary.md").read_text(encoding="utf-8"), data)
    outputs["summary.md"] = summary
    all_missing |= miss
    for r in data.get("repos", []):
        rd = {**data, **r, "repo_name": r["name"],
              "sibling_mrs": [{"repo": o["name"], "url": o.get("mr_url") or "_pending_"} for o in data["repos"] if o["name"] != r["name"]]}
        rd.update(narrative.get("per_repo", {}).get(r["name"], {}))
        text, miss = render_text(resolve_template(cp, "mr-description.md", r["path"]).read_text(encoding="utf-8"), rd)
        outputs[f"mr-{r['name']}.md"] = text
        all_missing |= miss
    text, miss = render_text(resolve_template(cp, "jira-impact-comment.md").read_text(encoding="utf-8"), data)
    outputs["qa-handoff.md"] = text
    all_missing |= miss
    if cfg_bool(cp, "notify", "teams_summary", True):
        text, miss = render_text(resolve_template(cp, "teams-update.md").read_text(encoding="utf-8"), data)
        outputs["teams.md"] = text
        all_missing |= miss
    for name, text in outputs.items():
        (wd / name).write_text(text, encoding="utf-8")
    print(f"[sdlc] wrote: {', '.join(outputs)} in {wd}")
    if all_missing:
        print("[sdlc] fields not provided (rendered as '—'): " + ", ".join(sorted(all_missing)))
        print(f"[sdlc] add them to {wd / 'narrative.json'} and run summary again.")
    return 0


def cmd_render(cp, args) -> int:
    tpath = Path(args.template)
    if not tpath.exists():
        tpath = resolve_template(cp, args.template, args.repo)
    data = json.loads(Path(args.data).read_text(encoding="utf-8")) if args.data else {}
    text, missing = render_text(tpath.read_text(encoding="utf-8"), data)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if missing:
        print("[sdlc] missing: " + ", ".join(sorted(missing)), file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# hooks
# --------------------------------------------------------------------------


def _posix(p) -> str:
    return str(p).replace("\\", "/")


def hook_scripts() -> dict:
    py = _posix(sys.executable)
    me = _posix(Path(__file__).resolve())
    return {
        "commit-msg": f"""#!/bin/sh
# {HOOK_MARKER}: enforce team commit format (edit config/toolkit.ini, not this file)
"{py}" "{me}" check-commit --message-file "$1"
""",
        "pre-push": f"""#!/bin/sh
# {HOOK_MARKER}: block pushes to protected branches
while read local_ref local_sha remote_ref remote_sha; do
  branch="${{remote_ref#refs/heads/}}"
  "{py}" "{me}" check-branch --branch "$branch" || exit 1
done
exit 0
""",
    }


def cmd_install_hooks(cp, args) -> int:
    manual = []
    for repo in discover_repos(cp, args.repo):
        hooks_path = git(repo, "config", "--get", "core.hooksPath", check=False)
        if hooks_path:
            manual.append(f"{repo.name}: core.hooksPath={hooks_path} is set (husky/pre-commit?). Add the toolkit commit-msg check there manually: "
                          f"\"{_posix(sys.executable)}\" \"{_posix(Path(__file__).resolve())}\" check-commit --message-file \"$1\"")
            continue
        hdir = Path(git(repo, "rev-parse", "--git-path", "hooks"))
        if not hdir.is_absolute():
            hdir = repo / hdir
        hdir.mkdir(parents=True, exist_ok=True)
        for name, body in hook_scripts().items():
            target = hdir / name
            before = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else None
            if before is not None and HOOK_MARKER not in before:
                manual.append(f"{repo.name}: existing {name} hook kept. Chain the toolkit hook into it manually (see USER_MANUAL.md > Hooks).")
                print(f"[sdlc] hook foreign {name} {_posix(target)}")
                continue
            target.write_text(body, encoding="utf-8", newline="\n")
            target.chmod(0o755)
            status = "installed" if before is None else ("unchanged" if before == body else "updated")
            print(f"[sdlc] hook {status} {name} {_posix(target)}")
        exclude = Path(git(repo, "rev-parse", "--git-path", "info/exclude"))
        if not exclude.is_absolute():
            exclude = repo / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        wd = cfg(cp, "workspace", "work_dir", ".sdlc")
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if f"/{wd}/" not in existing.splitlines():
            with exclude.open("a", encoding="utf-8") as fh:
                fh.write(f"\n# {HOOK_MARKER}\n/{wd}/\n")
        print(f"[sdlc] hooks installed in {repo}")
    for m in manual:
        print(f"[sdlc] MANUAL: {m}")
    return 0


# --------------------------------------------------------------------------
# Hook inventory: every hook the toolkit installs or that affects it
# --------------------------------------------------------------------------

HOOK_EVENTS = {"commit-msg": "git commit (checks the commit message format)",
               "pre-push": "git push (blocks pushes to protected branches)"}
# editor / agent hook configs that may hold hooks (the toolkit writes none; listed when they reference it or Orbit)
EDITOR_HOOK_FILES = (("Claude Code", ".claude/settings.json"), ("Gemini CLI", ".gemini/settings.json"),
                     ("Cursor", ".cursor/hooks.json"))


def _hook_dir(repo: Path) -> Path:
    hdir = Path(git(repo, "rev-parse", "--git-path", "hooks", check=False) or ".git/hooks")
    return hdir if hdir.is_absolute() else repo / hdir


def _manifest_repos() -> list[Path]:
    m = _load_json(TOOLKIT_HOME / "manifest.json") if (TOOLKIT_HOME / "manifest.json").exists() else {}
    return [Path(r) for r in m.get("hooks", []) if r]


def git_hook_inventory(cp, repos: list[Path] | None = None) -> list[dict]:
    """State of the toolkit's git hooks in every workspace repo (and every repo it ever hooked)."""
    if repos is None:
        try:
            repos = discover_repos(cp)
        except SystemExit:
            repos = []
        repos = repos + [r for r in _manifest_repos() if r not in repos]
    wanted = hook_scripts()
    out = []
    glob_path = git(Path.cwd(), "config", "--global", "--get", "core.hooksPath", check=False) if shutil.which("git") else ""
    if glob_path:
        out.append({"name": "core.hooksPath", "type": "git config (global)", "event": "all git hooks of every repo",
                    "path": glob_path, "repo": "", "status": "external",
                    "note": "a global hooks folder replaces .git/hooks in every repo: the toolkit hooks are not used"})
    for repo in repos:
        if not is_repo(repo):
            for name in wanted:
                out.append({"name": name, "type": "git hook", "event": HOOK_EVENTS[name], "repo": str(repo),
                            "path": _posix(repo / ".git" / "hooks" / name), "status": "missing",
                            "note": "repo no longer exists"})
            continue
        local = git(repo, "config", "--get", "core.hooksPath", check=False)
        hdir = _hook_dir(repo)
        for name, body in wanted.items():
            row = {"name": name, "type": "git hook", "event": HOOK_EVENTS[name], "repo": str(repo)}
            if local:
                target = Path(local) if Path(local).is_absolute() else repo / local
                row.update(path=_posix(target / name), status="skipped",
                           note=f"core.hooksPath={local} (husky/pre-commit?): add the toolkit check there by hand")
            else:
                target = hdir / name
                text = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else None
                row["path"] = _posix(target)
                if text is None:
                    row["status"] = "missing"
                elif HOOK_MARKER not in text:
                    row.update(status="foreign", note="your own hook, kept; chain the toolkit check into it")
                elif text != body:
                    used = re.findall(r'"([^"]*sdlc\.py)"', text)
                    if used and all(Path(u).exists() for u in used):
                        row.update(status="installed", note=f"runs {used[0]}")
                    else:
                        row.update(status="outdated", note="points at a helper that no longer exists: run install-hooks")
                else:
                    row["status"] = "installed"
            out.append(row)
    return out


def _walk_hook_commands(node, event=None):
    """(event, command) pairs from Claude/Gemini/Cursor style hook configs."""
    if isinstance(node, dict):
        if isinstance(node.get("command"), str):
            yield event, node["command"]
        for k, v in node.items():
            if k != "command":
                yield from _walk_hook_commands(v, event or k)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_hook_commands(v, event)


def editor_hook_inventory(home: Path | None = None) -> list[dict]:
    home = home or Path.home()
    out = []
    for editor, rel in EDITOR_HOOK_FILES:
        path = home / rel
        hooks = _load_json(path).get("hooks") if path.exists() else None
        if not hooks:
            continue
        for event, command in _walk_hook_commands(hooks):
            low = command.lower()
            if HOOK_MARKER in low or "sdlc.py" in low or "orbit" in low:
                ours = HOOK_MARKER in low or "sdlc.py" in low
                out.append({"name": redact(command)[:120], "type": f"editor hook ({editor})", "event": event or "?",
                            "path": _posix(path), "repo": "", "status": "installed" if ours else "external",
                            "note": "" if ours else "not written by the toolkit (e.g. `orbit setup`)"})
    return out


def hook_inventory(cp, repos: list[Path] | None = None, home: Path | None = None) -> list[dict]:
    return git_hook_inventory(cp, repos) + editor_hook_inventory(home)


HOOKS_NONE_NOTE = ("The toolkit installs only git hooks (commit-msg, pre-push) in workspace repos. It installs no "
                   "global git hooks, editor/agent hooks, shell hooks or scheduled jobs.")


def render_hooks(rows: list[dict], markdown: bool = True) -> str:
    if not rows:
        return "No hooks found (no git repos in the workspace yet).\n" + HOOKS_NONE_NOTE
    lines = []
    if markdown:
        lines += ["| Hook | Type | Trigger | Status | Path |", "|---|---|---|---|---|"]
        for r in rows:
            st = r["status"] + (f" - {r['note']}" if r.get("note") else "")
            lines.append(f"| `{r['name']}` | {r['type']} | {r['event']} | {st} | `{r['path']}` |")
    else:
        for r in rows:
            lines.append(f"- {r['name']:<14} {r['type']:<20} {r['status']:<10} {r['path']}")
            lines.append(f"    trigger: {r['event']}" + (f"; {r['note']}" if r.get("note") else ""))
    lines += ["", HOOKS_NONE_NOTE]
    return "\n".join(lines)


def cmd_hooks(cp, args) -> int:
    rows = hook_inventory(cp, discover_repos(cp, args.repo) if args.repo else None)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(render_hooks(rows, markdown=args.markdown))
    return 0 if all(r["status"] in ("installed", "unchanged", "updated", "external") for r in rows) else 1


# --------------------------------------------------------------------------
# simple commands
# --------------------------------------------------------------------------


def cmd_config(cp, args) -> int:
    data = {s: dict(cp.items(s)) for s in cp.sections()}
    data["_resolved"] = {"toolkit_home": str(TOOLKIT_HOME), "workspace_root": str(workspace_root(cp)),
                         "config_files": [str(f) for f in _config_files()], "python": sys.executable}
    print(json.dumps(data, indent=2))
    return 0


def cmd_template(cp, args) -> int:
    p = resolve_template(cp, args.name, args.repo)
    print(f"<!-- template: {p} -->")
    print(p.read_text(encoding="utf-8"))
    return 0


def cmd_repos(cp, args) -> int:
    rows = []
    for repo in discover_repos(cp, args.repo):
        rows.append({
            "name": repo.name, "path": str(repo), "branch": current_branch(repo),
            "target": target_branch(cp, repo),
            "dirty": bool(git(repo, "status", "--porcelain", check=False)),
            "web_url": remote_web_url(repo),
        })
    print(json.dumps(rows, indent=2))
    return 0


def cmd_workdir(cp, args) -> int:
    print(ensure_workdir(cp, args.key))
    return 0


BRANCH_TYPE_ALIASES = {"feat": "feature", "fix": "bugfix", "poc": "spike", "bug": "bugfix"}


def default_branch_user(repo: Path | None = None) -> str:
    name = ""
    try:
        name = git(repo or Path("."), "config", "user.name", check=False).strip()
    except Exception:
        pass
    return slugify(name.split()[0] if name else os.environ.get("USER", "dev"), 20)


def cmd_branch_name(cp, args) -> int:
    pattern = cfg(cp, "git", "branch_pattern", "{type}/{user}/{key}")
    types = cfg_list(cp, "git", "branch_types") or ["feature", "bugfix", "spike", "refactor", "chore"]
    btype = BRANCH_TYPE_ALIASES.get(args.type, args.type)
    if btype not in types:
        raise RuntimeError(f"branch type '{btype}' not allowed; use one of: {', '.join(types)}")
    if btype == "spike":
        if not args.poc:
            raise RuntimeError("spike branches need --poc <poc_name>, e.g. spike/py3/JIVA66-9988")
        user = slugify(args.poc, 30)
    else:
        user = slugify(args.user, 20) if args.user else default_branch_user()
    print(pattern.format(type=btype, user=user, key=args.key, slug=slugify(args.title or "")))
    return 0


def cmd_check_branch(cp, args) -> int:
    branch = args.branch or current_branch(Path(args.repo or ".").resolve())
    if protected(cp, branch):
        print(f"[sdlc] '{branch}' is a protected branch. Create a ticket branch first "
              f"(python sdlc.py branch-name KEY --type bugfix).", file=sys.stderr)
        return 1
    types = cfg_list(cp, "git", "branch_types")
    key_re = cfg(cp, "jira", "ticket_regex", r"[A-Z][A-Z0-9]+-[0-9]+")
    if types and not re.match(rf"^({'|'.join(map(re.escape, types))})/[^/]+/{key_re}$", branch):
        print(f"[sdlc] note: '{branch}' does not follow <type>/<username>/<KEY> "
              f"(types: {', '.join(types)}). Working on it anyway.", file=sys.stderr)
    print(f"[sdlc] branch '{branch}' OK")
    return 0


def cmd_check_commit(cp, args) -> int:
    msg = args.message if args.message is not None else Path(args.message_file).read_text(encoding="utf-8", errors="replace")
    errors = check_commit_message(cp, msg)
    if errors:
        print("\n✖ Commit rejected by team rules (sdlc-ai-toolkit):", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        print("   Fix the message, or ask the Release Scribe agent to write it.\n", file=sys.stderr)
        return 1
    if args.message is not None:
        print("✔ commit message OK")
    return 0


# --------------------------------------------------------------------------
# GitLab Orbit (code knowledge graph, one graph per workspace folder)
# --------------------------------------------------------------------------


def orbit_command() -> list[str] | None:
    found = shutil.which("orbit")
    if not found and shutil.which("npm"):
        # npm's global bin dir is not always on PATH (e.g. user-level node installs)
        prefix = subprocess.run(["npm", "prefix", "-g"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()
        for cand in (Path(prefix) / "bin" / "orbit", Path(prefix) / "orbit.cmd"):
            if prefix and cand.exists():
                found = str(cand)
                break
    if found:
        return [found]
    if shutil.which("glab"):
        return ["glab", "orbit"]
    return None


def orbit_folder(cp, args) -> Path:
    """The workspace folder whose graph is used: --folder, else the folder
    containing the cwd (a configured root wins), else the cwd itself."""
    if getattr(args, "folder", None):
        return Path(args.folder).expanduser().resolve()
    env = os.environ.get("SDLC_WORKSPACE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    roots = [Path(r.strip()).expanduser().resolve() for r in cfg(cp, "workspace", "roots", "").split(",") if r.strip()]
    root = workspace_root(cp)
    for r in roots + [root]:
        if cwd == r or r in cwd.parents:
            return r
    return cwd


def orbit_env(cp, folder: Path) -> dict:
    data = folder / cfg(cp, "workspace", "work_dir", ".sdlc") / "orbit"
    data.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ORBIT_DATA_DIR=str(data))
    env["ORBIT_TELEMETRY_ENABLED"] = "true" if cfg_bool(cp, "orbit", "telemetry", False) else "false"
    return env


def cmd_orbit(cp, args) -> int:
    base = orbit_command()
    if not base:
        print("sdlc: Orbit CLI not found. Install: npm install -g @gitlab/orbit  (or: glab, see docs/USER_MANUAL.md)",
              file=sys.stderr)
        return 2
    folder = orbit_folder(cp, args)
    env = orbit_env(cp, folder)
    print(f"[sdlc] orbit graph for workspace folder {folder} ({env['ORBIT_DATA_DIR']})", file=sys.stderr)
    action = args.action
    extra = [a for a in args.rest if a != "--"]
    cwd = folder
    if args.repo:
        cwd = Path(args.repo).expanduser().resolve()
    if action == "index":
        cmd = base + ["workspace", "index", str(folder)] + extra
    elif action == "list":
        cmd = base + ["workspace", "list"] + extra
    elif action == "status":  # local graph state (`orbit status` would ask the GitLab API)
        cmd = base + ["workspace", "list"] + extra
    elif action in ("grep", "context"):
        cmd = base + [action] + extra
        if cwd == folder and not is_repo(folder):
            print("[sdlc] note: folder holds several repos; pass --repo <path> to search one, "
                  "or run `orbit index` first and use paths.", file=sys.stderr)
    else:
        print(f"sdlc: unknown orbit action {action}", file=sys.stderr)
        return 2
    return subprocess.run(cmd, cwd=str(cwd), env=env).returncode


# --------------------------------------------------------------------------
# Setup checks: Orbit preflight (gate for ticket work) + post-install checklist
# All checks are non-interactive, time out quickly and never print secrets.
# --------------------------------------------------------------------------

ORBIT_INSTALL_CMD = "npm install -g @gitlab/orbit"
_INDEXING = ("indexing", "pending", "queued", "running", "in_progress", "in-progress", "started")
_URL_CREDS = re.compile(r"(\w+://)[^/@\s]+@")


def self_command() -> str:
    """How to call this helper CLI again (shown in hints)."""
    script = Path(__file__).resolve().as_posix()
    if os.name == "nt":
        launcher = "py -3" if shutil.which("py") else "python"
    else:
        exe = sys.executable
        launcher = exe if exe and " " not in exe else "python3"
    return f'{launcher} "{script}"'


def redact(text: str) -> str:
    """Strip credentials embedded in URLs (https://user:token@host)."""
    return _URL_CREDS.sub(r"\1***@", text or "")


def checks_offline(args=None) -> bool:
    return bool(getattr(args, "offline", False)) or os.environ.get("SDLC_CHECKS_OFFLINE", "") in ("1", "yes", "true")


def _home_or_root(p: Path) -> bool:
    try:
        home = Path.home().resolve()
    except (RuntimeError, KeyError):
        home = None
    return p == home or p == Path(p.anchor)


def _orbit_rows(base: list[str], data: Path, folder: Path, timeout: int = 30) -> list[dict] | None:
    """Indexed repos in the folder's graph; None when the CLI could not answer."""
    if not data.is_dir() or not any(data.iterdir()):
        return []
    env = dict(os.environ, ORBIT_DATA_DIR=str(data), ORBIT_TELEMETRY_ENABLED="false", ORBIT_NO_GITLAB="1")
    try:
        proc = subprocess.run(base + ["workspace", "list", "-F", "json"], cwd=str(folder), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError:
        return None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None


def orbit_state(cp, folder: Path) -> dict:
    """Is Orbit installed, and is every repo of this workspace folder indexed?

    state: disabled | not-installed | no-folder | no-repos | not-indexed | partial | indexing | unknown | indexed
    ok: True when ticket work can go ahead without extra token cost."""
    sdlc = self_command()
    index_cmd = f'{sdlc} orbit index --folder "{folder.as_posix()}"'
    st = {"name": "orbit", "folder": str(folder), "install_cmd": ORBIT_INSTALL_CMD, "index_cmd": index_cmd,
          "indexed": [], "missing": [], "cli": None}
    if not cfg_bool(cp, "orbit", "enabled", True):
        return dict(st, state="disabled", ok=True, summary="Orbit is turned off in the team config ([orbit] enabled = no).")
    base = orbit_command()
    st["cli"] = " ".join(base) if base else None
    if not base:
        return dict(st, state="not-installed", ok=False,
                    summary="GitLab Orbit CLI is not installed.",
                    steps=[f"Install it (needs Node.js): {ORBIT_INSTALL_CMD}",
                           f"Then index this workspace folder: {index_cmd}"])
    if _home_or_root(folder):
        return dict(st, state="no-folder", ok=False,
                    summary=f"{folder} is your home directory / the filesystem root, not a workspace folder.",
                    steps=["Open the folder that holds your repos in the editor (or cd into it)",
                           f'Then run: {sdlc} orbit index --folder "<folder with your repos>"'])
    old = os.environ.get("SDLC_WORKSPACE_ROOT")
    os.environ["SDLC_WORKSPACE_ROOT"] = str(folder)
    try:
        repos = [folder] if is_repo(folder) else discover_repos(cp)
    finally:
        if old is None:
            os.environ.pop("SDLC_WORKSPACE_ROOT", None)
        else:
            os.environ["SDLC_WORKSPACE_ROOT"] = old
    if not repos:
        return dict(st, state="no-repos", ok=True, summary=f"No git repositories under {folder}; nothing to index yet.",
                    steps=[f"After cloning your repos there, run: {index_cmd}"])
    data = folder / cfg(cp, "workspace", "work_dir", ".sdlc") / "orbit"
    rows = _orbit_rows(base, data, folder)
    if rows is None:
        return dict(st, state="unknown", ok=False, summary="Could not read the Orbit graph (the CLI failed or timed out).",
                    steps=[f"Re-index this workspace folder: {index_cmd}"])
    by_path = {}
    for r in rows:
        try:
            by_path[str(Path(str(r.get("repo_path", ""))).resolve())] = r
        except (OSError, ValueError):
            continue
    indexed = [str(p) for p in repos if str(p.resolve()) in by_path]
    missing = [str(p) for p in repos if str(p.resolve()) not in by_path]
    busy = [p for p in indexed if str(by_path[str(Path(p).resolve())].get("status", "")).lower() in _INDEXING]
    st.update(indexed=indexed, missing=missing)
    if not indexed:
        return dict(st, state="not-indexed", ok=False,
                    summary=f"Orbit is installed but {folder} is not indexed yet ({len(repos)} repo(s)).",
                    steps=[f"Index it (one time, then incremental): {index_cmd}"])
    if busy and not missing:
        return dict(st, state="indexing", ok=False,
                    summary=f"Orbit is still indexing {len(busy)} repo(s) in {folder}.",
                    steps=[f"Wait until it finishes (check: {sdlc} orbit status), or run it in the foreground: {index_cmd}"])
    if missing:
        return dict(st, state="partial", ok=False,
                    summary=f"{len(missing)} of {len(repos)} repo(s) in {folder} are not indexed: "
                            + ", ".join(Path(m).name for m in missing),
                    steps=[f"Index the workspace folder again (incremental): {index_cmd}"])
    return dict(st, state="indexed", ok=True, summary=f"{len(indexed)} repo(s) indexed in {data}.")


_GIT_BATCH = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": "",
              "SSH_ASKPASS": "", "SSH_ASKPASS_REQUIRE": "never"}


def _remote_host(url: str) -> tuple[str, str]:
    """(scheme, host) of a git remote URL; scheme is ssh | https | http | file."""
    m = re.match(r"^(\w+)://(?:[^@/]+@)?([^/:]+)", url)
    if m:
        return m.group(1).lower(), m.group(2).lower()
    m = re.match(r"^(?:[^@/]+@)?([^/:]+):(?!/)", url)  # scp-like git@host:group/repo.git
    if m and not re.match(r"^[A-Za-z]:[\\/]", url):
        return "ssh", m.group(1).lower()
    return "file", ""


def _git_noninteractive_env(repo: Path | None) -> dict:
    env = dict(os.environ, **_GIT_BATCH)
    custom = os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH")
    if not custom and repo is not None:
        custom = git(repo, "config", "--get", "core.sshCommand", check=False)
    if not custom:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=8"
    return env


def git_auth_state(cp, folder: Path, offline: bool = False, timeout: int = 15) -> dict:
    """Can git reach the remotes of this workspace without asking for a password?"""
    st = {"name": "git", "checked": []}
    gl_host = _remote_host(cfg(cp, "gitlab", "url", "https://gitlab.com"))[1] or "gitlab.com"
    steps_ssh = [f"SSH (recommended): ssh-keygen -t ed25519   then add ~/.ssh/id_ed25519.pub in GitLab > Preferences > SSH Keys",
                 f"Check: ssh -T git@{gl_host}   (accept the host key once)"]
    steps_https = ["HTTPS: create a GitLab personal access token (scopes read_repository, write_repository)",
                   "Store it with a credential helper: git config --global credential.helper manager "
                   "(Windows/macOS Git Credential Manager; or osxkeychain / libsecret), then run any git fetch once "
                   "and enter your user name + the token"]
    if offline:
        return dict(st, state="unverified", ok=False, summary="Not checked (offline mode).",
                    steps=[f"Check later with: {self_command()} checklist"])
    if not shutil.which("git"):
        return dict(st, state="pending", ok=False, summary="git is not installed / not on PATH.",
                    steps=["Install Git, then re-run the installer"])
    old = os.environ.get("SDLC_WORKSPACE_ROOT")
    os.environ["SDLC_WORKSPACE_ROOT"] = str(folder)
    try:
        repos = [] if _home_or_root(folder) or not folder.exists() else ([folder] if is_repo(folder) else discover_repos(cp))
    except SystemExit:
        repos = []
    finally:
        if old is None:
            os.environ.pop("SDLC_WORKSPACE_ROOT", None)
        else:
            os.environ["SDLC_WORKSPACE_ROOT"] = old
    seen, todo = set(), []
    for repo in repos:
        remotes = git(repo, "remote", check=False).split()
        if not remotes:
            continue
        name = "origin" if "origin" in remotes else remotes[0]
        url = git(repo, "remote", "get-url", name, check=False)
        key = _remote_host(url)
        if not url or key in seen:
            continue
        seen.add(key)
        todo.append((repo, name, url, key))
        if len(todo) >= 5:
            break
    if not todo:
        if shutil.which("ssh"):
            try:
                p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-T", f"git@{gl_host}"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                   env=dict(os.environ, **{k: v for k, v in _GIT_BATCH.items() if k.startswith("SSH")}))
                if "welcome" in p.stdout.lower():
                    return dict(st, state="done", ok=True, summary=f"SSH key accepted by {gl_host} (no repos found to test yet).")
            except (OSError, subprocess.TimeoutExpired):
                pass
        return dict(st, state="pending", ok=False,
                    summary=f"No repo remotes to test under {folder}, and SSH to {gl_host} was not accepted.",
                    steps=steps_ssh + steps_https)
    bad = []
    for repo, name, url, (scheme, host) in todo:
        label = f"{host or 'local'} ({scheme})"
        try:
            p = subprocess.run(["git", "-c", "credential.interactive=never", "-C", str(repo), "ls-remote", "--heads", name],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout,
                               env=_git_noninteractive_env(repo))
            good, why = p.returncode == 0, redact((p.stderr.strip().splitlines() or [""])[-1])[:200]
        except subprocess.TimeoutExpired:
            good, why = False, f"timed out after {timeout}s"
        except OSError as exc:
            good, why = False, str(exc)
        st["checked"].append({"remote": label, "repo": repo.name, "ok": good, **({} if good else {"error": why})})
        if not good:
            bad.append((label, scheme, why))
    if not bad:
        return dict(st, state="done", ok=True,
                    summary="git can reach " + ", ".join(c["remote"] for c in st["checked"]) + " without a prompt.")
    steps = []
    if any(s == "ssh" for _, s, _ in bad):
        steps += steps_ssh
    if any(s in ("https", "http") for _, s, _ in bad):
        steps += steps_https
    steps.append(f"Re-check with: {self_command()} checklist")
    return dict(st, state="pending", ok=False,
                summary="git could not authenticate to " + "; ".join(f"{l}: {w}" if w else l for l, _, w in bad), steps=steps)


_JIRA_TOKEN_VARS = ("JIRA_API_TOKEN", "ATLASSIAN_API_TOKEN")
_JIRA_USER_VARS = ("JIRA_EMAIL", "JIRA_USER", "ATLASSIAN_EMAIL", "ATLASSIAN_USER")


def jira_auth_state(cp, offline: bool = False, timeout: int = 8, opener=None) -> dict:
    """Jira is reached through the Atlassian MCP server (OAuth kept by the editor).
    An API token in the environment, if present, is verified with /rest/api/3/myself."""
    import base64
    import urllib.error
    import urllib.request
    st = {"name": "jira"}
    site = cfg(cp, "jira", "site", "").rstrip("/")
    sign_in = ["Sign in once: VS Code > Command Palette > `MCP: List Servers` > `atlassian` > Start Server > approve "
               "in the browser (other editors: start the `atlassian` MCP server, e.g. `/mcp` in Claude Code / Gemini CLI)",
               "Confirm: ask the agent to call the Atlassian tool `atlassianUserInfo` (it shows your Jira user)"]
    if not site or "your-company" in site:
        return dict(st, state="pending", ok=False, summary="Jira site is not configured yet.",
                    steps=["python install.py --set jira.site=https://<your-site>.atlassian.net --set jira.project_keys=<KEY>"]
                    + sign_in)
    token = next((os.environ[v] for v in _JIRA_TOKEN_VARS if os.environ.get(v)), "")
    user = next((os.environ[v] for v in _JIRA_USER_VARS if os.environ.get(v)), "")
    if not token or not user:
        return dict(st, state="unverified", ok=False,
                    summary=f"{site}: the Atlassian MCP sign-in is stored inside your editor and cannot be checked from "
                            "here. If you already signed in, you're done.",
                    steps=sign_in)
    if offline:
        return dict(st, state="unverified", ok=False, summary="Jira API token found but not checked (offline mode).",
                    steps=[f"Check later with: {self_command()} checklist"])
    auth = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(f"{site}/rest/api/3/myself",
                                 headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
        who = body.get("displayName") or body.get("emailAddress") or "your account"
        return dict(st, state="done", ok=True, summary=f"Jira API token works for {site} (signed in as {who}).",
                    steps=["The agents still use the `atlassian` MCP server: sign in there once too if you have not"])
    except urllib.error.HTTPError as exc:
        why = f"HTTP {exc.code}" + (" - token or e-mail rejected" if exc.code in (401, 403) else "")
    except Exception as exc:  # network, TLS, timeout, bad JSON
        why = f"{type(exc).__name__}: {redact(str(exc))[:120]}"
    return dict(st, state="pending", ok=False, summary=f"Jira API check against {site} failed ({why}).",
                steps=["Create a new token at https://id.atlassian.com/manage-profile/security/api-tokens and set "
                       "JIRA_API_TOKEN + JIRA_EMAIL in your environment (never in toolkit.ini)"] + sign_in)


CHECK_TITLES = {
    "orbit": "Orbit code index (MANDATORY - required to save tokens)",
    "git": "Git authentication",
    "jira": "Jira authentication",
}
_MARK = {"done": "[x]", "indexed": "[x]", "disabled": "[x]", "no-repos": "[x]", "unverified": "[?]", "indexing": "[~]"}


def checklist(cp, folder: Path, offline: bool = False) -> list[dict]:
    items = [orbit_state(cp, folder), git_auth_state(cp, folder, offline), jira_auth_state(cp, offline)]
    for it in items:
        it["title"] = CHECK_TITLES[it["name"]]
        if it["name"] == "orbit" and it["state"] == "no-repos":
            it["ok"] = False  # ticket work may go ahead, but the mandatory index is still to do
        it["mark"] = "[x]" if it["ok"] else _MARK.get(it["state"], "[ ]")
    return items


def render_checklist(items: list[dict]) -> str:
    out = []
    for i, it in enumerate(items, 1):
        out.append(f"{i}. {it['mark']} **{it['title']}** - {it['summary']}")
        if not it["ok"]:
            out += [f"   - {s}" for s in it.get("steps", [])]
    return "\n".join(out)


def _checks_folder(cp, args) -> Path:
    if getattr(args, "folder", None):
        return Path(args.folder).expanduser().resolve()
    folder = orbit_folder(cp, args)
    if _home_or_root(folder) and workspace_root(cp).is_dir():
        return workspace_root(cp)  # run from ~: use the configured workspace root
    return folder


def cmd_preflight(cp, args) -> int:
    """Gate for every ticket workflow: Orbit installed and this folder indexed."""
    st = orbit_state(cp, _checks_folder(cp, args))
    if args.json:
        print(json.dumps(st, indent=2))
        return 0 if st["ok"] else 3
    if st["ok"]:
        print(f"[sdlc] preflight OK - Orbit: {st['summary']}")
        return 0
    print("[sdlc] PREFLIGHT STOP - Orbit code index missing (needed to save tokens)")
    print(f"  {st['summary']}")
    for s in st.get("steps", []):
        print(f"  -> {s}")
    print("  Without the index the agent has to read many more files to analyse the ticket, which costs far more tokens.")
    print("  Ask the developer to run the command above (or let you run it), or to say explicitly "
          "'proceed without Orbit'.")
    return 3


def cmd_checklist(cp, args) -> int:
    items = checklist(cp, _checks_folder(cp, args), checks_offline(args))
    if args.json:
        print(json.dumps(items, indent=2))
    else:
        print("Post-install checklist\n")
        print(render_checklist(items))
        print("\n[x] done  [ ] to do  [~] in progress  [?] could not be verified automatically")
    return 0 if all(i["ok"] for i in items) else 1


# --------------------------------------------------------------------------
# Work journal: one personal, cross-workspace log of work per ticket
# --------------------------------------------------------------------------

ACTIVITIES = ("understanding", "impact-analysis", "planning", "development", "bugfix", "refactor",
              "testing", "quality-gate", "code-review", "commit", "merge-request", "jira-update",
              "spike", "investigation", "other")
ACTIVITY_ALIASES = {"impact": "impact-analysis", "analysis": "impact-analysis", "dev": "development",
                    "implement": "development", "implementation": "development", "fix": "bugfix",
                    "quality": "quality-gate", "mr": "merge-request", "review": "code-review",
                    "plan": "planning", "test": "testing", "poc": "spike", "debug": "investigation"}


def journal_path(cp) -> Path:
    env = os.environ.get("SDLC_JOURNAL")
    if env:
        return Path(env).expanduser()
    custom = cfg(cp, "journal", "path", "")
    if custom:
        return Path(custom).expanduser()
    return TOOLKIT_HOME.parent / "sdlc-journal" / "worklog.jsonl"


def read_journal(cp) -> list[dict]:
    path = journal_path(cp)
    rows: list[dict] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ticket") and row.get("ts"):
            rows.append(row)
    return rows


def cmd_log(cp, args) -> int:
    if not cfg_bool(cp, "journal", "enabled", True):
        print("sdlc: work journal disabled ([journal] enabled = no)")
        return 0
    key = args.key.upper()
    activity = ACTIVITY_ALIASES.get(args.activity.lower(), args.activity.lower())
    if activity not in ACTIVITIES:
        sys.exit(f"sdlc: unknown activity '{args.activity}'. Use one of: {', '.join(ACTIVITIES)}")
    summary = " ".join(args.summary.split())
    if not summary:
        sys.exit("sdlc: --summary is required (one or two short sentences)")
    now = _dt.datetime.now().astimezone()
    entry = {
        "ts": now.isoformat(timespec="seconds"),
        "ticket": key,
        "title": args.title or "",
        "activity": activity,
        "summary": summary,
        "status": args.status or "",
        "repos": [r for r in (args.repos or "").split(",") if r.strip()],
        "branch": args.branch or "",
        "workspace": str(workspace_root(cp)),
    }
    path = journal_path(cp)
    for row in read_journal(cp):
        if (row["ticket"], row.get("activity"), row.get("summary")) == (key, activity, summary) \
                and row["ts"][:10] == entry["ts"][:10]:
            print(f"[sdlc] already logged today: {key} {activity}")
            return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[sdlc] logged {key} {activity} -> {path}")
    return 0


def period_range(period: str, today: _dt.date | None = None) -> tuple[_dt.date, _dt.date]:
    d = today or _dt.date.today()
    p = period.lower()
    if p == "today":
        return d, d
    if p == "yesterday":
        y = d - _dt.timedelta(days=1)
        return y, y
    if p == "week":
        s = d - _dt.timedelta(days=d.weekday())
        return s, s + _dt.timedelta(days=6)
    if p == "last-week":
        s = d - _dt.timedelta(days=d.weekday() + 7)
        return s, s + _dt.timedelta(days=6)
    if p in ("month", "last-month"):
        first = d.replace(day=1)
        if p == "last-month":
            first = (first - _dt.timedelta(days=1)).replace(day=1)
        nxt = (first.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
        return first, nxt - _dt.timedelta(days=1)
    if p in ("year", "last-year"):
        yr = d.year - (1 if p == "last-year" else 0)
        return _dt.date(yr, 1, 1), _dt.date(yr, 12, 31)
    if p == "all":
        return _dt.date(1970, 1, 1), _dt.date(9999, 12, 31)
    sys.exit("sdlc: --period must be today, yesterday, week, last-week, month, last-month, year, last-year or all")


def journal_select(cp, args) -> tuple[list[dict], _dt.date, _dt.date]:
    start, end = period_range(args.period or "week")
    if args.date_from:
        start = _dt.date.fromisoformat(args.date_from)
    if args.date_to:
        end = _dt.date.fromisoformat(args.date_to)
    rows = []
    for r in read_journal(cp):
        day = _dt.date.fromisoformat(r["ts"][:10])
        if not (start <= day <= end):
            continue
        if args.ticket and r["ticket"] != args.ticket.upper():
            continue
        if getattr(args, "activity", None) and r.get("activity") != ACTIVITY_ALIASES.get(args.activity, args.activity):
            continue
        rows.append(r)
    rows.sort(key=lambda r: r["ts"])
    return rows, start, end


def cmd_worklog(cp, args) -> int:
    rows, start, end = journal_select(cp, args)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    print(f"Journal: {journal_path(cp)}  ({start} .. {end}, {len(rows)} entries)")
    for r in rows:
        print(f"{r['ts'][:16].replace('T', ' ')}  {r['ticket']:<12} {r.get('activity', ''):<16} {r.get('summary', '')}")
    return 0


def render_report(rows: list[dict], start: _dt.date, end: _dt.date, period: str, by: str) -> str:
    title = {r["ticket"]: r["title"] for r in rows if r.get("title")}
    out = [f"# Work report: {period} ({start} to {end})", ""]
    if not rows:
        out.append("No work recorded for this period.")
        return "\n".join(out) + "\n"
    tickets = sorted({r["ticket"] for r in rows})
    days = sorted({r["ts"][:10] for r in rows})
    acts: dict[str, int] = {}
    for r in rows:
        acts[r.get("activity", "other")] = acts.get(r.get("activity", "other"), 0) + 1
    out += [f"**{len(tickets)} tickets, {len(days)} active days, {len(rows)} activities.**",
            "Activities: " + ", ".join(f"{a} x{n}" for a, n in sorted(acts.items(), key=lambda x: -x[1])), ""]

    def label(k: str) -> str:
        return f"{k} - {title[k]}" if k in title else k

    def line(r: dict, show_ticket: bool, show_day: bool) -> str:
        bits = [r["ts"][:10] if show_day else r["ts"][11:16]]
        if show_ticket:
            bits.append(r["ticket"])
        bits.append(f"**{r.get('activity', '')}**")
        text = " ".join(str(b) for b in bits) + f": {r.get('summary', '')}"
        extra = []
        if r.get("repos"):
            extra.append("repos: " + ", ".join(r["repos"]))
        if r.get("status"):
            extra.append("status: " + r["status"])
        return "- " + text + (f" ({'; '.join(extra)})" if extra else "")

    if by == "day":
        for day in days:
            out += [f"## {day} ({_dt.date.fromisoformat(day).strftime('%A')})", ""]
            out += [line(r, True, False) for r in rows if r["ts"][:10] == day]
            out.append("")
    else:
        for k in tickets:
            mine = [r for r in rows if r["ticket"] == k]
            out += [f"## {label(k)}", f"First worked {mine[0]['ts'][:10]}, last {mine[-1]['ts'][:10]}, {len(mine)} activities", ""]
            out += [line(r, False, True) for r in mine]
            out.append("")
    return "\n".join(out)


def cmd_report(cp, args) -> int:
    rows, start, end = journal_select(cp, args)
    text = render_report(rows, start, end, args.period or "week", args.by)
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        print(f"[sdlc] report written to {args.out}")
    else:
        print(text)
    return 0


def cmd_doctor(cp, args) -> int:
    ok = True
    def line(good, text):
        nonlocal ok
        ok &= good
        print(("  ✅ " if good else "  ⚠  ") + text)
    print(f"SDLC toolkit at {TOOLKIT_HOME}")
    line(sys.version_info >= (3, 8), f"Python {sys.version.split()[0]}")
    line(bool(shutil.which("git")), "git on PATH")
    site = cfg(cp, "jira", "site")
    line("your-company" not in site, f"Jira site configured ({site})")
    line(cfg(cp, "gitlab", "group") != "your-group", f"GitLab group configured ({cfg(cp, 'gitlab', 'group')})")
    root = workspace_root(cp)
    line(root.exists(), f"workspace root exists ({root})")
    home = TOOLKIT_HOME.parent
    line((home / "agents").exists() and any((home / "agents").glob("sdlc-*.agent.md")), f"agents installed in {home / 'agents'}")
    line((home / "skills" / "jira-ticket-digest").exists(), f"skills installed in {home / 'skills'}")
    mcp = home / "mcp-config.json"
    servers = _load_json(mcp).get("mcpServers", {}) if mcp.exists() else {}
    line("atlassian" in servers and "gitlab" in servers, "MCP servers 'atlassian' and 'gitlab' configured")
    jp = journal_path(cp)
    line(True, f"Work journal: {jp} ({len(read_journal(cp))} entries)")
    ob = orbit_command()
    line(bool(ob) or not cfg_bool(cp, "orbit", "enabled", True), "Orbit CLI (code graph for impact analysis)" + ("" if ob else " - not found: npm install -g @gitlab/orbit"))
    if ob and cfg_bool(cp, "orbit", "enabled", True):
        st = orbit_state(cp, _checks_folder(cp, args))
        line(st["ok"], f"Orbit index for {st['folder']}: {st['summary']}" + ("" if st["ok"] else f" -> {st['index_cmd']}"))
    hooks = git_hook_inventory(cp)
    bad = [h for h in hooks if h["status"] in ("missing", "outdated")]
    line(not bad, f"git hooks: {sum(h['status'] == 'installed' for h in hooks)} installed"
         + (f", {len(bad)} missing/outdated -> install-hooks (details: hooks)" if bad else "")
         + ("".join(f", {n} {s}" for s, n in ((s, sum(h['status'] == s for h in hooks)) for s in ("foreign", "skipped", "external")) if n)))
    for tool in ("ruff", "bandit", "mypy"):
        print(("  ✅ " if shutil.which(tool) else "  ·  ") + f"{tool} {'found' if shutil.which(tool) else 'not found (optional)'}")
    print("\nAll good." if ok else "\nSome items need attention (see ⚠ above and MANUAL_STEPS.md).")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sdlc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    p = sub.add_parser("template"); p.add_argument("name"); p.add_argument("--repo")
    p = sub.add_parser("repos"); p.add_argument("--repo", action="append")
    p = sub.add_parser("workdir"); p.add_argument("key")
    p = sub.add_parser("branch-name"); p.add_argument("key"); p.add_argument("--type", default="feature"); p.add_argument("--title", default=""); p.add_argument("--user"); p.add_argument("--poc")
    p = sub.add_parser("check-branch"); p.add_argument("--branch"); p.add_argument("--repo")
    p = sub.add_parser("check-commit"); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--message"); g.add_argument("--message-file")
    p = sub.add_parser("quality"); p.add_argument("key"); p.add_argument("--repo", action="append")
    p = sub.add_parser("collect"); p.add_argument("key"); p.add_argument("--repo", action="append"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("summary"); p.add_argument("key")
    p = sub.add_parser("render"); p.add_argument("template"); p.add_argument("--data"); p.add_argument("--out"); p.add_argument("--repo")
    p = sub.add_parser("install-hooks"); p.add_argument("--repo", action="append")
    p = sub.add_parser("hooks"); p.add_argument("--repo", action="append"); p.add_argument("--json", action="store_true")
    p.add_argument("--markdown", action="store_true")
    p = sub.add_parser("orbit"); p.add_argument("action", choices=["index", "list", "status", "grep", "context"])
    p.add_argument("--folder"); p.add_argument("--repo"); p.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("log"); p.add_argument("key"); p.add_argument("--activity", required=True)
    p.add_argument("--summary", required=True); p.add_argument("--title"); p.add_argument("--status")
    p.add_argument("--repos"); p.add_argument("--branch")
    for name in ("worklog", "report"):
        p = sub.add_parser(name); p.add_argument("--ticket"); p.add_argument("--activity")
        p.add_argument("--period", default="week"); p.add_argument("--from", dest="date_from"); p.add_argument("--to", dest="date_to")
        if name == "worklog":
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--by", choices=["day", "ticket"], default="day"); p.add_argument("--out")
    sub.add_parser("doctor")
    for name in ("preflight", "checklist"):
        p = sub.add_parser(name); p.add_argument("--folder"); p.add_argument("--json", action="store_true")
        if name == "checklist":
            p.add_argument("--offline", action="store_true", help="skip the network checks (git remotes, Jira API)")
    args = ap.parse_args(argv)
    cp = load_config()
    handler = globals()["cmd_" + args.cmd.replace("-", "_")]
    try:
        return handler(cp, args)
    except RuntimeError as exc:
        print(f"sdlc: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())
