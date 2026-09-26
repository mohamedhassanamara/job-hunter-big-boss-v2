"""Turn source HTML (or loose plain text) into the small markdown subset the UI renders:
paragraphs, `## ` headings and `- ` bullets. The original language is kept."""

import re
from html.parser import HTMLParser

_BLOCK = {
    "p", "div", "section", "article", "header", "footer", "blockquote", "pre", "table",
    "tr", "ul", "ol", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dl", "dt", "dd",
}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BOLD = {"strong", "b"}
_SKIP = {"script", "style", "noscript", "svg", "head"}
_BULLET_RE = re.compile(r"^\s*(?:[•·▪●◦*–—-]|\d+[.)])\s+")
_WS = re.compile(r"[ \t\r\f\v ]+")


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []  # (kind, text) kind: p | h | li
        self.buf: list[str] = []
        self.kind = "p"
        self.bold_depth = 0
        self.all_bold = True
        self.skip_depth = 0

    def _flush(self) -> None:
        text = _WS.sub(" ", "".join(self.buf)).strip()
        if text:
            kind = self.kind
            if kind == "p" and self.all_bold and len(text) <= 90 and not text.endswith("."):
                kind = "h"
                text = text.rstrip(":").strip()
            self.blocks.append((kind, text))
        self.buf, self.kind, self.all_bold = [], "p", True

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP:
            self.skip_depth += 1
        elif tag in _BLOCK:
            self._flush()
            if tag == "li":
                self.kind = "li"
            elif tag in _HEADINGS:
                self.kind = "h"
        elif tag in _BOLD:
            self.bold_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in _BLOCK:
            self._flush()
        elif tag in _BOLD:
            self.bold_depth = max(0, self.bold_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if data.strip() and not self.bold_depth:
            self.all_bold = False
        self.buf.append(data.replace("\n", " "))

    def close(self) -> None:
        super().close()
        self._flush()


def _plain_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for raw in text.replace("\r", "").split("\n"):
        line = _WS.sub(" ", raw).strip()
        if not line:
            blocks.append(("gap", ""))
        elif _BULLET_RE.match(line):
            blocks.append(("li", _BULLET_RE.sub("", line)))
        elif line.startswith("#"):
            blocks.append(("h", line.lstrip("# ").strip()))
        else:
            blocks.append(("p", line))
    return blocks


def _render(blocks: list[tuple[str, str]]) -> str:
    out: list[str] = []
    prev = None
    for kind, text in blocks:
        if kind == "gap":
            prev = "gap"
            continue
        line = f"- {text}" if kind == "li" else f"## {text}" if kind == "h" else text
        if out:
            out.append("\n" if kind == "li" and prev == "li" else "\n\n")
        out.append(line)
        prev = kind
    return "".join(out).strip()


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    if "<" not in value or not re.search(r"</?[a-zA-Z][^>]*>", value):
        return _render(_plain_blocks(value))
    parser = _Converter()
    parser.feed(value)
    parser.close()
    blocks: list[tuple[str, str]] = []
    for kind, text in parser.blocks:
        # Bullets typed as text inside paragraphs ("• foo") become real bullets too.
        if kind == "p" and _BULLET_RE.match(text):
            blocks.append(("li", _BULLET_RE.sub("", text)))
        else:
            blocks.append((kind, text))
    return _render(blocks)
