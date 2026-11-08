# Agent Workbench
My personal toolkit for building, customizing, and orchestrating AI agents across Codex, Claude Code, and beyond.

## Install skills

With Python 3 installed, run [the installer](scripts/install-skills.py) from the repository root:

```sh
python3 scripts/install-skills.py
```

The installer links each folder under `skills/` that contains a `SKILL.md` into
`~/.agents/skills/` for Codex and `~/.claude/skills/` for Claude Code. Both tools
read the skill files from this checkout, so edits take effect through the same
links.

Run the installer again whenever you add a skill. It recognizes links that
already point to this checkout and skips and reports other entries with the
same name, including broken symlinks.
