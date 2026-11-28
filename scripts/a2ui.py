"""Tiny A2UI v1.0 message builder (basic catalog only) for the SDLC AI Toolkit UI server.

Builds the `createSurface` message that `scripts/ui/sdlc-ui.html` (the bundled
A2UI Lit renderer) draws. Only components and enum values of the A2UI v1.0
basic catalog are produced, so a standard renderer accepts every payload.

    s = Surface("plan_PROJ_1")
    title = s.text("### Plan")
    s.root(s.card(s.column([title])))
    messages = s.messages(data={"comment": ""})

Standard library only; Python 3.8+.
"""
from __future__ import annotations

import itertools
import re

VERSION = "1.0"
CATALOG = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"
MIME = "application/a2ui+json"
MAX_TEXT = 20_000

COMPONENTS = {"Text", "Image", "Icon", "Video", "AudioPlayer", "Row", "Column", "List", "Card", "Tabs",
              "Modal", "Divider", "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput"}
ICONS = {"accountCircle", "add", "arrowBack", "arrowForward", "attachFile", "calendarToday", "call", "camera",
         "check", "close", "delete", "download", "edit", "event", "error", "fastForward", "favorite", "favoriteOff",
         "folder", "help", "home", "info", "locationOn", "lock", "lockOpen", "mail", "menu", "moreVert", "moreHoriz",
         "notificationsOff", "notifications", "pause", "payment", "person", "phone", "photo", "play", "print",
         "refresh", "rewind", "search", "send", "settings", "share", "shoppingCart", "skipNext", "skipPrevious",
         "star", "starHalf", "starOff", "stop", "upload", "visibility", "visibilityOff", "volumeDown", "volumeMute",
         "volumeOff", "volumeUp", "warning"}
# Material Design icon paths (Apache-2.0, 24x24). Sent as Icon {svgPath} so the panel needs no icon
# font: MCP App iframes block external fonts, and the ligature names would show as plain words.
ICON_PATHS = {
    "check": "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
    "done": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
    "todo": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z",
    "close": "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
    "edit": "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
    "error": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z",
    "warning": "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
    "info": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z",
    "help": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z",
    "lock": "M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z",
    "folder": "M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z",
    "share": "M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z",
    "arrowForward": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    "play": "M8 5v14l11-7z",
    "refresh": "M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
    "settings": "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z",
    "download": "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
    "upload": "M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z",
    "search": "M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
    "star": "M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z",
    "send": "M2.01 21L23 12 2.01 3 2 10l15 2-15 2z",
    "mail": "M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z",
    "skipNext": "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
}
JUSTIFY = {"center", "end", "spaceAround", "spaceBetween", "spaceEvenly", "start", "stretch"}
ALIGN = {"start", "center", "end", "stretch"}

_ID_BAD = re.compile(r"[^A-Za-z0-9_]")


def ident(text: str) -> str:
    """A UAX #31 style identifier (letters, digits, `_`; not starting with a digit)."""
    s = _ID_BAD.sub("_", str(text)) or "x"
    return s if not s[0].isdigit() else "_" + s


def clip(text, limit: int = MAX_TEXT) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + "\n\n… (shortened, open the file for the rest)"


