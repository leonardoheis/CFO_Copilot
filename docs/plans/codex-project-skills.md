# Copy project skills for Codex

1. Copy the tracked skill packages from `.claude/skills/` to
   `.agents/skills/` with their scripts and references.
2. Point the Codex project guides at `AGENTS.md` and make the time-series
   commands runnable from the repository root.
3. Validate all skill entrypoints, check links and scripts, and run
   `uv run poe check`.
