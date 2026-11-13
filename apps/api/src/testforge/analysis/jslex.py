"""A small JavaScript and TypeScript lexer for static analysis.

It does not build a syntax tree. It produces a *masked* copy of the source: the same
length and the same line breaks, with the contents of comments, strings, template
literals and regular expression literals replaced by spaces. Brace matching, keyword
search and comma splitting then work on code only, and every offset still points at the
same place in the original text. Nothing is evaluated.
"""

from __future__ import annotations

import re

# After one of these (ignoring whitespace), a "/" starts a regular expression literal.
_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = {
    "return",
    "typeof",
    "case",
    "in",
    "of",
    "new",
    "delete",
    "void",
    "throw",
    "else",
    "do",
    "yield",
    "await",
}
_WORD = re.compile(r"[A-Za-z_$][\w$]*$")


def _blank(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] != "\n":
            chars[i] = " "


def _prev_significant(chars: list[str], i: int) -> tuple[str, str]:
    """The previous non-space character and the word ending there (if any)."""
    j = i - 1
    while j >= 0 and chars[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return "", ""
    k = j
    while k >= 0 and (chars[k].isalnum() or chars[k] in "_$"):
        k -= 1
    word = "".join(chars[k + 1 : j + 1])
    return chars[j], word if _WORD.match(word or "-") else ""


def mask(text: str) -> str:
    chars = list(text)
    n = len(chars)
    i = 0
    while i < n:
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end == -1 else end
            _blank(chars, i, end)
            i = end
        elif c == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            _blank(chars, i, end)
            i = end
        elif c in ("'", '"'):
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            _blank(chars, i + 1, min(j, n))
            i = j + 1
        elif c == "`":
            j = _template_end(text, i + 1)
            _blank(chars, i + 1, min(j, n))
            i = j + 1
        elif c == "/":
            prev, word = _prev_significant(chars, i)
            if prev == "" or prev in _REGEX_BEFORE or word in _REGEX_KEYWORDS:
                j = i + 1
                in_class = False
                while j < n and text[j] != "\n":
                    ch = text[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        break
                    j += 1
                _blank(chars, i + 1, min(j, n))
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return "".join(chars)


def _template_end(text: str, i: int) -> int:
    """The index of the backtick closing a template literal that starts at ``i``."""
    n = len(text)
    depth = 0
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if depth == 0 and ch == "`":
            return i
        if ch == "$" and i + 1 < n and text[i + 1] == "{":
            depth += 1
            i += 2
            continue
        if depth and ch == "}":
            depth -= 1
        elif depth and ch == "`":
            i = _template_end(text, i + 1)
        i += 1
    return n


def match_close(masked: str, open_at: int) -> int:
    """The index of the bracket closing the one at ``open_at`` (({[), or -1."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    opener = masked[open_at]
    closer = pairs[opener]
    depth = 0
    for i in range(open_at, len(masked)):
        ch = masked[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def split_top_level(masked: str, original: str, start: int, end: int) -> list[str]:
    """Split ``original[start:end]`` at commas outside any bracket (masked decides)."""
    parts: list[str] = []
    depth = 0
    last = start
    angle = 0
    for i in range(start, end):
        ch = masked[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "<":
            angle += 1
        elif ch == ">" and angle and masked[i - 1] != "=":
            angle -= 1
        elif ch == "," and depth == 0 and angle == 0:
            parts.append(original[last:i].strip())
            last = i + 1
    tail = original[last:end].strip()
    if tail:
        parts.append(tail)
    return parts


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def depth_map(masked: str) -> list[int]:
    """Brace depth ({ }) at every offset, computed once."""
    depths = [0] * (len(masked) + 1)
    d = 0
    for i, ch in enumerate(masked):
        depths[i] = d
        if ch == "{":
            d += 1
        elif ch == "}":
            d = max(0, d - 1)
    depths[len(masked)] = d
    return depths
