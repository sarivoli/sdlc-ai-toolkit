#!/usr/bin/env python3
"""SDLC AI Toolkit UI server (MCP stdio): A2UI screens for agents and skills, as an MCP App.

Editors that support MCP Apps (VS Code Copilot Chat, Cursor, ...) show the result
of every `sdlc_ui_*` tool as an interactive panel in the chat: the server serves
one self-contained HTML file (scripts/ui/sdlc-ui.html, the A2UI Lit renderer)
under `ui://sdlc/app`, and each tool returns A2UI v1.0 messages
(`application/a2ui+json`) that the panel draws.

Buttons never act behind the developer's back: a confirmation button sends the
reply ("yes", "approve", ...) into the chat as the developer's own message, so
the agent's checkpoints and `[safety] confirm_before` rules work exactly as when
the developer types it. The only button that runs anything on the server is
"Re-check" on the setup checklist (read-only checks).

Editors without MCP Apps (terminal CLIs) get no tools from this server
([ui] mode = auto), so agents fall back to their normal text output.

    python sdlc_ui_mcp.py

Transport: JSON-RPC 2.0, one message per line on stdin/stdout (MCP stdio).
Standard library only; Python 3.8+.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import a2ui as A  # noqa: E402
import sdlc as S  # noqa: E402

SERVER_NAME = "sdlc-ui"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
APP_URI = "ui://sdlc/app"
APP_MIME = "text/html;profile=mcp-app"
UI_EXTENSION = "io.modelcontextprotocol/ui"
BUNDLE = HERE / "ui" / "sdlc-ui.html"
# MCP Apps hosts that may not declare the UI extension in `initialize` yet
KNOWN_UI_CLIENTS = re.compile(r"visual studio code|vscode|code - insiders|copilot|cursor|claude-ai|claude desktop|"
                              r"goose|chatgpt|mcp-inspector|mcpjam", re.I)
TIMEOUT = int(os.environ.get("SDLC_UI_TIMEOUT", "120"))


def log(msg: str):
    print(f"[sdlc-ui] {msg}", file=sys.stderr, flush=True)


def load_cp():
    try:
        return S.load_config()
    except SystemExit as exc:  # no toolkit.ini: still serve, tools explain what is missing
        log(str(exc))
        import configparser
        return configparser.ConfigParser()


# --------------------------------------------------------------------------
# tool catalogue
# --------------------------------------------------------------------------

_UI_META = {"ui": {"resourceUri": APP_URI, "visibility": ["model", "app"]}, "ui/resourceUri": APP_URI}
_APP_ONLY = {"ui": {"resourceUri": APP_URI, "visibility": ["app"]}}
_TICKET = {"type": "string", "description": "Jira ticket key, e.g. PROJ-123"}
_LINKS = {"type": "array", "items": {"type": "object", "required": ["label", "url"], "properties": {
    "label": {"type": "string"}, "url": {"type": "string"}}}}
_FACTS = {"type": "array", "description": "Short label/value pairs (repo, branch, files ...)",
          "items": {"type": "object", "required": ["label", "value"], "properties": {
              "label": {"type": "string"}, "value": {"type": "string"}}}}

TOOLS = [
    {
        "name": "sdlc_ui_confirm",
        "title": "Ask for confirmation (panel)",
        "description": "Show a confirmation panel before an action that needs the developer's explicit yes "
                       "([safety] confirm_before: edit_repo, push, create_mr, jira_comment, jira_transition, install). "
                       "Put the exact text/command in `preview`. The panel's buttons send the reply into the chat as "
                       "the developer's message; still WAIT for that message - never treat the panel as consent.",
        "inputSchema": {"type": "object", "required": ["title", "action"], "properties": {
            "title": {"type": "string", "description": "e.g. 'Push 3 commits to origin/feature/PROJ-1-login'"},
            "action": {"type": "string", "description": "edit_repo | push | create_mr | jira_comment | jira_transition | install | other"},
            "ticket": _TICKET,
            "agent": {"type": "string", "description": "Agent or skill asking"},
            "summary": {"type": "string", "description": "Markdown: what will happen and why"},
            "facts": _FACTS,
            "preview": {"type": "string", "description": "Exact text, diff or command that will be used (markdown)"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "confirm_label": {"type": "string"}, "confirm_reply": {"type": "string", "description": "default: yes"},
            "cancel_label": {"type": "string"}, "cancel_reply": {"type": "string", "description": "default: no"},
            "allow_comment": {"type": "boolean", "description": "Offer 'Change request' with a comment box"},
        }, "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_summary",
        "title": "Show step summary (panel)",
        "description": "Show what an agent or skill just did, as a panel: status, key facts, links and next steps. "
                       "Call it at the end of every stage/skill run instead of repeating a long text summary.",
        "inputSchema": {"type": "object", "required": ["title", "status"], "properties": {
            "title": {"type": "string"},
            "status": {"type": "string", "enum": ["done", "needs_input", "blocked", "failed", "info"]},
            "agent": {"type": "string", "description": "Agent or skill name"},
            "ticket": _TICKET,
            "summary": {"type": "string", "description": "Markdown, a few lines"},
            "facts": _FACTS,
            "items": {"type": "array", "description": "Checklist of results",
                      "items": {"type": "object", "required": ["label"], "properties": {
                          "label": {"type": "string"},
                          "state": {"type": "string", "enum": ["done", "todo", "warn", "fail", "skip", "info"]},
                          "detail": {"type": "string"}}}},
            "links": _LINKS,
            "next_steps": {"type": "array", "description": "Buttons that send `reply` into the chat",
                           "items": {"type": "object", "required": ["label", "reply"], "properties": {
                               "label": {"type": "string"}, "reply": {"type": "string"}}}},
        }, "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_plan",
        "title": "Review implementation plan (panel)",
        "description": "Checkpoint 1: show <workdir>/plan.md (and impact.md) with Approve / Request changes. "
                       "Approve sends 'approve' into the chat; write plan.approved only after that message arrives.",
        "inputSchema": {"type": "object", "required": ["ticket"], "properties": {"ticket": _TICKET},
                        "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_quality",
        "title": "Show quality gate (panel)",
        "description": "Show <workdir>/quality.json (written by `sdlc quality KEY`) per repo and check.",
        "inputSchema": {"type": "object", "required": ["ticket"], "properties": {"ticket": _TICKET},
                        "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_ticket",
        "title": "Show ticket progress (panel)",
        "description": "Show where a ticket is in the SDLC (understanding, impact, plan, approval, quality, commits, "
                       "MRs, summary) from its notes folder, with each stage's file readable in tabs. Use it on resume.",
        "inputSchema": {"type": "object", "required": ["ticket"], "properties": {"ticket": _TICKET},
                        "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_install_preview",
        "title": "Preview toolkit install/update (panel)",
        "description": "Before installing or updating the toolkit: run `install.py --dry-run` and show what would "
                       "change, with Install / Cancel buttons (they reply in the chat; run the installer only after "
                       "the developer's yes).",
        "inputSchema": {"type": "object", "properties": {
            "source": {"type": "string", "description": "Toolkit clone that holds install.py (default: the one used last time)"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "Extra installer arguments, e.g. --target, --set"},
        }, "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_install_report",
        "title": "Show install result (panel)",
        "description": "After install/update: show the installation report (done, manual steps, post-install "
                       "checklist, hooks) from ~/.copilot/sdlc-toolkit/install-report.json.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_checklist",
        "title": "Show setup checklist (panel)",
        "description": "Live post-install checklist (Orbit index - mandatory, git auth, Jira auth) with Re-check. "
                       "Use it when `sdlc preflight` stops.",
        "inputSchema": {"type": "object", "properties": {
            "folder": {"type": "string", "description": "Workspace folder (default: the open folder / configured root)"},
        }, "additionalProperties": False},
    },
    {
        "name": "sdlc_ui_checklist_refresh",
        "title": "Re-check setup",
        "description": "Panel callback: re-run the setup checks.",
        "inputSchema": {"type": "object", "properties": {"folder": {"type": "string"}}, "additionalProperties": True},
        "_meta": _APP_ONLY,
    },
]
for _t in TOOLS:
    _t.setdefault("_meta", _UI_META)
    _t["annotations"] = {"readOnlyHint": True, "openWorldHint": False}

STATUS = {  # status -> (icon, badge)
    "done": ("check", "✅ Done"), "needs_input": ("help", "❓ Your input"), "blocked": ("warning", "⛔ Blocked"),
    "failed": ("error", "❌ Failed"), "info": ("info", "ℹ️ Info"),
}
ITEM = {"done": ("done", "done"), "todo": ("todo", "to do"), "warn": ("warning", "check"),
        "fail": ("error", "failed"), "skip": ("skipNext", "skipped"), "info": ("info", "")}


class ToolError(Exception):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _key(a: dict) -> str:
    key = str(a.get("ticket") or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", key):
        raise ToolError(f"Not a Jira ticket key: {key!r} (expected e.g. PROJ-123)")
    return key.upper()


def _read(p: Path, limit: int = A.MAX_TEXT) -> str:
    try:
        return A.clip(p.read_text(encoding="utf-8", errors="replace"), limit)
    except OSError:
        return ""


def _safe_url(url: str) -> str:
    u = str(url or "").strip()
    return u if urllib.parse.urlparse(u).scheme in ("http", "https") else ""


def _sid(prefix: str) -> str:
    return A.ident(f"{prefix}_{os.getpid()}_{next(_SEQ)}")


_SEQ = iter(range(1, 1 << 30))


def _md_facts(facts) -> list[str]:
    return [f"- {f.get('label')}: {f.get('value')}" for f in facts or [] if isinstance(f, dict)]


def _facts(a: dict) -> list[tuple[str, str]]:
    return [(str(f.get("label", "")), str(f.get("value", ""))) for f in a.get("facts") or [] if isinstance(f, dict)]


# --------------------------------------------------------------------------
# screens: each returns (a2ui messages, short text for the model)
# --------------------------------------------------------------------------


def screen_confirm(a: dict):
    title = str(a.get("title") or "Confirm")
    action = str(a.get("action") or "other")
    s = A.Surface(_sid("confirm"))
    sub = " · ".join(x for x in (a.get("agent"), a.get("ticket"), action.replace("_", " ")) if x)
    body = [s.header(title, sub, "lock" if action in ("push", "create_mr", "install") else "help", "Needs your OK"),
            s.divider()]
    if a.get("summary"):
        body.append(s.text(str(a["summary"])))
    f = s.facts(_facts(a))
    if f:
        body.append(f)
    if a.get("preview"):
        body.append(s.card(s.column([s.text("Exactly this will be used", "caption"), s.text(str(a["preview"]))])))
    for w in a.get("warnings") or []:
        body.append(s.row([s.icon("warning"), s.text(str(w), weight=1)]))
    data = {}
    if a.get("allow_comment"):
        data["comment"] = ""
        body.append(s.text_field("Change request (optional)", "/comment", "What should change?"))
    yes = str(a.get("confirm_reply") or "yes")
    no = str(a.get("cancel_reply") or "no")
    buttons = [s.chat_button(str(a.get("cancel_label") or "Cancel"), no, "borderless", "close")]
    if a.get("allow_comment"):
        buttons.append(s.chat_button("Request changes", "changes", "default", "edit", "/comment", True))
    buttons.append(s.chat_button(str(a.get("confirm_label") or "Confirm"), yes, "primary", "check"))
    body.append(s.row(buttons, justify="end"))
    s.root(s.card(s.column(body)))
    text = (f"Confirmation panel shown: {title}. Wait for the developer's reply in the chat "
            f"('{yes}' to go ahead, '{no}' to stop) before doing it.")
    return s.messages(data or None), text


def screen_summary(a: dict):
    status = a.get("status") if a.get("status") in STATUS else "info"
    icon, badge = STATUS[status]
    title = str(a.get("title") or "Summary")
    s = A.Surface(_sid("summary"))
    body = [s.header(title, " · ".join(x for x in (a.get("agent"), a.get("ticket")) if x), icon, badge), s.divider()]
    if a.get("summary"):
        body.append(s.text(str(a["summary"])))
    f = s.facts(_facts(a))
    if f:
        body.append(f)
    items = [i for i in a.get("items") or [] if isinstance(i, dict) and i.get("label")]
    if items:
        rows = []
        for it in items[:40]:
            ic, word = ITEM.get(it.get("state") or "info", ITEM["info"])
            rows.append(s.status_line(ic, str(it["label"]), word, str(it.get("detail") or "")))
        body.append(s.column(rows))
    links = [(str(x.get("label")), _safe_url(x.get("url"))) for x in a.get("links") or [] if isinstance(x, dict)]
    links = [(lbl, u) for lbl, u in links if u]
    nxt = [x for x in a.get("next_steps") or [] if isinstance(x, dict) and x.get("label") and x.get("reply")]
    if links or nxt:
        buttons = [s.link_button(lbl, u) for lbl, u in links[:6]]
        buttons += [s.chat_button(str(x["label"]), str(x["reply"]), "primary" if i == 0 else "default", "arrowForward")
                    for i, x in enumerate(nxt[:4])]
        body.append(s.row(buttons, justify="end"))
    s.root(s.card(s.column(body)))
    return s.messages(), f"Summary panel shown: {title} ({status})."


def _workdir(cp, key: str) -> Path:
    return S.workspace_root(cp) / S.cfg(cp, "workspace", "work_dir", ".sdlc") / key


def screen_plan(cp, a: dict):
    key = _key(a)
    wd = _workdir(cp, key)
    plan, impact = _read(wd / "plan.md"), _read(wd / "impact.md")
    if not plan:
        raise ToolError(f"No plan yet: {wd / 'plan.md'} does not exist. Run impact analysis first.")
    approved = (wd / "plan.approved").exists()
    s = A.Surface(_sid(f"plan_{key}"))
    body = [s.header(f"Implementation plan · {key}", str(wd),
                     "check" if approved else "edit", "✅ Approved" if approved else "Checkpoint 1"), s.divider()]
    tabs = [("Plan", s.text(plan))]
    if impact:
        tabs.append(("Impact", s.text(impact)))
    body.append(s.tabs(tabs) if len(tabs) > 1 else tabs[0][1])
    data = None
    if approved:
        body.append(s.text(_read(wd / "plan.approved", 300) or "Approved.", "caption"))
    else:
        data = {"comment": ""}
        body.append(s.text_field("Change request", "/comment", "What should change in the plan?"))
        body.append(s.row([
            s.chat_button("Request changes", f"changes to the plan for {key}", "default", "edit", "/comment", True),
            s.chat_button("Approve plan", "approve", "primary", "check"),
        ], justify="end"))
    s.root(s.card(s.column(body)))
    text = (f"Plan panel shown for {key} ({'already approved' if approved else 'waiting for approval'}). "
            + ("" if approved else "Wait for 'approve' or a change request in the chat; write plan.approved only after 'approve'."))
    return s.messages(data), text


_CHECK_ICON = {"pass": ("done", "✅ pass"), "fail": ("error", "❌ fail"), "skipped": ("skipNext", "⏭ skipped"),
               "missing": ("warning", "⚠ missing")}


def screen_quality(cp, a: dict):
    key = _key(a)
    wd = _workdir(cp, key)
    try:
        rep = json.loads((wd / "quality.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ToolError(f"No quality report: run `sdlc quality {key}` first ({wd / 'quality.json'}).")
    ok = rep.get("result") == "PASS"
    s = A.Surface(_sid(f"quality_{key}"))
    body = [s.header(f"Quality gate · {key}", str(rep.get("timestamp", "")), "check" if ok else "error",
                     "✅ PASS" if ok else "❌ FAIL"), s.divider()]
    fails = []
    for r in rep.get("repos") or []:
        rows = [s.row([s.icon("folder"), s.text(f"**{r.get('name')}**", weight=1),
                       s.text(f"{len(r.get('changed_files') or [])} changed files · {r.get('result')}", "caption")],
                      justify="spaceBetween")]
        for c in r.get("checks") or []:
            ic, word = _CHECK_ICON.get(c.get("status"), ("info", str(c.get("status"))))
            label = str(c.get("check")) + (" (required)" if c.get("required") else "")
            detail = (str(c.get("details") or "").strip().splitlines() or [""])[-1][:160]
            rows.append(s.status_line(ic, label, word, f"{c.get('command') or '-'}" + (f" · {detail}" if detail else "")))
            if c.get("status") == "fail":
                fails.append((f"{r.get('name')} / {c.get('check')}", str(c.get("details") or "")[-1500:]))
        body.append(s.card(s.column(rows)))
    if fails:
        body.append(s.tabs([(t, s.text(f"```\n{d}\n```")) for t, d in fails[:6]]))
        body.append(s.row([s.chat_button("Fix the failures", f"fix the quality gate failures for {key}", "primary",
                                         "edit")], justify="end"))
    s.root(s.card(s.column(body)))
    n_fail = len(fails)
    return s.messages(), f"Quality panel shown for {key}: {rep.get('result')} ({n_fail} failing check(s))."


STAGES = [  # (label, files, icon)
    ("Ticket understood", ["understanding.md"], "search"),
    ("Impact analysed", ["impact.md"], "share"),
    ("Plan written", ["plan.md"], "edit"),
    ("Plan approved", ["plan.approved"], "check"),
    ("Quality gate", ["quality.json", "quality.md"], "star"),
    ("Commits", ["commits.json"], "upload"),
    ("Merge requests", ["mrs.json"], "send"),
    ("Summary", ["summary.md"], "mail"),
]


def screen_ticket(cp, a: dict):
    key = _key(a)
    wd = _workdir(cp, key)
    s = A.Surface(_sid(f"ticket_{key}"))
    rows, tabs, done = [], [], 0
    for label, files, icon in STAGES:
        have = [f for f in files if (wd / f).exists()]
        state = "✅ done" if have else "· to do"
        extra = ""
        if label == "Quality gate" and have:
            try:
                extra = json.loads((wd / "quality.json").read_text(encoding="utf-8")).get("result", "")
            except (OSError, ValueError):
                pass
        rows.append(s.status_line("done" if have else "todo", label, state, ", ".join(have) + (f" · {extra}" if extra else "")))
        done += bool(have)
        md = next((f for f in have if f.endswith(".md")), None)
        if md:
            tabs.append((label.split()[0], s.text(_read(wd / md, 8000))))
    nxt = next((label for label, files, _ in STAGES if not any((wd / f).exists() for f in files)), None)
    body = [s.header(f"Ticket progress · {key}", str(wd), "folder", f"{done}/{len(STAGES)}"), s.divider(),
            s.column(rows)]
    if tabs:
        body.append(s.tabs(tabs))
    body.append(s.row([s.chat_button(f"Continue: {nxt}" if nxt else "Show final summary",
                                     f"continue {key}", "primary", "play")], justify="end"))
    s.root(s.card(s.column(body)))
    return s.messages(), f"Ticket panel shown for {key}: {done}/{len(STAGES)} stages done; next: {nxt or 'none'}."


def _manifest() -> dict:
    try:
        return json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _report_screen(rep: dict, preview: bool, source: str = "", args: list[str] | None = None):
    s = A.Surface(_sid("install_preview" if preview else "install_report"))
    ver = rep.get("version", "")
    title = f"Toolkit {'update preview' if preview else 'installed'} · {ver}"
    old = (_manifest().get("version") or "") if preview else ""
    sub = (f"Installed now: {old} · " if old else "") + ("dry run, nothing written yet" if preview
                                                         else str(rep.get("installed_at", "")))
    open_items = [c for c in rep.get("checklist") or [] if not c.get("ok")]
    badge = "Needs your OK" if preview else ("✅ Ready" if not open_items else f"{len(open_items)} to finish")
    body = [s.header(title, sub, "download" if preview else "check", badge), s.divider()]
    sections = []
    done = rep.get("done") or []
    if done:
        sections.append(("Will do" if preview else "Done",
                         s.column([s.row([s.icon("check"), s.text(str(d).replace("(dry run) ", ""), weight=1)],
                                         align="start") for d in done[:40]])))
    manual = rep.get("manual") or []
    if manual:
        sections.append(("Manual steps", s.text("\n".join(f"{i}. {m}" for i, m in enumerate(manual, 1)))))
    if rep.get("checklist"):
        sections.append(("Checklist", _checklist_rows(s, rep["checklist"])))
    hooks = rep.get("hooks") or []
    if hooks:
        sections.append(("Hooks", s.column([s.status_line("settings", f"{h.get('name')} ({h.get('type')})",
                                                           str(h.get("status")), str(h.get("path")))
                                            for h in hooks[:30]])))
    notes = rep.get("notes") or []
    if notes:
        sections.append(("Notes", s.text("\n".join(f"- {n}" for n in notes))))
    if sections:
        body.append(s.tabs(sections))
    if preview:
        cmd = " ".join([Path(sys.executable).name or "python3", str(Path(source) / "install.py")] + list(args or []))
        body.append(s.card(s.column([s.text("Command", "caption"), s.text(f"`{cmd}`")])))
        body.append(s.row([s.chat_button("Cancel", "no, do not install", "borderless", "close"),
                           s.chat_button("Install", f"yes, run the installer: {cmd}", "primary", "download")],
                          justify="end"))
    elif open_items:
        body.append(s.row([s.button("Re-check", "sdlc_ui_checklist_refresh", {}, "default", "refresh"),
                           s.chat_button("Help me finish setup", "help me finish the post-install checklist",
                                         "primary", "arrowForward")], justify="end"))
    s.root(s.card(s.column(body)))
    return s


def screen_install_preview(cp, a: dict):
    source = str(a.get("source") or _manifest().get("source") or "").strip()
    if not source:
        raise ToolError("Give `source`: the toolkit clone that holds install.py.")
    src = Path(source).expanduser().resolve()
    if not (src / "install.py").is_file():
        raise ToolError(f"No install.py in {src}.")
    extra = [str(x) for x in a.get("args") or [] if str(x) not in ("--uninstall",)]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.json"
        try:
            proc = subprocess.run([sys.executable, str(src / "install.py"), "--dry-run", "--report-json", str(out)]
                                  + extra, cwd=str(src), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                  timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"Dry run failed: {exc}")
        if not out.exists():
            raise ToolError("Dry run wrote no report (installer too old for --report-json?).\n" + proc.stdout[-2000:])
        rep = json.loads(out.read_text(encoding="utf-8"))
    s = _report_screen(rep, True, str(src), extra)
    return s.messages(), (f"Install preview shown ({len(rep.get('done') or [])} changes). Wait for the developer's "
                          "'yes' in the chat before running the installer.")


def screen_install_report(cp, a: dict):
    p = HERE.parent / "install-report.json"
    try:
        rep = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ToolError(f"No install report at {p}. Run the installer first.")
    s = _report_screen(rep, False)
    open_n = len([c for c in rep.get("checklist") or [] if not c.get("ok")])
    return s.messages(), f"Install report shown: {open_n} checklist item(s) still open."


def _checklist_rows(s: A.Surface, items: list[dict]) -> str:
    rows = []
    for it in items:
        ic = "done" if it.get("ok") else ("refresh" if it.get("state") == "indexing" else "warning")
        steps = "" if it.get("ok") else "\n".join(f"- `{x}`" if " " in x and "/" in x else f"- {x}"
                                                   for x in it.get("steps") or [])
        rows.append(s.status_line(ic, str(it.get("title") or it.get("name")), "done" if it.get("ok") else "to do",
                                  str(it.get("summary") or "")))
        if steps:
            rows.append(s.text(steps, "caption"))
    return s.column(rows)


def _check_folder(cp, a: dict, roots: Path | None) -> Path:
    if a.get("folder"):
        return Path(str(a["folder"])).expanduser().resolve()
    if roots and not S._home_or_root(roots):
        return roots
    return S.workspace_root(cp)


def screen_checklist(cp, a: dict, roots: Path | None = None):
    folder = _check_folder(cp, a, roots)
    items = S.checklist(cp, folder, S.checks_offline())
    open_n = len([i for i in items if not i.get("ok")])
    s = A.Surface(_sid("checklist"))
    body = [s.header("Setup checklist", str(folder), "settings", "✅ All set" if not open_n else f"{open_n} to do"),
            s.divider(), _checklist_rows(s, items)]
    btn = [s.button("Re-check", "sdlc_ui_checklist_refresh", {"folder": str(folder)}, "default", "refresh")]
    orbit = next((i for i in items if i.get("name") == "orbit" and not i.get("ok")), None)
    if orbit:
        btn.append(s.chat_button("Index Orbit now", f"run the Orbit index for {folder}", "primary", "play"))
    body.append(s.row(btn, justify="end"))
    s.root(s.card(s.column(body)))
    text = "Setup checklist shown: " + "; ".join(f"{i['title']}: {'done' if i['ok'] else 'to do'}" for i in items)
    return s.messages(), text


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------


def ui_mode(cp) -> str:
    mode = (S.cfg(cp, "ui", "mode", "auto") if cp.has_section("ui") else "auto").lower()
    return mode if mode in ("auto", "on", "off") else "auto"


def client_has_ui(params: dict) -> bool:
    caps = params.get("capabilities") or {}
    ext = caps.get("extensions") or (caps.get("experimental") or {})
    if isinstance(ext, dict) and UI_EXTENSION in ext:
        return True
    info = params.get("clientInfo") or {}
    return bool(KNOWN_UI_CLIENTS.search(f"{info.get('name', '')} {info.get('title', '')}"))


class Server:
    def __init__(self, cp, stdout=None):
        self.cp = cp
        self.out = stdout or sys.stdout
        self.lock = threading.Lock()
        self.ui = False
        self.roots: Path | None = None
        self.client_roots = False
        self.pending: dict = {}
        self._rid = 0

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
                if isinstance(m, dict):
                    self.dispatch(m)

    def ask_roots(self):
        self._rid += 1
        rid = f"sdlc-ui-roots-{self._rid}"
        self.pending[rid] = self.on_roots
        self.send({"jsonrpc": "2.0", "id": rid, "method": "roots/list"})

    def on_roots(self, msg: dict):
        for r in ((msg.get("result") or {}).get("roots") or []):
            uri = str(r.get("uri", ""))
            if uri.startswith("file://"):
                path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
                if re.match(r"^/[A-Za-z]:", path):
                    path = path[1:]
                self.roots = Path(path)
                return

    def dispatch(self, m: dict):
        method = m.get("method")
        if method is None and "id" in m:
            cb = self.pending.pop(m["id"], None)
            if cb:
                cb(m)
            return
        if method == "notifications/initialized" or method == "notifications/roots/list_changed":
            if self.client_roots:
                self.ask_roots()
            return
        reply = self.handle(m)
        if reply is not None:
            self.send(reply)

    def tools(self) -> list[dict]:
        return list(TOOLS) if self.ui else []

    def call(self, name: str, a: dict) -> dict:
        cp = self.cp
        screens = {
            "sdlc_ui_confirm": lambda: screen_confirm(a),
            "sdlc_ui_summary": lambda: screen_summary(a),
            "sdlc_ui_plan": lambda: screen_plan(cp, a),
            "sdlc_ui_quality": lambda: screen_quality(cp, a),
            "sdlc_ui_ticket": lambda: screen_ticket(cp, a),
            "sdlc_ui_install_preview": lambda: screen_install_preview(cp, a),
            "sdlc_ui_install_report": lambda: screen_install_report(cp, a),
            "sdlc_ui_checklist": lambda: screen_checklist(cp, a, self.roots),
            "sdlc_ui_checklist_refresh": lambda: screen_checklist(cp, a, self.roots),
        }
        try:
            messages, text = screens[name]()
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:  # never kill the server on one bad call
            log(f"{name}: {type(exc).__name__}: {exc}")
            return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
        problems = A.check(messages)
        if problems:
            return {"content": [{"type": "text", "text": "UI payload invalid: " + "; ".join(problems)}], "isError": True}
        return {"content": [
            {"type": "text", "text": text},
            {"type": "resource", "resource": {"uri": f"a2ui://sdlc/{messages[0]['createSurface']['surfaceId']}",
                                              "mimeType": A.MIME, "text": json.dumps(messages, ensure_ascii=False)}},
        ]}

    def handle(self, msg: dict) -> dict | None:
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}

        def ok(result):
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code, message):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

        if not isinstance(method, str):
            return err(-32600, "Invalid Request") if "id" in msg else None
        if "id" not in msg:
            return None  # notification
        if method == "initialize":
            mode = ui_mode(self.cp)
            self.ui = mode == "on" or (mode == "auto" and client_has_ui(params))
            self.client_roots = isinstance((params.get("capabilities") or {}).get("roots"), dict)
            info = params.get("clientInfo") or {}
            log(f"client {info.get('name')!r}: panels {'on' if self.ui else 'off'} (mode {mode})")
            want = params.get("protocolVersion")
            return ok({
                "protocolVersion": want if want in PROTOCOLS else PROTOCOLS[1],
                "capabilities": {"tools": {"listChanged": False}, "resources": {},
                                 "extensions": {UI_EXTENSION: {}}},
                "serverInfo": {"name": SERVER_NAME, "title": "SDLC AI Toolkit UI", "version": _version()},
                "instructions": ("Interactive panels for the SDLC agents and skills. Show results with sdlc_ui_* "
                                 "instead of long text: sdlc_ui_summary after every stage, sdlc_ui_confirm before "
                                 "every confirm_before action, sdlc_ui_plan at checkpoint 1. Panel buttons only send "
                                 "a chat message; always wait for the developer's reply.") if self.ui else
                                "No panels in this editor; use the normal text output.",
            })
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": self.tools()})
        if method == "tools/call":
            name = params.get("name")
            if not self.ui or name not in {t["name"] for t in TOOLS}:
                return err(-32602, f"Unknown tool: {name}")
            return ok(self.call(name, params.get("arguments") or {}))
        if method == "resources/list":
            return ok({"resources": [{"uri": APP_URI, "name": "sdlc-ui", "title": "SDLC AI Toolkit panel",
                                      "mimeType": APP_MIME}] if self.ui else []})
        if method == "resources/templates/list":
            return ok({"resourceTemplates": []})
        if method == "resources/read":
            if params.get("uri") != APP_URI:
                return err(-32002, f"Resource not found: {params.get('uri')}")
            try:
                html = BUNDLE.read_text(encoding="utf-8")
            except OSError:
                return err(-32002, f"UI bundle missing: {BUNDLE}. Re-run the toolkit installer.")
            return ok({"contents": [{"uri": APP_URI, "mimeType": APP_MIME, "text": html,
                                     "_meta": {"ui": {"csp": {"connectDomains": [], "resourceDomains": []},
                                                      "prefersBorder": False}}}]})
        if method == "prompts/list":
            return ok({"prompts": []})
        return err(-32601, f"Method not found: {method}")


def _version() -> str:
    v = HERE.parent / "VERSION"
    return v.read_text(encoding="utf-8").strip() if v.exists() else "dev"


def main(argv=None) -> int:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    Server(load_cp()).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
