#!/usr/bin/env python3
"""Copy .claude/skills to the mirrors that git cannot carry.

`.claude/skills` is the source of truth and travels with the repo, as does
its `.cursor/skills` mirror. `~/.claude/skills` does not — it is per-machine,
and a personal skill there SHADOWS the project copy silently, so a stale one
means your committed edits never load.

Run this after cloning on a new machine, and after editing .claude/skills.

    uv run poe sync-skills          # show what would change
    uv run poe sync-skills -- --write
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / ".claude" / "skills"
TARGETS = (REPO / ".cursor" / "skills", Path.home() / ".claude" / "skills")

SKIP = {"AUDIT.md"}

# Skills that describe THIS repo. They stay project-local: installed globally
# they would fire in unrelated repos and confidently hand out CFO_Copilot
# paths. (optimal-scaffold was removed from the global tree for exactly that.)
PROJECT_ONLY = {
    "analyzing-time-series",
    "cfo-copilot-structure",
    "find-skills",
    "optimal-scaffold",
}


def skill_dirs() -> list[Path]:
    """Every skill directory in the source tree.

    Returns:
        Directories holding a SKILL.md, sorted by name.
    """
    return sorted(p.parent for p in SOURCE.glob("*/SKILL.md"))


def same(a: Path, b: Path) -> bool:
    """Compare two files ignoring line-ending style.

    Returns:
        True when both exist and their normalized text matches.
    """
    if not (a.is_file() and b.is_file()):
        return False
    return a.read_text(encoding="utf-8").replace("\r\n", "\n") == b.read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n")


def sync_one(source: Path, target: Path, *, write: bool) -> list[str]:
    """Mirror one skill directory into a target tree.

    Returns:
        A line per file that differs, describing what would change.
    """
    changes: list[str] = []
    for src in sorted(source.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts or src.name in SKIP:
            continue
        dst = target / src.relative_to(source.parent)
        if same(src, dst):
            continue
        changes.append(f"{'updated' if dst.exists() else 'added'}: {dst}")
        if write:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="apply changes (default: dry run)"
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"error: {SOURCE} not found")
        return 1

    changes: list[str] = []
    for target in TARGETS:
        is_global = target == Path.home() / ".claude" / "skills"
        for skill in skill_dirs():
            if is_global and skill.name in PROJECT_ONLY:
                continue
            changes.extend(sync_one(skill, target, write=args.write))

    for change in changes:
        print(change)

    if not changes:
        print("all mirrors already in sync")
        return 0

    if args.write:
        print(f"\n{len(changes)} file(s) synced")
        return 0

    print(f"\n{len(changes)} file(s) would change — re-run with --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