class Surface:
    def __init__(self, surface_id: str):
        self.id = ident(surface_id)
        self.components: list[dict] = []
        self._n = itertools.count(1)
        self._root: str | None = None

    # ------------------------------------------------------------ core
    def add(self, component: str, cid: str | None = None, **props) -> str:
        if component not in COMPONENTS:
            raise ValueError(f"not a basic catalog component: {component}")
        cid = ident(cid) if cid else f"{component.lower()}_{next(self._n)}"
        node = {"id": cid, "component": component}
        node.update({k: v for k, v in props.items() if v is not None})
        self.components.append(node)
        return cid

    def root(self, child: str) -> str:
        self._root = self.add("Column", "root", children=[child], align="stretch")
        return self._root

    def messages(self, data: dict | None = None) -> list[dict]:
        if not self._root:
            raise ValueError("call root() first")
        create = {"surfaceId": self.id, "catalogId": CATALOG, "components": self.components}
        if data:
            create["dataModel"] = data
        return [{"version": VERSION, "createSurface": create}]

    # ------------------------------------------------------------ components
    def text(self, text, variant: str | None = None, weight: float | None = None) -> str:
        if isinstance(text, str):
            text = clip(text)
        return self.add("Text", text=text, variant=variant if variant in ("caption", "body") else None, weight=weight)

    def icon(self, name: str) -> str:
        if name in ICON_PATHS:
            return self.add("Icon", name={"svgPath": ICON_PATHS[name]})
        return self.add("Icon", name=name if name in ICONS else "info")

    def row(self, children: list[str], justify: str = "start", align: str = "center", weight=None) -> str:
        return self.add("Row", children=[c for c in children if c], justify=justify if justify in JUSTIFY else None,
                        align=align if align in ALIGN else None, weight=weight)

    def column(self, children: list[str], align: str = "stretch", weight=None) -> str:
        return self.add("Column", children=[c for c in children if c], align=align if align in ALIGN else None,
                        weight=weight)

    def card(self, child: str) -> str:
        return self.add("Card", child=child)

    def divider(self) -> str:
        return self.add("Divider", axis="horizontal")

    def tabs(self, tabs: list[tuple[str, str]]) -> str:
        return self.add("Tabs", tabs=[{"title": t, "child": c} for t, c in tabs])

    def button(self, label: str, action: str, context: dict | None = None, variant: str = "default",
               icon: str | None = None) -> str:
        inner = self.text(label)
        if icon:
            inner = self.row([self.icon(icon), inner], align="center")
        event = {"name": action}
        if context:
            event["context"] = context
        return self.add("Button", child=inner, variant=variant if variant in ("default", "primary", "borderless")
                        else "default", action={"event": event})

    def text_field(self, label: str, path: str, placeholder: str = "", long: bool = True) -> str:
        return self.add("TextField", label=label, value={"@path": path}, placeholder=placeholder or None,
                        variant="longText" if long else "shortText")

    # ------------------------------------------------------------ toolkit patterns
    def header(self, title: str, subtitle: str = "", icon: str = "info", badge: str = "") -> str:
        head = [self.text(f"### {title}")]
        if subtitle:
            head.append(self.text(subtitle, "caption"))
        parts = [self.icon(icon), self.column(head, weight=1)]
        if badge:
            parts.append(self.text(f"**{badge}**"))
        return self.row(parts, justify="spaceBetween", align="center")

    def facts(self, pairs: list[tuple[str, str]]) -> str | None:
        rows = [self.row([self.text(str(k), "caption", weight=1), self.text(str(v), weight=3)], align="start")
                for k, v in pairs if str(v or "").strip()]
        return self.column(rows) if rows else None

    def status_line(self, icon: str, label: str, state: str, detail: str = "") -> str:
        main = [self.text(f"**{label}**")]
        if detail:
            main.append(self.text(detail, "caption"))
        return self.row([self.icon(icon), self.column(main, weight=1), self.text(state, "caption")],
                        justify="spaceBetween", align="center")

    def chat_button(self, label: str, reply: str, variant: str = "default", icon: str | None = None,
                    comment_path: str | None = None, require_comment: bool = False) -> str:
        ctx = {"text": reply}
        if comment_path:
            ctx["comment"] = {"@path": comment_path}
        if require_comment:
            ctx["require_comment"] = "true"
        return self.button(label, "sdlc.chat", ctx, variant, icon)

    def link_button(self, label: str, url: str) -> str:
        return self.button(label, "sdlc.open", {"url": url}, "borderless", "share")


def check(messages: list[dict]) -> list[str]:
    """Structural checks a renderer would also make: ids unique, every child exists, one root."""
    problems = []
    for m in messages:
        cs = (m.get("createSurface") or {}).get("components") or (m.get("updateComponents") or {}).get("components")
        if not cs:
            continue
        ids = [c["id"] for c in cs]
        if len(ids) != len(set(ids)):
            problems.append("duplicate component ids")
        if "root" not in ids:
            problems.append("no root component")
        known = set(ids)
        for c in cs:
            if c["component"] not in COMPONENTS:
                problems.append(f"{c['id']}: unknown component {c['component']}")
            refs = list(c.get("children") or []) + ([c["child"]] if c.get("child") else [])
            refs += [t["child"] for t in c.get("tabs") or []]
            problems += [f"{c['id']}: missing child {r}" for r in refs if r not in known]
    return problems
