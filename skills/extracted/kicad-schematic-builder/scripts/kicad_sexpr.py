#!/usr/bin/env python3
"""Small KiCad S-expression reader shared by schematic audit modules."""

from __future__ import annotations

from collections.abc import Iterator, Sequence


SExpr = str | list["SExpr"]


def tokenize(text: str) -> Iterator[str]:
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if char in "()":
            yield char
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text):
                char = text[index]
                if char == '"':
                    index += 1
                    break
                if char == "\\" and index + 1 < len(text):
                    index += 1
                    escaped = text[index]
                    value.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
                else:
                    value.append(char)
                index += 1
            yield "".join(value)
            continue
        end = index
        while end < len(text) and not text[end].isspace() and text[end] not in "()":
            end += 1
        yield text[index:end]
        index = end


def parse(text: str) -> list[SExpr]:
    stack: list[list[SExpr]] = []
    root: list[SExpr] | None = None
    for token in tokenize(text):
        if token == "(":
            node: list[SExpr] = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("Unexpected closing parenthesis")
            root = stack.pop()
        else:
            if not stack:
                raise ValueError("Token outside root expression")
            stack[-1].append(token)
    if stack:
        raise ValueError("Unbalanced S-expression")
    if root is None:
        raise ValueError("Empty S-expression")
    return root


def node_name(node: SExpr) -> str:
    return node[0] if isinstance(node, list) and node and isinstance(node[0], str) else ""


def children(node: Sequence[SExpr], name: str) -> list[list[SExpr]]:
    return [item for item in node[1:] if isinstance(item, list) and node_name(item) == name]


def child(node: Sequence[SExpr], name: str) -> list[SExpr] | None:
    return next(iter(children(node, name)), None)


def atom(node: Sequence[SExpr] | None, index: int, default: str = "") -> str:
    if node is not None and len(node) > index and isinstance(node[index], str):
        return node[index]
    return default


def recursive_nodes(node: Sequence[SExpr], name: str) -> list[list[SExpr]]:
    found: list[list[SExpr]] = []
    for item in node:
        if not isinstance(item, list):
            continue
        if node_name(item) == name:
            found.append(item)
        found.extend(recursive_nodes(item, name))
    return found
