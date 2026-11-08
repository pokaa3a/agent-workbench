#!/usr/bin/env python3
"""Parse the small, deterministic YAML subset used by the framework.

Supported constructs: indentation-based mappings (two-space indent), scalar
block lists, inline lists/maps, quoted or plain scalars, numbers, booleans,
null, and JSON documents. Anchors, aliases, tags, block scalars (| and >),
multi-line plain scalars, and list-of-map shorthand (``- key: value``) are
unsupported and rejected with an error instead of being silently misread, so
the same files parse consistently without third-party packages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*$")
MAP_ITEM_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*:(\s|$)")


class YamlSubsetError(ValueError):
    """Report unsupported or malformed framework YAML."""


@dataclass(frozen=True)
class Line:
    number: int
    indent: int
    content: str


def strip_comment(raw: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        # A quote opens a quoted scalar only at the start of a value token;
        # an apostrophe inside a plain word (e.g. "don't") is literal text.
        if character in {"'", '"'} and (index == 0 or raw[index - 1] in " \t[{,:-"):
            quote = character
            continue
        if character == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index]
    return raw


def split_inline(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'} and (index == 0 or value[index - 1] in " \t[{,:"):
            quote = character
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def parse_scalar(raw: str, line_number: int) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise YamlSubsetError(f"line {line_number}: invalid quoted string") from exc
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise YamlSubsetError(f"line {line_number}: unterminated string")
        return value[1:-1].replace("''", "'")
    if value.startswith("["):
        if not value.endswith("]"):
            raise YamlSubsetError(f"line {line_number}: unterminated inline list")
        inside = value[1:-1].strip()
        return [] if not inside else [
            parse_scalar(part, line_number) for part in split_inline(inside)
        ]
    if value.startswith("{"):
        if not value.endswith("}"):
            raise YamlSubsetError(f"line {line_number}: unterminated inline map")
        result: dict[str, Any] = {}
        inside = value[1:-1].strip()
        if not inside:
            return result
        for part in split_inline(inside):
            if ":" not in part:
                raise YamlSubsetError(f"line {line_number}: invalid inline map item")
            key, child = (piece.strip() for piece in part.split(":", 1))
            if not KEY_RE.fullmatch(key):
                raise YamlSubsetError(f"line {line_number}: invalid key {key!r}")
            if key in result:
                raise YamlSubsetError(f"line {line_number}: duplicate key {key!r}")
            result[key] = parse_scalar(child, line_number)
        return result
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?(0|[1-9]\d*)", value):
        return int(value)
    if re.fullmatch(r"-?(0|[1-9]\d*)\.\d+", value):
        return float(value)
    if value.startswith(("&", "*", "!", "|", ">")):
        raise YamlSubsetError(
            f"line {line_number}: unsupported YAML feature in {value!r}"
        )
    return value


def tokenize(text: str) -> list[Line]:
    result: list[Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError(f"line {number}: tabs are not allowed for indentation")
        cleaned = strip_comment(raw).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        if indent % 2:
            raise YamlSubsetError(f"line {number}: indentation must use two spaces")
        result.append(Line(number, indent, cleaned[indent:]))
    return result


def parse_block(lines: list[Line], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines) or lines[index].indent != indent:
        line_number = lines[index].number if index < len(lines) else "EOF"
        raise YamlSubsetError(f"line {line_number}: unexpected indentation")
    is_list = lines[index].content == "-" or lines[index].content.startswith("- ")
    container: Any = [] if is_list else {}

    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YamlSubsetError(f"line {line.number}: unexpected indentation")

        line_is_list = line.content == "-" or line.content.startswith("- ")
        if line_is_list != is_list:
            raise YamlSubsetError(f"line {line.number}: cannot mix lists and mappings")

        if is_list:
            item = line.content[1:].strip()
            if not item:
                raise YamlSubsetError(
                    f"line {line.number}: list items must be scalar or inline values"
                )
            if MAP_ITEM_RE.match(item):
                raise YamlSubsetError(
                    f"line {line.number}: list-of-map shorthand is unsupported; "
                    "quote the item or use an inline map {key: value}"
                )
            container.append(parse_scalar(item, line.number))
            index += 1
            continue

        if ":" not in line.content:
            raise YamlSubsetError(f"line {line.number}: expected key: value")
        key, raw_value = (part.strip() for part in line.content.split(":", 1))
        if not KEY_RE.fullmatch(key):
            raise YamlSubsetError(f"line {line.number}: invalid key {key!r}")
        if key in container:
            raise YamlSubsetError(f"line {line.number}: duplicate key {key!r}")
        index += 1
        if raw_value:
            container[key] = parse_scalar(raw_value, line.number)
        elif index < len(lines) and lines[index].indent > indent:
            child_indent = lines[index].indent
            if child_indent != indent + 2:
                raise YamlSubsetError(
                    f"line {lines[index].number}: nested content must indent two spaces"
                )
            container[key], index = parse_block(lines, index, child_indent)
        else:
            container[key] = {}
    return container, index


def loads(text: str) -> Any:
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise YamlSubsetError(f"invalid JSON-compatible YAML: {exc}") from exc
    lines = tokenize(text)
    if not lines:
        return {}
    if lines[0].indent != 0:
        raise YamlSubsetError(f"line {lines[0].number}: top level must not be indented")
    value, index = parse_block(lines, 0, 0)
    if index != len(lines):
        raise YamlSubsetError(f"line {lines[index].number}: unexpected content")
    return value


def load_frontmatter(text: str) -> dict[str, Any] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            value = loads("\n".join(lines[1:index]))
            if not isinstance(value, dict):
                raise YamlSubsetError("frontmatter must be a mapping")
            return value
    raise YamlSubsetError("unterminated YAML frontmatter")
