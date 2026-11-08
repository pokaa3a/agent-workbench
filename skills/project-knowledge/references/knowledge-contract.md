# Project knowledge contract

Read this before you edit `.ai/project.yaml`, a knowledge, history, or inbox record, or the task-link section of a task file. JSON Schemas: [project.schema.json](project.schema.json) and [knowledge-metadata.schema.json](knowledge-metadata.schema.json) describe the fields for editors. `knowledge.py validate` uses its own checks, not a JSON Schema engine: supported keys and types, nonblank strings, declared facets, date syntax, unique record/task IDs, storage boundaries, existing policy files and record links, and the inbox-link prohibition. Task parse/link problems are warnings. Validation does not verify factual truth or execute a semantic backend.

## Storage areas

```text
tasks/          task files: goals, status, progress (authoritative for tasks)
.ai/knowledge/  current durable truth
.ai/history/    prior states, superseded decisions, rationale, chronology
.ai/inbox/      unreviewed candidates (validated, never retrieved)
.ai/index/      optional derived JSON written by `index`; retrieval never reads it
```

Paths are configurable under `storage`, must be project-relative, and must not overlap. Areas are matched by resolved path, so an alias such as `./.ai/../.ai/inbox/x.md` still counts as inbox.

## Project contract (`.ai/project.yaml`)

```yaml
version: 1
storage:            # optional; defaults shown
  tasks: "tasks"
  knowledge: ".ai/knowledge"
  history: ".ai/history"
  inbox: ".ai/inbox"
  index: ".ai/index"
facets: {}          # name -> {description, values}; grow only for real concepts
context:
  always_load: ["README.md", ".ai/project.yaml"]   # keep small: goals + policy
  deterministic:
    include_history: false
    max_relationship_depth: 2
  semantic:
    enabled: false
    command: []     # argv; reads a JSON query on stdin, prints [{ref, reason, score?}]
  budget:
    max_sources: 12     # files to read; inline metadata records do not count
    max_chars: 40000    # Unicode characters, not bytes or tokens
```

`always_load` must contain only current knowledge or ordinary project files: history, inbox, task, and index paths (including aliases) are rejected. Valid policy files and requested task files are mandatory; if they exceed either budget, `unresolved` says so. Other sources are admitted in priority order until a limit is reached. Each omitted source is listed in `budget.omitted`. Character cost covers selected file contents and inline titles/summaries, not JSON envelope, reasons, or snippets; it is not a total response or token cap. `overview` and `search` return catalogs/snippets bounded by `--limit`, not full-file read budgets.

## Records

A record is either a Markdown file with YAML frontmatter or a metadata-only `.yaml` file.

```yaml
---
id: KNOW-authentication          # required, stable, unique across all areas
title: Authentication behavior    # non-empty if present
summary: Current JWT constraints and entry points.
facets:
  domain: [identity]             # facet names and values must be declared
applies_to: ["src/auth/**"]      # project-relative globs
topics: [authentication, jwt]
source: ["docs/security/authentication.md"]   # canonical documents
related: [KNOW-api-security]
supersedes: [HIST-cookie-sessions]
last_verified: "2026-08-25"      # date the fact was last checked, not edited
attributes: {}                   # project-specific, not used for retrieval
---
Body: the durable fact, in a few focused paragraphs.
```

- Relationship targets are record IDs or project-relative file paths, and they must exist.
- A record with an empty body that has a `source` is treated as a metadata-only pointer. Retrieval returns its summary inline and reads the source.
- Inbox candidates use `CAND-` IDs and keep proposal state, confidence, and rationale under `attributes`.
- Facet filtering: a record that declares a facet must match the requested value. A record that does not declare that facet is not excluded.

## Task files

A task file is a Markdown file under `storage.tasks` with frontmatter that includes `id` and usually `status` (and `title`; otherwise the first `# ` heading is used). The statuses `done`, `closed`, `completed`, `cancelled`, `archived`, and `abandoned` are hidden from `overview` unless you pass `--all-tasks`. Knowledge links go in a section like this:

```markdown
## Related knowledge
- KNOW-authentication
- [Auth design](../docs/auth.md)
```

The headings `Related knowledge`, `Knowledge links`, and the legacy `相關知識` are recognized. A path link is resolved relative to the task file first, then relative to the project root. Task IDs must be unique; ambiguity is an error rather than silently choosing one file.

## Retrieval rules

1. Mandatory: `always_load`, then any `--task` files.
2. Primary: links from the requested tasks, then records scored by facet, topic, path, and request-term matches. Terms match at word starts: `token` matches `tokens`, but `id` does not match `grid`. CJK text matches by substring, and longer CJK runs are split into overlapping two-character pieces.
3. Each admitted record is followed immediately by its `source` files. The remaining links are then expanded breadth-first, only from admitted records, up to `max_relationship_depth`.
4. Lexical: a literal search of record metadata values and bodies, their source documents, and requested task files. It runs when the structured layers find nothing, or with `--search`.
5. Semantic: an external command. It runs when it is enabled and nothing else matched, or with `--semantic`. Its results and their direct source documents follow the same area and budget rules. The command can have side effects; configure only a backend you intend to execute.

Every route enforces the same area rules: inbox is never returned, history only with `--include-history` or `include_history: true`, task files only when requested, and the index never. Refused links are listed in `excluded`.

`search` includes task content only with `--task`. It returns up to `--limit` ranked hits with at most three 160-character snippets per hit; line 0 denotes synthesized metadata. Files over 400,000 characters and unsupported file extensions are skipped. A partial structured match suppresses automatic lexical fallback: use `--search` if it did not answer the question. Unlinked documents are outside the lexical corpus; use targeted project navigation when needed.

## Parser subset

The files are parsed by a built-in YAML subset parser (`scripts/yaml_subset.py`). It supports two-space-indented mappings, scalar block lists, inline `[...]` and `{...}`, quoted and plain scalars, numbers, booleans, null, and JSON documents. It rejects tabs, anchors, aliases, tags, block scalars (`|`, `>`), multi-line plain scalars, duplicate keys, and list-of-map shorthand (`- key: value`; use `- {key: value}` instead). A `#` starts a comment only after whitespace and outside quotes.

## When to add more retrieval

The default stack is metadata navigation, explicit links, and a literal fallback. Configure a semantic command only when you have recorded cases where useful records were missed because the wording differed (paraphrase or another language) after overview, query, and search were all tried, and when a pilot on those cases shows better recall at similar context size, with an index refresh you can automate. Index freshness becomes your responsibility. The query reports semantic failures in `unresolved` but cannot detect a stale external index.
