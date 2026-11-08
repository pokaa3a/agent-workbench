#!/usr/bin/env python3
"""Validate, summarize, search, and retrieve project-owned AI knowledge.

Commands:
  overview  compact cold-start map: read-first files, facets, open tasks,
            current knowledge catalog.
  query     budgeted, layered source selection for a request.
  search    bounded literal search over canonical knowledge, linked
            documents, and task files.
  validate  check the project contract, records, and relationships.
  index     write the optional derived index (never read by query).

Retrieval is read-only and reads files live, so edits are visible
immediately. All sizes are Unicode characters, not bytes or model tokens.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from yaml_subset import YamlSubsetError, load_frontmatter, loads as yaml_loads


FACET_NAME_RE = re.compile(r"[a-z][a-z0-9_-]*$")
RECORD_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]*$")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]+")
CJK_RUN_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]+")
STOPWORDS = {
    "a", "an", "and", "are", "about", "as", "at", "be", "by", "can", "do", "does",
    "explain", "for", "from", "how", "in", "is", "it", "me", "of", "on", "or",
    "please", "should", "tell", "the", "this", "that", "to", "was", "we", "what",
    "when", "where", "which", "who", "why", "with", "our", "you",
}
TASK_LINK_HEADINGS = {"related knowledge", "knowledge links", "相關知識"}
CLOSED_TASK_STATUSES = {"done", "closed", "completed", "complete", "cancelled", "canceled", "archived", "abandoned"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".yaml", ".yml", ".json", ".toml", ".adoc"}
MAX_SEARCH_FILE_CHARS = 400_000
PROJECT_KEYS = {"version", "storage", "facets", "context"}
STORAGE_KEYS = {"tasks", "knowledge", "history", "inbox", "index"}
CONTEXT_KEYS = {"always_load", "deterministic", "semantic", "budget"}
DETERMINISTIC_KEYS = {"include_history", "max_relationship_depth"}
SEMANTIC_KEYS = {"enabled", "command"}
BUDGET_KEYS = {"max_sources", "max_chars"}
RECORD_KEYS = {
    "id", "title", "summary", "facets", "applies_to", "topics", "related",
    "supersedes", "superseded_by", "source", "created", "updated",
    "last_verified", "attributes",
}
DEFAULT_STORAGE = {
    "tasks": "tasks",
    "knowledge": ".ai/knowledge",
    "history": ".ai/history",
    "inbox": ".ai/inbox",
    "index": ".ai/index",
}
LAYERS = ("always_loaded", "tasks", "deterministic", "explicit_relationships", "lexical", "semantic")


class KnowledgeError(Exception):
    """Report a deterministic project-knowledge failure."""


@dataclass(frozen=True)
class Record:
    identifier: str
    ref: str
    bucket: str
    title: str
    summary: str
    facets: dict[str, list[str]]
    applies_to: list[str]
    topics: list[str]
    relationships: list[tuple[str, str]]
    chars: int
    body_chars: int
    last_verified: str | None


@dataclass
class Task:
    identifier: str
    ref: str
    title: str
    status: str
    links: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Paths and configuration


def reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise KnowledgeError(f"{label} has unknown keys: {', '.join(unexpected)}")


def string_list(value: Any, label: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise KnowledgeError(f"{label} must be a list of non-empty strings")
    result: list[str] = []
    for item in value:
        normalized = item.strip()
        if normalized in result:
            raise KnowledgeError(f"{label} contains duplicate value {normalized!r}")
        result.append(normalized)
    if not allow_empty and not result:
        raise KnowledgeError(f"{label} must not be empty")
    return result


def project_path(project_root: Path, raw: str, label: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        raise KnowledgeError(f"{label} must be project-relative: {raw!r}")
    resolved = (project_root / path).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise KnowledgeError(f"{label} escapes the project root: {raw!r}") from exc
    return resolved


def relative_ref(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root).as_posix()


def parse_yaml_file(path: Path) -> dict[str, Any]:
    try:
        value = yaml_loads(path.read_text(encoding="utf-8"))
    except (OSError, YamlSubsetError) as exc:
        raise KnowledgeError(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError(f"{path} must contain a mapping")
    return value


def load_project_config(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / ".ai" / "project.yaml"
    if not path.is_file():
        raise KnowledgeError(f"Missing project contract: {path}")
    return normalize_project_config(project_root.resolve(), parse_yaml_file(path))


def normalize_project_config(project_root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    project_root = project_root.resolve()
    reject_unknown(raw, PROJECT_KEYS, ".ai/project.yaml")
    if isinstance(raw.get("version"), bool) or raw.get("version") != 1:
        raise KnowledgeError(".ai/project.yaml version must be 1")

    storage_raw = raw.get("storage", {})
    if not isinstance(storage_raw, dict):
        raise KnowledgeError("project.storage must be a mapping")
    reject_unknown(storage_raw, STORAGE_KEYS, "project.storage")
    storage = dict(DEFAULT_STORAGE)
    for name, value in storage_raw.items():
        if not isinstance(value, str) or not value.strip():
            raise KnowledgeError(f"project.storage.{name} must be a path string")
        storage[name] = value.strip()
    resolved = {name: project_path(project_root, value, f"project.storage.{name}") for name, value in storage.items()}
    for name, path in resolved.items():
        if path == project_root:
            raise KnowledgeError(f"project.storage.{name} cannot be the project root")
    names = list(resolved)
    for index, left_name in enumerate(names):
        left = resolved[left_name]
        for right_name in names[index + 1:]:
            right = resolved[right_name]
            if left == right or left in right.parents or right in left.parents:
                raise KnowledgeError(f"project.storage.{left_name} and project.storage.{right_name} must not overlap")

    facets_raw = raw.get("facets")
    if not isinstance(facets_raw, dict):
        raise KnowledgeError("project.facets must be a mapping")
    facets: dict[str, dict[str, Any]] = {}
    for name, definition in facets_raw.items():
        if not isinstance(name, str) or not FACET_NAME_RE.fullmatch(name):
            raise KnowledgeError(f"Invalid project facet name: {name!r}")
        if not isinstance(definition, dict):
            raise KnowledgeError(f"project.facets.{name} must be a mapping")
        reject_unknown(definition, {"description", "values"}, f"facet {name}")
        description = definition.get("description")
        if not isinstance(description, str) or not description.strip():
            raise KnowledgeError(f"facet {name} needs a description")
        values = string_list(definition.get("values"), f"facet {name}.values")
        facets[name] = {"description": description.strip(), "values": values}

    context_raw = raw.get("context", {})
    if not isinstance(context_raw, dict):
        raise KnowledgeError("project.context must be a mapping")
    reject_unknown(context_raw, CONTEXT_KEYS, "project.context")
    always_load = string_list(context_raw.get("always_load", []), "context.always_load")
    for index, ref in enumerate(always_load):
        policy_path = project_path(project_root, ref, f"context.always_load[{index}]")
        for area in ("inbox", "history", "tasks", "index"):
            if policy_path == resolved[area] or resolved[area] in policy_path.parents:
                raise KnowledgeError(f"context.always_load cannot contain {area} files: {ref}; use query options for tasks/history")

    deterministic_raw = context_raw.get("deterministic", {})
    if not isinstance(deterministic_raw, dict):
        raise KnowledgeError("context.deterministic must be a mapping")
    reject_unknown(deterministic_raw, DETERMINISTIC_KEYS, "context.deterministic")
    include_history = deterministic_raw.get("include_history", False)
    max_depth = deterministic_raw.get("max_relationship_depth", 2)
    if not isinstance(include_history, bool):
        raise KnowledgeError("context.deterministic.include_history must be boolean")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not 0 <= max_depth <= 10:
        raise KnowledgeError("context.deterministic.max_relationship_depth must be 0..10")

    semantic_raw = context_raw.get("semantic", {})
    if not isinstance(semantic_raw, dict):
        raise KnowledgeError("context.semantic must be a mapping")
    reject_unknown(semantic_raw, SEMANTIC_KEYS, "context.semantic")
    semantic_enabled = semantic_raw.get("enabled", False)
    command = string_list(semantic_raw.get("command", []), "context.semantic.command")
    if not isinstance(semantic_enabled, bool):
        raise KnowledgeError("context.semantic.enabled must be boolean")
    if semantic_enabled and not command:
        raise KnowledgeError("context.semantic.command is required when semantic retrieval is enabled")

    budget_raw = context_raw.get("budget", {})
    if not isinstance(budget_raw, dict):
        raise KnowledgeError("context.budget must be a mapping")
    reject_unknown(budget_raw, BUDGET_KEYS, "context.budget")
    max_sources = budget_raw.get("max_sources", 12)
    max_chars = budget_raw.get("max_chars", 40000)
    if not isinstance(max_sources, int) or isinstance(max_sources, bool) or not 1 <= max_sources <= 100:
        raise KnowledgeError("context.budget.max_sources must be 1..100")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1000:
        raise KnowledgeError("context.budget.max_chars must be at least 1000")

    return {
        "version": 1,
        "storage": storage,
        "storage_paths": resolved,
        "facets": facets,
        "context": {
            "always_load": always_load,
            "deterministic": {"include_history": include_history, "max_relationship_depth": max_depth},
            "semantic": {"enabled": semantic_enabled, "command": command},
            "budget": {"max_sources": max_sources, "max_chars": max_chars},
        },
    }


def bucket_of(config: dict[str, Any], path: Path) -> str:
    """Classify a resolved path by storage area; aliases resolve to the same bucket."""
    resolved = path.resolve()
    for name, root in config["storage_paths"].items():
        if resolved == root or root in resolved.parents:
            return name
    return "reference"


def text_chars(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


# --------------------------------------------------------------------------
# Records and tasks


def validate_classification(classification: dict[str, list[str]], config: dict[str, Any], label: str) -> None:
    for name, values in classification.items():
        if name not in config["facets"]:
            raise KnowledgeError(f"{label} uses undeclared facet {name!r}")
        allowed = set(config["facets"][name]["values"])
        for value in values:
            if value not in allowed:
                raise KnowledgeError(f"{label} uses invalid {name} value {value!r}; allowed: {', '.join(sorted(allowed))}")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body) for a Markdown file; frontmatter is '' when absent."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:])
    raise YamlSubsetError("unterminated YAML frontmatter")


def load_metadata(path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".md":
            value = load_frontmatter(text)
            _, body = split_frontmatter(text)
        else:
            value, body = yaml_loads(text), ""
    except (OSError, YamlSubsetError) as exc:
        raise KnowledgeError(f"Cannot parse metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError(f"Knowledge file lacks valid metadata: {path}")
    return value, body, text


def build_record(project_root: Path, path: Path, bucket: str, config: dict[str, Any]) -> Record:
    raw, body, text = load_metadata(path)
    ref = relative_ref(project_root, path)
    reject_unknown(raw, RECORD_KEYS, ref)
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not RECORD_ID_RE.fullmatch(identifier):
        raise KnowledgeError(f"{ref}.id must be a stable identifier")
    for name in ("title", "summary"):
        if name in raw and (not isinstance(raw[name], str) or not raw[name].strip()):
            raise KnowledgeError(f"{ref}.{name} must be a non-empty string when present")
    title = raw.get("title", "")
    summary = raw.get("summary", "")

    facets_raw = raw.get("facets", {})
    if not isinstance(facets_raw, dict):
        raise KnowledgeError(f"{ref}.facets must be a mapping")
    facets = {name: string_list(values, f"{ref}.facets.{name}", allow_empty=False) for name, values in facets_raw.items()}
    validate_classification(facets, config, ref)
    applies_to = string_list(raw.get("applies_to", []), f"{ref}.applies_to")
    for pattern in applies_to:
        path_value = Path(pattern)
        if path_value.is_absolute() or ".." in path_value.parts:
            raise KnowledgeError(f"{ref}.applies_to must contain project-relative globs")
    topics = string_list(raw.get("topics", []), f"{ref}.topics")
    relationships: list[tuple[str, str]] = []
    source = raw.get("source", [])
    if isinstance(source, str):
        source = [source]
    relationships.extend(("source", target) for target in string_list(source, f"{ref}.source"))
    for name in ("related", "supersedes", "superseded_by"):
        relationships.extend((name, target) for target in string_list(raw.get(name, []), f"{ref}.{name}"))
    attributes = raw.get("attributes", {})
    if not isinstance(attributes, dict):
        raise KnowledgeError(f"{ref}.attributes must be a mapping")
    for name in ("created", "updated", "last_verified"):
        value = raw.get(name)
        if value is not None:
            if not isinstance(value, str):
                raise KnowledgeError(f"{ref}.{name} must be YYYY-MM-DD")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise KnowledgeError(f"{ref}.{name} must be YYYY-MM-DD") from exc
    return Record(
        identifier, ref, bucket, title.strip(), summary.strip(), facets, applies_to, topics,
        relationships, len(text), len(body.strip()), raw.get("last_verified"),
    )


def discover_records(project_root: Path, config: dict[str, Any], buckets: tuple[str, ...] = ("knowledge", "history", "inbox")) -> tuple[list[Record], dict[str, Record]]:
    records: list[Record] = []
    by_reference: dict[str, Record] = {}
    identifiers: dict[str, str] = {}
    for bucket in buckets:
        root = config["storage_paths"][bucket]
        if not root.exists():
            continue
        if not root.is_dir():
            raise KnowledgeError(f"storage.{bucket} is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml"}:
                continue
            record = build_record(project_root, path, bucket, config)
            if record.identifier in identifiers:
                raise KnowledgeError(f"Duplicate knowledge ID {record.identifier}: {identifiers[record.identifier]}, {record.ref}")
            identifiers[record.identifier] = record.ref
            records.append(record)
            by_reference[record.identifier] = record
            by_reference[record.ref] = record
    return records, by_reference


def resolve_reference(project_root: Path, raw: str, by_reference: dict[str, Record]) -> tuple[str, Record | None]:
    if raw in by_reference:
        record = by_reference[raw]
        return record.ref, record
    path = project_path(project_root, raw, f"relationship {raw!r}")
    if not path.exists():
        raise KnowledgeError(f"Dangling explicit relationship: {raw}")
    if not path.is_file():
        raise KnowledgeError(f"Explicit relationship must identify a file: {raw}")
    ref = relative_ref(project_root, path)
    return ref, by_reference.get(ref)


def validate_relationships(project_root: Path, config: dict[str, Any], records: list[Record], by_reference: dict[str, Record]) -> None:
    for record in records:
        for relation, target in record.relationships:
            try:
                ref, _ = resolve_reference(project_root, target, by_reference)
            except KnowledgeError as exc:
                raise KnowledgeError(f"{record.ref} has invalid {relation} relationship: {exc}") from exc
            if record.bucket != "inbox" and bucket_of(config, project_root / ref) == "inbox":
                raise KnowledgeError(f"{record.ref} {relation} links to inbox candidate {ref}; canonical and historical records must not depend on unreviewed candidates")


def parse_task_link(line: str) -> str | None:
    item = line.lstrip()[2:].strip()
    link = re.match(r"\[[^\]]*\]\(([^)\s]+)\)", item)
    if link:
        item = link.group(1)
    item = item.strip("`").split(" ")[0].strip()
    if not item or item.startswith("{{"):
        return None
    return item


def discover_tasks(project_root: Path, config: dict[str, Any]) -> tuple[list[Task], list[str]]:
    root = config["storage_paths"]["tasks"]
    tasks: list[Task] = []
    identifiers: dict[str, str] = {}
    warnings: list[str] = []
    if not root.is_dir():
        return tasks, warnings
    for path in sorted(root.rglob("*.md")):
        ref = relative_ref(project_root, path)
        try:
            text = path.read_text(encoding="utf-8")
            metadata = load_frontmatter(text) or {}
        except (OSError, YamlSubsetError) as exc:
            warnings.append(f"Cannot parse task metadata {ref}: {exc}")
            continue
        identifier = metadata.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        identifier = identifier.strip()
        if identifier in identifiers:
            raise KnowledgeError(f"Duplicate task ID {identifier}: {identifiers[identifier]}, {ref}")
        identifiers[identifier] = ref
        title = metadata.get("title") if isinstance(metadata.get("title"), str) else ""
        links: list[str] = []
        in_section = False
        for raw in text.splitlines():
            stripped = raw.strip()
            if not title and stripped.startswith("# "):
                title = stripped[2:].strip()
            if stripped.startswith("## "):
                in_section = stripped[3:].strip().casefold() in TASK_LINK_HEADINGS
                continue
            if in_section and raw.lstrip().startswith("- "):
                link = parse_task_link(raw)
                if link and ("/" in link or Path(link).suffix):
                    # Markdown links are relative to the task file; prefer that when it exists.
                    local = (path.parent / link).resolve()
                    if local.is_file() and (local == project_root or project_root in local.parents):
                        link = relative_ref(project_root, local)
                if link:
                    links.append(link)
        status = metadata.get("status")
        tasks.append(Task(identifier.strip(), ref, title, str(status).strip() if status is not None else "unknown", links))
    return tasks, warnings


# --------------------------------------------------------------------------
# Matching


def query_terms(text: str) -> list[str]:
    """ASCII words (minus stopwords) plus CJK runs; long CJK runs become bigrams."""
    terms: list[str] = []
    for token in ASCII_TOKEN_RE.findall(text):
        lowered = token.casefold()
        if lowered not in STOPWORDS and lowered not in terms:
            terms.append(lowered)
    for run in CJK_RUN_RE.findall(text):
        pieces = [run] if len(run) <= 2 else [run[i:i + 2] for i in range(len(run) - 1)]
        for piece in pieces:
            if piece not in terms:
                terms.append(piece)
    return terms


def term_pattern(term: str) -> re.Pattern[str]:
    if CJK_RUN_RE.fullmatch(term):
        return re.compile(re.escape(term))
    # Word-start boundary: "token" matches "tokens", "id" does not match "grid".
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term), re.IGNORECASE)


def record_score(record: Record, facets: dict[str, list[str]], topics: list[str], paths: list[str], patterns: dict[str, re.Pattern[str]]) -> tuple[int, list[str]]:
    score = 5 if record.bucket == "knowledge" else 0
    reasons: list[str] = []
    for name, requested in facets.items():
        record_values = record.facets.get(name)
        if record_values and not set(record_values) & set(requested):
            return 0, []
        matches = sorted(set(record_values or []) & set(requested))
        if matches:
            score += 30 * len(matches)
            reasons.append(f"facet {name}={','.join(matches)}")
    requested_topics = {topic.casefold() for topic in topics}
    topic_matches = sorted(requested_topics & {topic.casefold() for topic in record.topics})
    if topic_matches:
        score += 25 * len(topic_matches)
        reasons.append(f"topic {','.join(topic_matches)}")
    path_matches: set[str] = set()
    for pattern in record.applies_to:
        for path in paths:
            if fnmatch.fnmatchcase(path, pattern) or path == pattern.rstrip("/"):
                path_matches.add(pattern)
    if path_matches:
        score += 35 * len(path_matches)
        reasons.append(f"path {','.join(sorted(path_matches))}")
    searchable = " ".join([record.identifier, record.title, record.summary, *record.topics])
    term_matches = [term for term, pattern in patterns.items() if pattern.search(searchable)]
    if term_matches:
        score += min(20, 4 * len(term_matches))
        reasons.append(f"request term {','.join(term_matches[:5])}")
    return (score, reasons) if reasons else (0, [])


def lexical_search(project_root: Path, config: dict[str, Any], terms: list[str], records: list[Record], by_reference: dict[str, Record], tasks: list[Task], include_history: bool, limit: int) -> list[dict[str, Any]]:
    """Literal search over canonical records, their linked documents, and task files."""
    if not terms:
        return []
    patterns = {term: term_pattern(term) for term in terms}
    corpus: dict[str, str] = {}
    for record in records:
        if record.bucket == "inbox" or (record.bucket == "history" and not include_history):
            continue
        corpus.setdefault(record.ref, record.bucket)
        for relation, target in record.relationships:
            if relation != "source":
                continue
            try:
                ref, linked = resolve_reference(project_root, target, by_reference)
            except KnowledgeError:
                continue
            if linked is None and bucket_of(config, project_root / ref) == "reference":
                corpus.setdefault(ref, "reference")
    for task in tasks:
        corpus.setdefault(task.ref, "task")
    hits: list[dict[str, Any]] = []
    for ref, kind in corpus.items():
        path = project_root / ref
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) > MAX_SEARCH_FILE_CHARS:
            continue
        record = by_reference.get(ref)
        numbered = list(enumerate(text.splitlines(), start=1))
        if record:
            # Search record metadata values and body, not raw frontmatter keys.
            skip = len(numbered) if path.suffix.lower() in {".yaml", ".yml"} else 0
            if not skip and numbered and numbered[0][1].strip() == "---":
                skip = next((i + 1 for i, (_, line) in enumerate(numbered[1:], start=1) if line.strip() == "---"), 0)
            heading = " — ".join(part for part in (record.title, record.summary, " ".join(record.topics)) if part)
            numbered = [(0, heading)] + numbered[skip:]
        matched: list[str] = []
        lines: list[int] = []
        snippets: list[str] = []
        occurrences = 0
        for number, line in numbered:
            found = [term for term, pattern in patterns.items() if pattern.search(line)]
            if not found:
                continue
            occurrences += len(found)
            for term in found:
                if term not in matched:
                    matched.append(term)
            if len(lines) < 3:
                lines.append(number)
                snippets.append(line.strip()[:160])
        if not matched:
            continue
        entry = {
            "ref": ref, "kind": kind, "reason": f"literal match {','.join(matched[:5])}",
            "score": 10 * len(matched) + min(occurrences, 10), "chars": len(text),
            "lines": lines, "snippets": snippets,
        }
        if record:
            entry["id"] = record.identifier
        hits.append(entry)
    hits.sort(key=lambda item: (-item["score"], item["ref"]))
    return hits[:limit]


def semantic_results(project_root: Path, config: dict[str, Any], payload: dict[str, Any], unresolved: list[str]) -> list[dict[str, Any]]:
    semantic = config["context"]["semantic"]
    try:
        process = subprocess.run(
            semantic["command"], cwd=project_root, input=json.dumps(payload, ensure_ascii=False),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        unresolved.append(f"Semantic retrieval failed: {exc}")
        return []
    if process.returncode != 0:
        unresolved.append(f"Semantic retrieval exited {process.returncode}: {process.stderr.strip()}")
        return []
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        unresolved.append(f"Semantic retrieval returned invalid JSON: {exc}")
        return []
    if not isinstance(value, list):
        unresolved.append("Semantic retrieval must return a JSON array")
        return []
    return [item for item in value if isinstance(item, dict)]


# --------------------------------------------------------------------------
# Budgeted selection


class Selection:
    """Admit sources in priority order while enforcing bucket rules and budgets."""

    def __init__(self, project_root: Path, config: dict[str, Any], include_history: bool, allowed_tasks: set[str]):
        self.project_root = project_root
        self.config = config
        self.include_history = include_history
        self.allowed_tasks = allowed_tasks
        self.max_sources = config["context"]["budget"]["max_sources"]
        self.max_chars = config["context"]["budget"]["max_chars"]
        self.layers: dict[str, list[dict[str, Any]]] = {name: [] for name in LAYERS}
        self.seen: set[str] = set()
        self.refused: set[str] = set()
        self.sources = 0
        self.chars = 0
        self.inline = 0
        self.omitted: list[dict[str, str]] = []
        self.excluded: list[dict[str, str]] = []
        self.mandatory_over_sources = False
        self.mandatory_over_chars = False

    def allowed(self, ref: str, reason: str) -> bool:
        bucket = bucket_of(self.config, self.project_root / ref)
        rule = None
        if bucket == "inbox":
            rule = "inbox candidates are never retrieved"
        elif bucket == "history" and not self.include_history:
            rule = "history requires --include-history"
        elif bucket == "index":
            rule = "derived index is not a knowledge source"
        elif bucket == "tasks" and ref not in self.allowed_tasks:
            rule = "task files are returned only for requested --task IDs"
        if rule is None:
            return True
        if ref not in self.refused:
            self.refused.add(ref)
            self.excluded.append({"ref": ref, "via": reason, "rule": rule})
        return False

    def admit(self, layer: str, entry: dict[str, Any], mandatory: bool = False, inline: bool = False) -> bool:
        ref = entry["ref"]
        if ref in self.seen:
            return True
        if not self.allowed(ref, entry["reason"]):
            return False
        cost = entry["chars"] if not inline else len(entry.get("title", "")) + len(entry.get("summary", ""))
        slots = 0 if inline else 1
        over_sources = bool(slots) and self.sources + slots > self.max_sources
        over_chars = self.chars + cost > self.max_chars
        if (over_sources or over_chars) and not mandatory:
            self.omitted.append({"ref": ref, "layer": layer, "reason": "max_sources" if over_sources else "max_chars"})
            return False
        self.mandatory_over_sources |= mandatory and over_sources
        self.mandatory_over_chars |= mandatory and over_chars
        if inline:
            entry["read"] = False
            self.inline += 1
        self.layers[layer].append({key: value for key, value in entry.items() if value not in (None, "", [])})
        self.seen.add(ref)
        self.sources += slots
        self.chars += cost
        return True

    def knowledge_selected(self) -> bool:
        return any(self.layers[name] for name in ("deterministic", "explicit_relationships", "lexical", "semantic"))


def record_entry(record: Record, reason: str, score: int) -> dict[str, Any]:
    return {
        "ref": record.ref, "id": record.identifier, "kind": record.bucket, "reason": reason, "score": score,
        "chars": record.chars, "title": record.title, "summary": record.summary,
        "last_verified": record.last_verified,
    }


def query_project(project_root: Path, query_text: str, raw_facets: list[str], topics: list[str], paths: list[str], task_ids: list[str], force_history: bool, force_search: bool = False, force_semantic: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_project_config(project_root)
    facets = parse_facets(raw_facets)
    validate_classification(facets, config, "query")
    topics = list(dict.fromkeys(item.strip() for item in topics if item.strip()))
    paths = list(dict.fromkeys(item.strip() for item in paths if item.strip()))
    task_ids = list(dict.fromkeys(item.strip() for item in task_ids if item.strip()))
    for index, raw in enumerate(paths):
        project_path(project_root, raw, f"query.path[{index}]")
    records, by_reference = discover_records(project_root, config)
    include_history = force_history or config["context"]["deterministic"]["include_history"]
    terms = query_terms(query_text)
    patterns = {term: term_pattern(term) for term in terms}
    unresolved: list[str] = []
    tasks, task_warnings = discover_tasks(project_root, config)
    tasks_by_id = {task.identifier: task for task in tasks}
    requested_tasks = [tasks_by_id[task_id] for task_id in task_ids if task_id in tasks_by_id]
    for task_id in task_ids:
        if task_id not in tasks_by_id:
            unresolved.append(f"Requested task not found: {task_id}")
    if task_ids:
        unresolved.extend(task_warnings)
    selection = Selection(project_root, config, include_history, {task.ref for task in requested_tasks})

    # 1. Mandatory policy sources.
    for raw in config["context"]["always_load"]:
        path = project_path(project_root, raw, "context.always_load")
        if not path.is_file():
            raise KnowledgeError(f"Always-loaded source is missing: {raw}")
        selection.admit("always_loaded", {"ref": relative_ref(project_root, path), "kind": "policy", "reason": "project always_load policy", "score": 1000, "chars": text_chars(path)}, mandatory=True)

    # 2. Explicitly requested tasks (authoritative goals/progress) are mandatory.
    for task in requested_tasks:
        selection.admit("tasks", {"ref": task.ref, "id": task.identifier, "kind": "task", "reason": f"requested task {task.identifier} ({task.status})", "score": 900, "chars": text_chars(project_root / task.ref), "title": task.title}, mandatory=True)

    # 3. Primary records: task links first, then ranked deterministic matches.
    primaries: list[tuple[str, str, Record | None, str, int]] = []  # (layer, ref, record, reason, score)
    for task in requested_tasks:
        for link in task.links:
            try:
                ref, record = resolve_reference(project_root, link, by_reference)
            except KnowledgeError as exc:
                unresolved.append(f"Task {task.identifier} link {link!r}: {exc}")
                continue
            primaries.append(("explicit_relationships", ref, record, f"task {task.identifier} related knowledge", 85))
    scored: list[tuple[int, Record, list[str]]] = []
    for record in records:
        if record.bucket != "knowledge" and not (record.bucket == "history" and include_history):
            continue
        score, reasons = record_score(record, facets, topics, paths, patterns)
        if score:
            scored.append((score, record, reasons))
    scored.sort(key=lambda item: (-item[0], item[1].ref))
    primaries.extend(("deterministic", record.ref, record, "; ".join(reasons), score) for score, record, reasons in scored)

    def admit_ref(layer: str, ref: str, record: Record | None, reason: str, score: int) -> bool:
        if record:
            entry = record_entry(record, reason, score)
            # Metadata-only records are delivered inline; their sources carry the content.
            inline = record.body_chars == 0 and any(rel == "source" for rel, _ in record.relationships)
            return selection.admit(layer, entry, inline=inline)
        return selection.admit(layer, {"ref": ref, "kind": "reference", "reason": reason, "score": score, "chars": text_chars(project_root / ref)})

    expansion: deque[tuple[Record, int]] = deque()
    for layer, ref, record, reason, score in primaries:
        if not admit_ref(layer, ref, record, reason, score) or record is None:
            continue
        # Direct sources immediately follow their record so a stub never starves its document.
        for relation, target in record.relationships:
            if relation != "source":
                continue
            try:
                source_ref, source_record = resolve_reference(project_root, target, by_reference)
            except KnowledgeError as exc:
                unresolved.append(str(exc))
                continue
            admit_ref("explicit_relationships", source_ref, source_record, f"{record.identifier} source", 80)
        expansion.append((record, 0))

    # 4. Remaining explicit relationships, breadth-first, to the configured depth.
    max_depth = config["context"]["deterministic"]["max_relationship_depth"]
    expanded: set[str] = set()
    while expansion:
        record, depth = expansion.popleft()
        if record.ref in expanded or depth >= max_depth:
            continue
        expanded.add(record.ref)
        for relation, target in record.relationships:
            try:
                ref, linked = resolve_reference(project_root, target, by_reference)
            except KnowledgeError as exc:
                unresolved.append(str(exc))
                continue
            if ref in selection.seen and linked is not None:
                expansion.append((linked, depth + 1))
                continue
            if admit_ref("explicit_relationships", ref, linked, f"{record.identifier} {relation}", 79 - depth) and linked is not None:
                expansion.append((linked, depth + 1))

    # 5. Lexical fallback: only on request or when structured layers found nothing.
    lexical_ran = False
    if terms and (force_search or not selection.knowledge_selected()):
        lexical_ran = True
        for hit in lexical_search(project_root, config, terms, records, by_reference, requested_tasks, include_history, limit=selection.max_sources):
            if hit["ref"] in selection.seen:
                continue
            selection.admit("lexical", hit)

    # 6. Semantic fallback: only when enabled and either requested or still empty.
    payload = {"query": query_text, "facets": facets, "topics": topics, "paths": paths, "tasks": task_ids}
    semantic = config["context"]["semantic"]
    if semantic["enabled"] and (force_semantic or not selection.knowledge_selected()):
        for item in semantic_results(project_root, config, payload, unresolved):
            raw, reason = item.get("ref"), item.get("reason")
            if not isinstance(raw, str) or not raw.strip() or not isinstance(reason, str) or not reason.strip():
                unresolved.append("Ignored malformed semantic result")
                continue
            try:
                ref, record = resolve_reference(project_root, raw.strip(), by_reference)
            except KnowledgeError as exc:
                unresolved.append(str(exc))
                continue
            score = item.get("score", 10)
            if isinstance(score, float) and not math.isfinite(score):
                unresolved.append("Ignored non-finite semantic score; using 10")
                score = 10
            score = int(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else 10
            if admit_ref("semantic", ref, record, f"semantic: {reason.strip()}", score) and record:
                for relation, target in record.relationships:
                    if relation != "source":
                        continue
                    try:
                        source_ref, source_record = resolve_reference(project_root, target, by_reference)
                    except KnowledgeError as exc:
                        unresolved.append(str(exc))
                        continue
                    admit_ref("semantic", source_ref, source_record, f"{record.identifier} source", score)
    elif force_semantic and not semantic["enabled"]:
        unresolved.append("Semantic retrieval requested but context.semantic.enabled is false")

    asked = bool(query_text.strip() or facets or topics or paths)
    if asked and not selection.knowledge_selected():
        hint = "" if lexical_ran or not terms else " Try --search for a literal body search."
        unresolved.append("No knowledge source matched the request; answer from code or ask, and consider recording durable findings." + hint)
    if selection.mandatory_over_sources:
        unresolved.append("Mandatory sources (always_load and requested tasks) exceed max_sources")
    if selection.mandatory_over_chars:
        unresolved.append("Mandatory sources (always_load and requested tasks) exceed max_chars")
    if selection.omitted:
        unresolved.append(f"Context budget omitted {len(selection.omitted)} lower-priority source(s); see budget.omitted")
    history_hidden = [item["ref"] for item in selection.excluded if item["rule"].startswith("history")]
    if history_hidden:
        unresolved.append(f"{len(history_hidden)} historical source(s) are linked but hidden; add --include-history for chronology or rationale")

    return {
        "schema_version": 2,
        "project_root": str(project_root),
        "query": payload,
        "layers": {name: entries for name, entries in selection.layers.items() if entries or name in {"always_loaded", "deterministic", "explicit_relationships"}},
        "excluded": selection.excluded,
        "budget": {
            "unit": "characters",
            "max_sources": selection.max_sources, "max_chars": selection.max_chars,
            "selected_sources": selection.sources, "selected_chars": selection.chars,
            "inline_records": selection.inline, "omitted": selection.omitted,
        },
        "unresolved": list(dict.fromkeys(unresolved)),
    }


def parse_facets(raw_values: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw in raw_values:
        if "=" not in raw:
            raise KnowledgeError(f"Facet must use name=value: {raw!r}")
        name, value = (part.strip() for part in raw.split("=", 1))
        if not FACET_NAME_RE.fullmatch(name) or not value:
            raise KnowledgeError(f"Invalid facet query: {raw!r}")
        result.setdefault(name, [])
        if value not in result[name]:
            result[name].append(value)
    return result


# --------------------------------------------------------------------------
# Overview, index, and commands


def overview_project(project_root: Path, limit: int, all_tasks: bool) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_project_config(project_root)
    records, _ = discover_records(project_root, config)
    tasks, warnings = discover_tasks(project_root, config)
    read_first = []
    for raw in config["context"]["always_load"]:
        path = project_path(project_root, raw, "context.always_load")
        read_first.append({"ref": raw, "chars": text_chars(path) if path.is_file() else None})
    open_tasks = [task for task in tasks if all_tasks or task.status.casefold() not in CLOSED_TASK_STATUSES]
    current = [record for record in records if record.bucket == "knowledge"]
    return {
        "schema_version": 2,
        "project_root": str(project_root),
        "read_first": read_first,
        "facets": {name: definition["values"] for name, definition in config["facets"].items()},
        "tasks": {
            "listed": [{"id": task.identifier, "status": task.status, "title": task.title, "ref": task.ref} for task in open_tasks[:limit]],
            "omitted": max(0, len(open_tasks) - limit),
            "closed_hidden": 0 if all_tasks else len(tasks) - len(open_tasks),
            "warnings": warnings,
        },
        "knowledge": {
            "listed": [{"id": record.identifier, "title": record.title, "topics": record.topics, "ref": record.ref} for record in current[:limit]],
            "omitted": max(0, len(current) - limit),
            "history_records": sum(record.bucket == "history" for record in records),
            "inbox_candidates": sum(record.bucket == "inbox" for record in records),
        },
    }


def build_index_value(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    records, by_reference = discover_records(project_root, config, ("knowledge", "history"))
    validate_relationships(project_root, config, records, by_reference)
    return {
        "schema_version": 2,
        "project_sha256": hashlib.sha256((project_root / ".ai" / "project.yaml").read_bytes()).hexdigest(),
        "records": [asdict(record) for record in records],
    }


def write_index(project_root: Path, config: dict[str, Any]) -> Path:
    root = config["storage_paths"]["index"]
    root.mkdir(parents=True, exist_ok=True)
    target = root / "records.json"
    temporary = root / ".records.json.tmp"
    temporary.write_text(json.dumps(build_index_value(project_root, config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1))


def command_validate(args: argparse.Namespace) -> None:
    root = Path(args.project_root).expanduser().resolve()
    config = load_project_config(root)
    records, by_reference = discover_records(root, config)
    validate_relationships(root, config, records, by_reference)
    for ref in config["context"]["always_load"]:
        if not project_path(root, ref, "context.always_load").is_file():
            raise KnowledgeError(f"Always-loaded source is missing: {ref}")
    tasks, warnings = discover_tasks(root, config)
    for task in tasks:
        for link in task.links:
            try:
                resolve_reference(root, link, by_reference)
            except KnowledgeError as exc:
                warnings.append(f"Task {task.identifier} link {link!r}: {exc}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"valid: {root / '.ai' / 'project.yaml'} ({len(records)} records) tasks: {len(tasks)}")


def command_index(args: argparse.Namespace) -> None:
    root = Path(args.project_root).expanduser().resolve()
    print(write_index(root, load_project_config(root)))


def command_overview(args: argparse.Namespace) -> None:
    emit(overview_project(Path(args.project_root).expanduser(), args.limit, args.all_tasks))


def command_query(args: argparse.Namespace) -> None:
    emit(query_project(Path(args.project_root).expanduser(), args.query, args.facet, args.topic, args.path, args.task, args.include_history, args.search, args.semantic))


def command_search(args: argparse.Namespace) -> None:
    root = Path(args.project_root).expanduser().resolve()
    config = load_project_config(root)
    records, by_reference = discover_records(root, config)
    tasks, warnings = discover_tasks(root, config)
    requested = set(args.task)
    tasks = [task for task in tasks if task.identifier in requested]
    for missing in sorted(requested - {task.identifier for task in tasks}):
        warnings.append(f"Requested task not found: {missing}")
    terms = query_terms(args.query)
    include_history = args.include_history or config["context"]["deterministic"]["include_history"]
    selection = Selection(root, config, include_history, {task.ref for task in tasks})
    hits = lexical_search(root, config, terms, records, by_reference, tasks, include_history, args.limit)
    # Search returns bounded snippets, not a budgeted read list. Area rules still apply.
    hits = [hit for hit in hits if selection.allowed(hit["ref"], hit["reason"])]
    emit({"schema_version": 2, "terms": terms, "hits": hits, "excluded": selection.excluded,
          "unresolved": warnings + ([] if hits else ["No literal match"])})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate, summarize, search, and retrieve project knowledge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--project-root", default=".")
    validate.set_defaults(handler=command_validate)
    index = subparsers.add_parser("index")
    index.add_argument("--project-root", default=".")
    index.set_defaults(handler=command_index)
    overview = subparsers.add_parser("overview")
    overview.add_argument("--project-root", default=".")
    overview.add_argument("--limit", type=int, default=40)
    overview.add_argument("--all-tasks", action="store_true")
    overview.set_defaults(handler=command_overview)
    query = subparsers.add_parser("query")
    query.add_argument("--project-root", default=".")
    query.add_argument("--query", default="")
    query.add_argument("--facet", action="append", default=[])
    query.add_argument("--topic", action="append", default=[])
    query.add_argument("--path", action="append", default=[])
    query.add_argument("--task", action="append", default=[])
    query.add_argument("--include-history", action="store_true")
    query.add_argument("--search", action="store_true", help="also run the literal body search layer")
    query.add_argument("--semantic", action="store_true", help="also run the configured semantic command")
    query.set_defaults(handler=command_query)
    search = subparsers.add_parser("search")
    search.add_argument("--project-root", default=".")
    search.add_argument("--query", required=True)
    search.add_argument("--include-history", action="store_true")
    search.add_argument("--task", action="append", default=[])
    search.add_argument("--limit", type=int, default=8)
    search.set_defaults(handler=command_search)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except KnowledgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
