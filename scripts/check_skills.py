#!/usr/bin/env python3
"""Check SKILL.md files for claims that are not true of this repo.

Skills drift silently: an example gets copied from another project, a symbol
gets renamed, a file moves. Nothing fails, and the agent keeps reading the
stale instruction. This is the check that fails.

Run: uv run poe check-skills
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT_SKILLS = REPO / ".claude" / "skills"
GLOBAL_SKILLS = Path.home() / ".claude" / "skills"

# Only the skills this repo maintains are checked. Third-party skills in the
# global tree are someone else's to keep correct, and several are legitimately
# about TypeScript — a ```ts fence there is content, not contamination.
OWNED = {
    "analyzing-time-series",
    "cfo-copilot-structure",
    "code-smells",
    "code-structure",
    "ddd-python",
    "dependency-injection-python",
    "design-patterns",
    "find-skills",
    "optimal-scaffold",
    "pep8-check",
    "pydantic",
    "pytest-testing",
    "python-backend",
    "python-oop",
    "refactoring-techniques",
    "solid-principles",
    "stop-using-none",
}

# Markers from other codebases. A skill naming these is describing someone
# else's project, which is worse than being vague: the agent trusts it.
FOREIGN = re.compile(
    r"classiflow|decreto|ollama|phi4-mini|wine reviews|OodEvidence"
    r"|ConfidenceTier|OOD_COSINE|\.claude/learnings\.md|```(ts|typescript)",
    re.IGNORECASE,
)

# Repo paths cited in backticks, e.g. `src/app/settings.py`.
PATH_REF = re.compile(r"`((?:src|tests|config)/[\w./-]+)`")

# Imports from the app package, e.g. `from app.settings import Settings`.
APP_IMPORT = re.compile(
    r"^\s*from\s+(app(?:\.[\w.]+)?)\s+import\s+([\w, ]+)", re.MULTILINE
)


def defined_names(module_file: Path) -> set[str]:
    """Top-level names a module defines or re-exports.

    Returns:
        The set of names bound at module level, empty if the file is
        unreadable or does not parse.
    """
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.ImportFrom | ast.Import):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return names


def resolve_module(dotted: str) -> Path | None:
    """Locate the file backing a dotted module path.

    Returns:
        The module file, or None when no such module exists under src/.
    """
    base = REPO / "src" / Path(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def check_file(skill: Path) -> list[str]:
    findings: list[str] = []
    text = skill.read_text(encoding="utf-8")

    for n, line in enumerate(text.splitlines(), 1):
        if match := FOREIGN.search(line):
            findings.append(f"{skill}:{n}: foreign-marker: {match.group(0)!r}")

    for match in PATH_REF.finditer(text):
        ref = match.group(1)
        if not (REPO / ref).exists():
            n = text[: match.start()].count("\n") + 1
            findings.append(f"{skill}:{n}: dead-path: {ref} does not exist")

    for match in APP_IMPORT.finditer(text):
        module, imported = match.group(1), match.group(2)
        n = text[: match.start()].count("\n") + 1
        target = resolve_module(module)
        if target is None:
            findings.append(f"{skill}:{n}: dead-import: no module {module}")
            continue
        available = defined_names(target)
        findings.extend(
            f"{skill}:{n}: missing-symbol: {name} not in {module}"
            for name in (s.strip() for s in imported.split(","))
            if name and name not in available
        )
    return findings


def check_collisions() -> list[str]:
    """Compare each skill that exists in both trees.

    The global copy shadows the project one, so a divergent pair means edits
    that silently never load.

    Returns:
        One finding per pair that differs, ignoring line-ending style.
    """
    if not GLOBAL_SKILLS.is_dir():
        return []

    findings: list[str] = []
    for project in sorted(PROJECT_SKILLS.glob("*/SKILL.md")):
        shadow = GLOBAL_SKILLS / project.parent.name / "SKILL.md"
        if not shadow.is_file():
            continue
        a = project.read_text(encoding="utf-8").replace("\r\n", "\n")
        b = shadow.read_text(encoding="utf-8").replace("\r\n", "\n")
        if a != b:
            findings.append(
                f"{project}:1: shadowed-drift: differs from {shadow} "
                "(the global copy is the one that loads)"
            )
    return findings


def demo() -> None:
    """Self-check: the checks must actually fire."""
    assert FOREIGN.search("built on classiflow.ingesta"), "foreign marker missed"
    assert FOREIGN.search("```ts\nexport async function"), "ts fence missed"
    assert not FOREIGN.search("a normal sentence about services")
    assert PATH_REF.findall("see `src/app/settings.py` now") == ["src/app/settings.py"]
    assert APP_IMPORT.findall("from app.settings import Settings") == [
        ("app.settings", "Settings")
    ]
    assert resolve_module("app.settings") is not None, "real module not resolved"
    assert resolve_module("app.nope_not_here") is None, "fake module resolved"
    assert "Settings" in defined_names(REPO / "src" / "app" / "settings.py")


def main() -> int:
    demo()

    roots = [PROJECT_SKILLS]
    if GLOBAL_SKILLS.is_dir():
        roots.append(GLOBAL_SKILLS)
    else:
        print(f"note: {GLOBAL_SKILLS} not found, checking project skills only")

    skills = [
        skill
        for root in roots
        for skill in sorted(root.glob("*/SKILL.md"))
        if skill.parent.name in OWNED
    ]

    findings: list[str] = []
    for skill in skills:
        findings.extend(check_file(skill))
    findings.extend(check_collisions())

    for finding in findings:
        print(finding)

    n_skills = len(skills)
    if findings:
        print(f"\n{len(findings)} finding(s) across {n_skills} skills")
        return 1
    print(f"{n_skills} skills checked, no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
