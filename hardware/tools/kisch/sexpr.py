# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal S-expression reader/writer for KiCad files.

Lists become Python lists, quoted strings become `Str`, everything else stays
a plain `str` atom, so a parse/serialize round trip keeps quoting intact.
"""
from __future__ import annotations


class Str(str):
    """A quoted string token."""


def parse(text: str):
    tokens = _tokenize(text)
    pos = 0

    def read():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            out = []
            while tokens[pos] != ")":
                out.append(read())
            pos += 1
            return out
        return tok

    result = read()
    return result


def _tokenize(text: str) -> list:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    nxt = text[j + 1]
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, nxt))
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            out.append(Str("".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            out.append(text[i:j])
            i = j
    return out


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dumps(node, indent: int = 0) -> str:
    """Serialize with one list per line for nested lists, KiCad style."""
    if isinstance(node, Str):
        return quote(node)
    if not isinstance(node, list):
        return str(node)
    if not any(isinstance(x, list) for x in node):
        return "(" + " ".join(dumps(x) for x in node) + ")"
    pad = "\t" * (indent + 1)
    head, rest = [], []
    for x in node:
        (rest if (isinstance(x, list) or rest) else head).append(x)
    s = "(" + " ".join(dumps(x) for x in head)
    for x in rest:
        s += "\n" + pad + dumps(x, indent + 1)
    return s + "\n" + "\t" * indent + ")"


def find(node: list, key: str):
    """First child list whose head is `key`."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node: list, key: str) -> list:
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
