"""Stage-by-stage console output for long ingestion runs."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import click

LABEL_WIDTH = 24
DETAIL_WIDTH = 26


@dataclass
class Stage:
    """One named step of a run, holding the note printed beside it."""

    note: str = field(default="")

    def detail(self, note: str) -> None:
        self.note = note


@dataclass(frozen=True)
class Progress:
    ticker: str
    enabled: bool = True

    @contextmanager
    def stage(self, label: str) -> Iterator[Stage]:
        """Time a stage and print it when it ends.

        Yields:
            The stage, so the caller can attach a detail note.
        """
        current = Stage()
        started = time.monotonic()
        try:
            yield current
        finally:
            if self.enabled:
                elapsed = time.monotonic() - started
                click.echo(
                    f"{self.ticker:6s} {label:<{LABEL_WIDTH}}"
                    f"{current.note:<{DETAIL_WIDTH}}{elapsed:6.1f}s",
                )
