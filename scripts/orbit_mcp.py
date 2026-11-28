#!/usr/bin/env python3
"""Local GitLab Orbit MCP server (stdio) for the SDLC AI Toolkit.

Serves the code knowledge graph of ONE workspace folder over the Model Context
Protocol, using the locally installed Orbit CLI (`npm install -g @gitlab/orbit`).
Everything runs on this machine: the graph lives in <workspace>/.sdlc/orbit
(the same place `sdlc.py orbit index` writes to) and no call goes to GitLab.

    python orbit_mcp.py [--workspace <folder>]

The editor configs carry no workspace path or variable (they are user level and
shared by all workspaces; Copilot rejects unresolved `${...}` variables). The
workspace folder is worked out at run time, first match wins:
  1. --workspace <folder>
  2. the MCP client's roots: when the client declares the `roots` capability the
     server asks `roots/list` after `notifications/initialized` and uses the
     first file:// root (re-read on `notifications/roots/list_changed`)
  3. $WORKSPACE_FOLDER (when it is a real directory)
  4. the current directory (spelled as $PWD when that is the same folder)
When the folder is inside a configured workspace root (`[workspace] root/roots`
in toolkit.ini) the root's graph is used, exactly like `sdlc.py orbit`. The home
directory and the filesystem root are never indexed automatically.

Transport: JSON-RPC 2.0, one message per line on stdin/stdout (MCP stdio).
Standard library only; Python 3.8+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sdlc as S  # noqa: E402  (helper CLI next to this file)

SERVER_NAME = "gitlab-orbit"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT = int(os.environ.get("SDLC_ORBIT_MCP_TIMEOUT", "300"))
ROOTS_WAIT = float(os.environ.get("SDLC_ORBIT_MCP_ROOTS_WAIT", "5"))
MAX_OUTPUT = 120_000

# grep/context kinds that make the Orbit CLI call the GitLab API. This server is local only.
_GITLAB_KIND = re.compile(
    r"(?:^|[\s\"'])(mr|issue|branch|commit|comment|milestone|user|project|group|gitlab|repo|pipeline|job):", re.I)
_GITLAB_REF = re.compile(r"^(https?://|(Project|Group)\[)", re.I)
_NO_MATCH = re.compile(r": 0 lines in 0 files\s*$")
# variables the Orbit CLI uses to reach / authenticate against GitLab
_SCRUB = ("GITLAB_TOKEN", "GITLAB_URL", "ORBIT_API_BASE_URL", "ORBIT_AUTH_HEADER_NAME", "ORBIT_AUTH_HEADER_VALUE")


def log(msg: str):
    print(f"[orbit-mcp] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# workspace / CLI
# --------------------------------------------------------------------------


def load_cp():
    try:
        return S.load_config()
    except SystemExit:  # toolkit not installed next to us: defaults
        import configparser
        return configparser.ConfigParser(interpolation=None)


def guarded(p: Path) -> bool:
    """Home directory or filesystem root: far too big to index by accident."""
    try:
        home = Path.home().resolve()
    except (RuntimeError, KeyError):
        home = None
    return p == home or p == Path(p.anchor)


def uri_to_path(uri: str) -> Path | None:
    u = urllib.parse.urlparse(uri or "")
    if u.scheme != "file":
        return None
    path = urllib.request.url2pathname(u.path)  # also percent-decodes
    if u.netloc and u.netloc != "localhost":
        path = f"//{u.netloc}{path}"
    return Path(path)


def fallback_start() -> str:
    """$WORKSPACE_FOLDER, else the current directory. $PWD is only used to keep the
    user's spelling of the cwd (symlinks): a parent's stale $PWD is ignored."""
    v = os.environ.get("WORKSPACE_FOLDER")
    if v and "${" not in v and Path(v).is_dir():
        return v
    cwd = os.getcwd()
    pwd = os.environ.get("PWD")
    try:
        if pwd and Path(pwd).is_dir() and os.path.samefile(pwd, cwd):
            return pwd
    except OSError:
        pass
    return cwd


def resolve_folder(cp, start: str | None) -> Path:
    if not start or "${" in start:
        start = fallback_start()
    p = Path(start).expanduser().resolve()
    roots = [Path(r.strip()).expanduser().resolve() for r in S.cfg(cp, "workspace", "roots", "").split(",") if r.strip()]
    root = S.cfg(cp, "workspace", "root", "")
    if root:
        roots.append(Path(root).expanduser().resolve())
    for r in roots:
        if p == r or r in p.parents:
            return r
    return p


class Orbit:
    def __init__(self, folder: Path, cp):
        self.folder = folder
        self.cp = cp
        self.base = S.orbit_command()
        if self.base and len(self.base) > 1:  # `glab orbit` would use the GitLab sign-in; stay with the plain CLI only
            self.base = None
        self.guarded = guarded(folder)
        data = folder / S.cfg(cp, "workspace", "work_dir", ".sdlc") / "orbit"
        if not self.guarded:
            data.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, ORBIT_DATA_DIR=str(data))
        self.env["ORBIT_TELEMETRY_ENABLED"] = "true" if S.cfg_bool(cp, "orbit", "telemetry", False) else "false"
        for k in _SCRUB:
            self.env.pop(k, None)
        self.env["ORBIT_NO_GITLAB"] = "1"
        os.environ["SDLC_WORKSPACE_ROOT"] = str(folder)  # discover_repos() searches this folder

    def run(self, args: list[str], cwd: Path | None = None, timeout: int = TIMEOUT) -> tuple[int, str]:
        if not self.base:
            return 127, ("Orbit CLI not found. Install it with `npm install -g @gitlab/orbit` (needs Node.js), "
                         "then restart the MCP server.")
        try:
            proc = subprocess.run(self.base + args, cwd=str(cwd or self.folder), env=self.env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, f"orbit {' '.join(args)} timed out after {timeout}s"
        out = proc.stdout
        if proc.stderr.strip():
            out = (out.rstrip("\n") + "\n\n[stderr]\n" if out.strip() else "") + proc.stderr
        return proc.returncode, out

    def repos(self) -> list[Path]:
        if S.is_repo(self.folder):
            return [self.folder]
        if self.guarded:
            return []
        return S.discover_repos(self.cp)

    def indexed(self) -> list[dict]:
        code, out = self.run(["workspace", "list", "-F", "json"], timeout=60)
        if code != 0:
            return []
        try:
            return json.loads(out.split("\n\n[stderr]")[0] or "[]")
        except ValueError:
            return []

    def index_async(self):
        return self.run(["workspace", "index", str(self.folder), "--async"], timeout=120)


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "orbit_status",
        "description": "Show which repositories of this workspace folder are in the local Orbit code graph "
                       "(branch, commit, last indexed time) and where the graph is stored. Local only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "orbit_index",
        "description": "Build or refresh the local Orbit code graph for this workspace folder (all repos in it), "
                       "or for one sub folder / repo. Runs in the background by default; check with orbit_status.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Repo or sub folder to index (default: the whole workspace folder)"},
            "wait": {"type": "boolean", "description": "Index in the foreground and return the statistics (default false)"},
        }, "additionalProperties": False},
    },
    {
        "name": "orbit_grep",
        "description": "Search local code, tests, config and docs like ripgrep, with definition context "
                       "(which function/class each match is in). Matching ignores case, `_` and `-`; "
                       "'a|b' is OR; `def:name` / `class:name` / `method:name` / `dir:name` / `file:x` narrow the search. "
                       "Without `repo` every repo of the workspace folder is searched.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}, "description": "Files/dirs/globs inside the repo"},
            "repo": {"type": "string", "description": "Repository path, absolute or relative to the workspace folder"},
            "fixed_strings": {"type": "boolean"},
            "word": {"type": "boolean", "description": "Whole words only"},
            "context_lines": {"type": "integer", "minimum": 0},
            "files_only": {"type": "boolean", "description": "Only list matching files"},
            "max_count": {"type": "integer", "minimum": 1, "description": "Max matching lines per file"},
            "glob": {"type": "array", "items": {"type": "string"}, "description": "rg-style -g globs"},
        }, "additionalProperties": False},
    },
    {
        "name": "orbit_context",
        "description": "Expand code from the local graph: file paths, path:start-end ranges, directories, names, "
                       "or the Definition:<id> / File:<id> tokens orbit_grep prints. Returns numbered source with "
                       "the indexed callers and covering tests.",
        "inputSchema": {"type": "object", "required": ["targets"], "properties": {
            "targets": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "repo": {"type": "string", "description": "Repository path (needed when the workspace folder holds several repos)"},
        }, "additionalProperties": False},
    },
    {
        "name": "orbit_sql",
        "description": "Run a read-only DuckDB SQL query against the local graph (see orbit_schema for tables).",
        "inputSchema": {"type": "object", "required": ["sql"], "properties": {
            "sql": {"type": "string"},
            "repo": {"type": "string", "description": "Only this checkout's current revision"},
            "format": {"type": "string", "enum": ["table", "json", "csv"]},
        }, "additionalProperties": False},
    },
    {
        "name": "orbit_schema",
        "description": "Describe the tables and columns of the local graph.",
        "inputSchema": {"type": "object", "properties": {
            "tables": {"type": "array", "items": {"type": "string"}},
        }, "additionalProperties": False},
    },
]


class ToolError(Exception):
    pass


def _local_only(values: list[str]):
    for v in values:
        if _GITLAB_KIND.search(v) or _GITLAB_REF.match(v.strip()):
            raise ToolError(f"`{v}` asks GitLab, and this Orbit server is local only. "
                            "Use the `gitlab` MCP server for merge requests, issues and pipelines.")


def _repo(ob: Orbit, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value).expanduser()
    p = (ob.folder / p if not p.is_absolute() else p).resolve()
    if not p.exists():
        raise ToolError(f"repo `{value}` not found (looked at {p})")
    return p


def call_tool(ob: Orbit, name: str, a: dict) -> tuple[bool, str]:
    """Return (is_error, text)."""
    if name == "orbit_status":
        rows = ob.indexed()
        lines = [f"Workspace folder: {ob.folder}", f"Graph: {ob.env['ORBIT_DATA_DIR']}", ""]
        if not ob.base:
            return True, ob.run([])[1]
        if ob.guarded:
            return False, "\n".join(lines[:1] + [
                "", "This is your home directory (or the filesystem root), so nothing is indexed automatically.",
                "The editor did not report an open folder. Open a project folder in the editor, or call orbit_index "
                "with `path` set to the folder that holds your repos, or run `sdlc orbit index --folder <path>`."])
        if not rows:
            lines.append("Nothing indexed yet. Call orbit_index (or run `sdlc orbit index` in this folder).")
        for r in rows:
            lines.append(f"- {r.get('repo_path')}  [{r.get('branch')} @ {str(r.get('commit_sha'))[:10]}]  "
                         f"{r.get('status')}  {r.get('last_indexed_at')}")
        missing = [str(p) for p in ob.repos() if not any(str(r.get("repo_path")) == str(p) for r in rows)]
        if rows and missing:
            lines += ["", "Repos in this folder not indexed yet: " + ", ".join(missing)]
        return False, "\n".join(lines)
    if name == "orbit_index":
        target = _repo(ob, a.get("path")) or ob.folder
        if guarded(target):
            raise ToolError(f"refusing to index {target} (home directory / filesystem root). "
                            "Pass `path` = the folder that holds your repos.")
        args = ["workspace", "index", str(target)] + ([] if a.get("wait") else ["--async"])
        code, out = ob.run(args, timeout=max(TIMEOUT, 1800) if a.get("wait") else 120)
        if code == 0 and not a.get("wait"):
            out = (out.strip() + "\n" if out.strip() else "") + f"Indexing {target} started in the background. Check with orbit_status."
        return code != 0, out
    if name == "orbit_grep":
        query = a.get("query") or ""
        paths = list(a.get("paths") or [])
        _local_only([query] + paths)
        flags = []
        if a.get("fixed_strings"):
            flags.append("-F")
        if a.get("word"):
            flags.append("-w")
        if a.get("files_only"):
            flags.append("-l")
        if a.get("context_lines") is not None:
            flags += ["-C", str(int(a["context_lines"]))]
        if a.get("max_count"):
            flags += ["-m", str(int(a["max_count"]))]
        for g in a.get("glob") or []:
            flags += ["-g", g]
        repo = _repo(ob, a.get("repo"))
        repos = [repo] if repo else ob.repos()
        if not repos:
            raise ToolError(f"no git repositories found under {ob.folder}"
                            + (" (home directory: pass `repo`)" if ob.guarded else ""))
        parts, failed = [], 0
        for r in repos:
            code, out = ob.run(["grep"] + flags + ["--repo", str(r), "--", query] + paths, cwd=r)
            if code in (0, 1) and (not out.strip() or _NO_MATCH.search(out.splitlines()[0])):
                continue  # no match in this repo
            if code not in (0, 1):
                failed += 1
            head = f"=== {r}\n" if len(repos) > 1 else ""
            parts.append(head + out.rstrip("\n"))
        if not parts:
            return False, f"No matches for `{query}` in {len(repos)} repo(s)."
        return failed == len(repos), "\n\n".join(parts)
    if name == "orbit_context":
        targets = [str(t) for t in a.get("targets") or []]
        if not targets:
            raise ToolError("targets is required")
        _local_only(targets)
        repo = _repo(ob, a.get("repo"))
        if not repo:
            repos = ob.repos()
            if len(repos) != 1:
                raise ToolError("this workspace folder holds several repos; pass `repo` (one of: "
                                + ", ".join(str(r.relative_to(ob.folder)) if ob.folder in r.parents else str(r) for r in repos) + ")")
            repo = repos[0]
        code, out = ob.run(["context", "--repo", str(repo), "--"] + targets, cwd=repo)
        return code != 0, out
    if name == "orbit_sql":
        args = ["workspace", "sql", "-F", a.get("format") or "table"]
        repo = _repo(ob, a.get("repo"))
        if repo:
            args += ["--repo", str(repo)]
        code, out = ob.run(args + ["--", a.get("sql") or ""])
        return code != 0, out
    if name == "orbit_schema":
        code, out = ob.run(["workspace", "schema"] + [str(t) for t in a.get("tables") or []])
        return code != 0, out
    raise ToolError(f"unknown tool {name}")


# --------------------------------------------------------------------------
# MCP / JSON-RPC over stdio
# --------------------------------------------------------------------------


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n\n[output truncated: {len(text) - MAX_OUTPUT} more characters; narrow the query]"


class Server:
    """MCP over stdio. Requests from the client run on worker threads, so the
    reader keeps going and can receive the answer to our own `roots/list`
    request (matched by id) while a tool call waits for the workspace."""

    def __init__(self, cp, explicit: str | None, auto_index: bool = True, stdout=None):
        self.cp = cp
        self.explicit = explicit if explicit and "${" not in explicit else None
        self.auto = auto_index
        self.out = stdout or sys.stdout
        self.lock = threading.Lock()
        self.ob: Orbit | None = None
        self.ready = threading.Event()
        self.client_roots = False
        self.pending: dict = {}
        self.seq = 0
        self.workers: list[threading.Thread] = []
        self.indexed_once: set = set()
        if self.explicit:
            self.set_folder(resolve_folder(cp, self.explicit), "--workspace")

    # -------------------------------------------------- workspace
    def set_folder(self, folder: Path, why: str):
        if self.ob and self.ob.folder == folder:
            self.ready.set()
            return
        self.ob = Orbit(folder, self.cp)
        log(f"workspace folder {folder} (from {why}), graph {self.ob.env['ORBIT_DATA_DIR']}, "
            f"cli {' '.join(self.ob.base or ['<not found>'])}")
        self.ready.set()
        if self.auto and folder not in self.indexed_once:
            self.indexed_once.add(folder)
            threading.Thread(target=auto_index, args=(self.ob,), daemon=True).start()

    def fallback(self, why: str):
        if not self.ready.is_set():
            self.set_folder(resolve_folder(self.cp, None), why)

    def ask_roots(self):
        self.seq += 1
        rid = f"orbit-mcp-roots-{self.seq}"
        self.pending[rid] = self.on_roots
        self.send({"jsonrpc": "2.0", "id": rid, "method": "roots/list", "params": {}})
        t = threading.Timer(ROOTS_WAIT, self.roots_timeout, args=(rid,))
        t.daemon = True
        t.start()

    def roots_timeout(self, rid: str):
        if self.pending.pop(rid, None):
            self.fallback("cwd/env: no roots answer")

    def on_roots(self, msg: dict):
        roots = ((msg.get("result") or {}).get("roots") or []) if "result" in msg else []
        for r in roots:
            p = uri_to_path(r.get("uri", "")) if isinstance(r, dict) else None
            if p and p.is_dir():
                self.set_folder(resolve_folder(self.cp, str(p)), "client roots")
                return
        self.fallback("cwd/env: client gave no usable root")

    def orbit(self) -> Orbit:
        if not self.ready.wait(ROOTS_WAIT):
            self.fallback("cwd/env: roots not answered in time")
        return self.ob

    # -------------------------------------------------- transport
    def send(self, obj):
        with self.lock:
            self.out.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.out.flush()

    def serve(self, stdin=None):
        for line in (stdin or sys.stdin):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue
            for m in (msg if isinstance(msg, list) else [msg]):
                if not isinstance(m, dict):
                    self.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
                    continue
                self.dispatch(m)
        for t in self.workers:
            t.join()

    def dispatch(self, m: dict):
        method = m.get("method")
        if method is None and "id" in m and ("result" in m or "error" in m):  # answer to our request
            cb = self.pending.pop(m["id"], None)
            if cb:
                cb(m)
            return
        if method == "initialize":
            caps = (m.get("params") or {}).get("capabilities") or {}
            self.client_roots = isinstance(caps.get("roots"), dict)
            if not self.client_roots:
                self.fallback("cwd/env: client has no roots")
        elif method == "notifications/initialized":
            if self.client_roots and not self.explicit:
                self.ask_roots()
            return
        elif method == "notifications/roots/list_changed":
            if self.client_roots and not self.explicit:
                self.ready.clear()
                self.ask_roots()
            return
        if method == "tools/call" and "id" in m:
            t = threading.Thread(target=lambda: self.send(self.handle(m)), daemon=True)
            self.workers.append(t)
            t.start()
            return
        reply = self.handle(m)
        if reply is not None:
            self.send(reply)

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        def ok(result):
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code, message):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

        if not isinstance(method, str):
            return err(-32600, "Invalid Request") if "id" in msg else None
        if "id" not in msg:  # other notifications (cancelled, ...): nothing to answer
            return None
        if method == "initialize":
            want = params.get("protocolVersion")
            return ok({
                "protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "title": "GitLab Orbit (local)", "version": _version()},
                "instructions": "Local GitLab Orbit code graph of the open workspace folder (orbit_status shows which). "
                                "Use orbit_grep to find code with definition context and orbit_context to read it with "
                                "callers and tests. If results look stale, call orbit_index.",
            })
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            if name not in {t["name"] for t in TOOLS}:
                return err(-32602, f"Unknown tool: {name}")
            try:
                is_error, text = call_tool(self.orbit(), name, params.get("arguments") or {})
            except ToolError as exc:
                is_error, text = True, str(exc)
            except Exception as exc:  # never kill the server on one bad call
                is_error, text = True, f"{type(exc).__name__}: {exc}"
            return ok({"content": [{"type": "text", "text": _clip(text) or "(no output)"}], "isError": bool(is_error)})
        if method in ("resources/list", "prompts/list"):
            return ok({method.split("/")[0]: []})
        return err(-32601, f"Method not found: {method}")


def _version() -> str:
    v = HERE.parent / "VERSION"
    return v.read_text(encoding="utf-8").strip() if v.exists() else "dev"


def auto_index(ob: Orbit):
    if not ob.base or ob.guarded or not S.cfg_bool(ob.cp, "orbit", "auto_index", True):
        return
    folder = str(ob.folder)
    rows = ob.indexed()
    if any(str(r.get("repo_path", "")) == folder or str(r.get("repo_path", "")).startswith(folder + os.sep) for r in rows):
        return
    if not ob.repos():
        return
    code, out = ob.index_async()
    log(f"no graph for {folder} yet: " + ("background indexing started" if code == 0 else f"index failed: {out.strip()[:300]}"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Local GitLab Orbit MCP server (stdio)")
    ap.add_argument("--workspace", help="workspace folder (default: the client's roots, else the current directory)")
    ap.add_argument("--no-auto-index", action="store_true", help="do not start indexing an unindexed folder")
    args = ap.parse_args(argv)
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    Server(load_cp(), args.workspace, auto_index=not args.no_auto_index).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
