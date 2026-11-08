---
name: project-knowledge
description: Load and maintain project goals, current tasks and progress, prior decisions, and durable knowledge in a repository that contains `.ai/project.yaml`. Use at the start of project-specific work in a fresh session, before project-specific explanation, design, implementation, debugging, review, or documentation changes, and after durable project facts change. Do not use for generic questions unrelated to the current project.
---

# Project Knowledge

Projects keep their knowledge as plain files: Markdown/YAML records with stable IDs, explicit links, and separate `knowledge/` (current truth), `history/` (prior states and rationale), and `inbox/` (unreviewed candidates). The helper picks a small, cited set of files to read. Live reads avoid a stale local index; stored facts can still be outdated. Check `last_verified` and the underlying evidence when it matters. The helper does not write during retrieval; an optional semantic command has its own side effects.

`<skill-dir>/scripts/knowledge.py` needs only Python 3.9+ and has no dependencies. Read [references/knowledge-contract.md](references/knowledge-contract.md) before you create or edit records or `.ai/project.yaml`.

## 1. Cold start: orient once per session

Find the project root that contains `.ai/project.yaml`, then run:

```sh
python3 <skill-dir>/scripts/knowledge.py overview --project-root <root>
```

The output lists the `read_first` files (goals and policy), the declared facet values, the **open tasks** (ID, status, title, file), and a catalog of current knowledge records (ID, title, topics). Read the `read_first` files. Use the task list and catalog to choose what to fetch next. Do not read the whole `.ai/` tree.

## 2. Retrieve for a request

```sh
python3 <skill-dir>/scripts/knowledge.py query --project-root <root> \
  --query "<request wording>" \
  [--task <TASK-ID>] [--topic <topic>] [--path <project-relative path>] \
  [--facet <name=value>] [--include-history] [--search] [--semantic]
```

- Pass only filters the evidence supports. Use topics from the catalog, facet values from the overview, and paths the request actually touches.
- `--task` returns the task file itself (status and progress) plus the knowledge listed under its `## Related knowledge` section.
- Read the files listed under `layers`. Records marked `"read": false` are metadata-only: their `summary` is included inline. Look for their source files and check `budget.omitted`, `excluded`, and `unresolved` before assuming the supporting content was returned.
- Add `--include-history` for questions about chronology, why something changed, or what used to be true. History explains past decisions. It is not current truth.
- `unresolved` lists anything that could change the answer: no match, sources omitted for budget, history hidden, a task not found, or a semantic retrieval failure. Either state the limitation or refine the query. Do not fall back to loading everything.

Admission prioritizes policy, requested tasks and their links, then ranked metadata matches; each primary record's sources follow it before other relationships. Results are grouped under `always_loaded`, `tasks`, `deterministic`, `explicit_relationships`, `lexical`, and `semantic`. Lexical body search runs only when the structured layers find nothing, or when you pass `--search`. Semantic runs only if configured and earlier layers find nothing, or with `--semantic`. Inbox files are never returned, history only with opt-in, and budgets count Unicode characters (not tokens).

For a quick term lookup, such as a config key or non-English wording, use `knowledge.py search --project-root <root> --query "<text>"` (add `--task <ID>` to search a task). It returns bounded snippets and line numbers, not a budgeted list of full files to read. Use `query --search` for that. Search matches terms, not exact phrases; use a scoped `rg -n -F` lookup when exact punctuation matters.

## 3. Store durable knowledge

After behavior, architecture, constraints, interfaces, or decisions change, ask: would a future session make a wrong decision, or repeat substantial discovery, without this? If so:

- Update or add a focused record under `.ai/knowledge/`. Point `source` at the canonical human document instead of copying it.
- When a fact or decision is superseded, move the old record to `.ai/history/` and link the two with `supersedes` / `superseded_by`. Keep the rationale in the historical record.
- Put uncertain findings in `.ai/inbox/` with a `CAND-` ID. Current and historical records must not link to inbox candidates.
- Task status and progress belong only in the task files (under `storage.tasks`). Update them there, using the project's task workflow if one exists. Do not copy them into knowledge records.
- Human-facing README and `docs/` pages state only currently valid facts, with no session narrative.
- Set `last_verified` only after you have checked the fact against the code or the owner. Do not store transient debugging output or obvious code facts.

Then run `knowledge.py validate --project-root <root>` and fix any errors before you finish.
