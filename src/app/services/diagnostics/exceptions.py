from dataclasses import dataclass


class DiagnosticsError(Exception):
    """Base error for series and panel diagnostics."""


@dataclass
class TooFewCompaniesError(DiagnosticsError):
    """Raised when fewer fully diagnosed companies exist than regimes requested."""

    companies: int
    regimes: int

    def __str__(self) -> str:
        return (
            f"{self.companies} fully diagnosed companies cannot fill "
            f"{self.regimes} regimes"
        )
