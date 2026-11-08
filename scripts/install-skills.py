#!/usr/bin/env python3
"""Link the repository's skills into the Codex and Claude Code user directories."""

import sys
from pathlib import Path


def main():
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    skills = sorted(path for path in skills_dir.iterdir() if (path / "SKILL.md").is_file())
    if not skills:
        print(f"No skills found in {skills_dir}.")
        return 0

    home = Path.home()
    destinations = (home / ".agents" / "skills", home / ".claude" / "skills")
    failed = False
    for directory in destinations:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            print(f"Could not prepare {directory}: {error}", file=sys.stderr)
            failed = True
            continue

        for skill in skills:
            link = directory / skill.name
            try:
                link.symlink_to(skill, target_is_directory=True)
                print(f"Linked {link} -> {skill}")
            except FileExistsError:
                try:
                    already_linked = link.is_symlink() and link.samefile(skill)
                except OSError:
                    already_linked = False
                if already_linked:
                    print(f"Already linked {link}")
                else:
                    print(f"Skipped existing entry {link}", file=sys.stderr)
            except OSError as error:
                print(f"Could not link {link}: {error}", file=sys.stderr)
                failed = True

    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
