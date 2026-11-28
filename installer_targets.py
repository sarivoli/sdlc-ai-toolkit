"""AI editor / CLI targets for install.py (standard library only).

Each target says where the editor reads skills, custom agents and MCP servers
from, and in which format. Skills (`SKILL.md` folders) are the open Agent
Skills standard and are copied as is; agents are converted from Copilot's
`.agent.md` to the target's format; MCP servers are written in the target's
config format. Paths come from each editor's own documentation.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOME = Path.home()


def _vscode_user_dir() -> Path:
    if sys.platform == "win32":
        base = Path(__import__("os").environ.get("APPDATA", HOME / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = HOME / "Library" / "Application Support"
    else:
        base = Path(__import__("os").environ.get("XDG_CONFIG_HOME", HOME / ".config"))
    return base / "Code" / "User"


# agents: "md" = custom agent files, "skills" = turn toolkit agents into skills, None = skip
# mcp: (path, top_key, shape) shape in {"typed", "url", "serverUrl", "httpUrl", "toml"}
# Local (stdio) servers get NO workspace path or `${...}` variable: the configs are user level and
# Copilot rejects unresolved variables. scripts/orbit_mcp.py finds the folder itself (client roots, cwd).
TARGETS = {
    "copilot": {
        "label": "GitHub Copilot (VS Code)",
        "detect": [HOME / ".copilot", _vscode_user_dir()],
    },
    "claude": {
        "label": "Claude Code",
        "detect": [HOME / ".claude"],
        "skills": HOME / ".claude" / "skills",
        "agents": ("md", HOME / ".claude" / "agents"),
        "mcp": (HOME / ".claude.json", "mcpServers", "typed"),
        "reload": "Restart Claude Code. Run `/mcp` to sign in to `atlassian` and `gitlab`; `/agents` lists the SDLC agents.",
    },
    "cursor": {
        "label": "Cursor",
        "detect": [HOME / ".cursor"],
        "skills": HOME / ".cursor" / "skills",
        "agents": ("md", HOME / ".cursor" / "agents"),
        "mcp": (HOME / ".cursor" / "mcp.json", "mcpServers", "url"),
        "reload": "Restart Cursor. Settings > Tools & MCP: connect `atlassian` and `gitlab`. Skills appear under `/`; agents are subagents.",
    },
    "antigravity": {
        "label": "Google Antigravity (app + CLI)",
        "detect": [HOME / ".gemini" / "config", HOME / ".gemini" / "antigravity", HOME / ".gemini" / "antigravity-cli"],
        "skills": HOME / ".gemini" / "config" / "skills",
        "agents": ("md", HOME / ".gemini" / "config" / "agents"),
        "mcp": (HOME / ".gemini" / "config" / "mcp_config.json", "mcpServers", "serverUrl"),
        "reload": "Restart Antigravity. Customizations > MCP Servers (or `/mcp` in the CLI): sign in to `atlassian` and `gitlab`.",
    },
    "gemini": {
        "label": "Gemini CLI",
        "detect": [HOME / ".gemini" / "settings.json"],
        "skills": HOME / ".gemini" / "skills",
        "agents": ("skills", None),
        "mcp": (HOME / ".gemini" / "settings.json", "mcpServers", "httpUrl"),
        "reload": "Restart the Gemini CLI. `/mcp` shows the servers (authenticate with `/mcp auth <name>`); the SDLC agents are installed as skills.",
    },
    "codex": {
        "label": "OpenAI Codex CLI / IDE",
        "detect": [HOME / ".codex"],
        "skills": HOME / ".codex" / "skills",
        "agents": ("skills", None),
        "mcp": (HOME / ".codex" / "config.toml", None, "toml"),
        "reload": "Restart Codex. Sign in with `codex mcp login atlassian` and `codex mcp login gitlab`; the SDLC agents are installed as skills.",
    },
}
ALL = list(TARGETS)


def detect() -> list[str]:
    found = ["copilot"]  # the original, always-on target
    for name, t in TARGETS.items():
        if name != "copilot" and any(p.exists() for p in t["detect"]):
            found.append(name)
    return found


# --------------------------------------------------------------------------
# agent conversion
# --------------------------------------------------------------------------

_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def slug(stem: str) -> str:
    s = stem[: -len(".agent")] if stem.endswith(".agent") else stem
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def name_map(agent_files: list[Path]) -> dict:
    """display name -> slug, so cross references between agents still resolve."""
    out = {}
    for p in agent_files:
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if meta.get("name"):
            out[meta["name"]] = slug(p.stem)
    return out


def convert_agent(path: Path, names: dict, text: str) -> tuple[str, str]:
    """Return (slug, markdown with minimal portable frontmatter). `text` already has placeholders substituted."""
    meta, body = split_frontmatter(text)
    for display in sorted(names, key=len, reverse=True):
        body = body.replace(display, names[display])
    desc = meta.get("description", "").replace("\r", " ")
    head = f"---\nname: {slug(path.stem)}\ndescription: {json.dumps(desc, ensure_ascii=False)}\n---\n"
    return slug(path.stem), head + body.lstrip("\n")


# --------------------------------------------------------------------------
# MCP shapes
# --------------------------------------------------------------------------


ORBIT_CLOUD_URL = "https://gitlab.com/api/v4/orbit/mcp"


def shape_server(conf: dict, shape: str) -> dict:
    """Write one server in an editor's format. `conf` is {"type": "http", "url"} or
    {"type": "stdio", "command", "args"} (a local server)."""
    if "command" in conf:
        args = list(conf.get("args", []))
        if shape == "typed":
            return {"type": "stdio", "command": conf["command"], "args": args}
        if shape == "copilot-cli":
            return {"type": "local", "command": conf["command"], "args": args, "tools": ["*"]}
        if shape == "toml":
            return {"command": conf["command"], "args": args}
        return {"command": conf["command"], "args": args}
    url = conf.get("url")
    if shape in ("typed", "copilot-cli"):
        return {"type": "http", "url": url}
    if shape in ("url", "serverUrl", "httpUrl"):
        return {shape: url}
    return conf


def server_url(conf: dict) -> str:
    return conf.get("url") or conf.get("serverUrl") or conf.get("httpUrl") or ""


def describe(conf: dict) -> str:
    if "command" in conf:
        return "local: " + " ".join([conf["command"]] + [str(a) for a in conf.get("args", [])])
    return server_url(conf)


def is_orbit_cloud(conf) -> bool:
    return isinstance(conf, dict) and server_url(conf).rstrip("/").endswith("/api/v4/orbit/mcp")


def is_orbit_legacy(name: str, existing, new: dict) -> bool:
    """True when an existing `gitlab-orbit` entry is one we replace with the local server: the hosted
    endpoint, or an earlier toolkit-written local entry (orbit_mcp.py, e.g. with `--workspace ${workspaceFolder}`)."""
    if name != "gitlab-orbit" or "command" not in new or not isinstance(existing, dict) or existing == new:
        return False
    return is_orbit_cloud(existing) or any("orbit_mcp.py" in str(a) for a in existing.get("args", []) or [])


TOML_BEGIN = "# >>> sdlc-ai-toolkit mcp >>>"
TOML_END = "# <<< sdlc-ai-toolkit mcp <<<"


def toml_block(servers: dict) -> str:
    lines = [TOML_BEGIN]
    for name, conf in servers.items():
        lines.append(f'[mcp_servers."{name}"]')
        if "command" in conf:
            lines += [f"command = {json.dumps(conf['command'])}", f"args = {json.dumps(list(conf.get('args', [])))}"]
        else:
            lines.append(f'url = "{conf["url"]}"')
        lines.append("")
    lines.append(TOML_END)
    return "\n".join(lines) + "\n"


def toml_upsert(text: str, servers: dict) -> str:
    """Replace our marked block, or append one. Servers the user defined themselves are left alone."""
    mine = {n: c for n, c in servers.items() if f'[mcp_servers."{n}"]' not in _outside_block(text)
            and f"[mcp_servers.{n}]" not in _outside_block(text)}
    text = toml_strip(text)
    if not mine:
        return text
    return text.rstrip("\n") + ("\n\n" if text.strip() else "") + toml_block(mine)


def _outside_block(text: str) -> str:
    return toml_strip(text)


def toml_strip(text: str) -> str:
    a, b = text.find(TOML_BEGIN), text.find(TOML_END)
    if a == -1 or b == -1:
        return text
    return (text[:a].rstrip("\n") + "\n" + text[b + len(TOML_END):].lstrip("\n")).lstrip("\n")
