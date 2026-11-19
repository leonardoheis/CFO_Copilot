import hashlib
import sys
import time
from pathlib import Path
from typing import Final

from app.data.exceptions import FeaturesNotFoundError, PanelNotFoundError
from app.data.panel_store import PanelStore

# When this process loaded the code: a notebook kernel keeps it until restarted.
CODE_LOADED_AT: Final = time.time()


def data_freeze_id(backup: Path) -> str:
    """Identify a freeze by the paths and contents of its evaluation inputs.

    Returns:
        ``<directory name>-<first 12 hex digits of a SHA-256>``.

    Raises:
        FeaturesNotFoundError: The backup holds no feature files.
        PanelNotFoundError: A consolidated panel file is missing.
    """
    features = backup / "features"
    feature_files = sorted(
        path for path in features.glob("*.parquet") if path.is_file()
    )
    if not feature_files:
        message = f"No feature files under {features}"
        raise FeaturesNotFoundError(message)
    panel_store = PanelStore(backup / "processed")
    panel_files = (panel_store.panel_long_path, panel_store.macro_q_path)
    absent = ", ".join(str(path) for path in panel_files if not path.is_file())
    if absent:
        message = f"Consolidated panel files missing: {absent}"
        raise PanelNotFoundError(message)

    digest = hashlib.sha256()
    for path in (*panel_files, *feature_files):
        digest.update(path.relative_to(backup).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"{backup.name}-{digest.hexdigest()[:12]}"


def head_commit(repository: Path) -> str:
    """Read the commit checked out in ``repository`` without running git.

    Returns:
        The full commit hash.
    """
    # ponytail: plain .git directories only; a worktree's .git file is not read.
    git = repository / ".git"
    head = (git / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    ref = head.removeprefix("ref: ")
    loose = git / ref
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    packed = (git / "packed-refs").read_text(encoding="utf-8").splitlines()
    return next(line.split()[0] for line in packed if line.endswith(f" {ref}"))


def modules_edited_since(moment: float, package: str = "app") -> list[str]:
    """Name the loaded modules of ``package`` whose file changed after ``moment``.

    Returns:
        Their names, sorted; empty when the code in memory is the code on disk.
    """
    edited: list[str] = []
    for name, module in sys.modules.copy().items():
        file = getattr(module, "__file__", None)
        in_package = name == package or name.startswith(f"{package}.")
        if in_package and file and Path(file).stat().st_mtime > moment:
            edited.append(name)
    return sorted(edited)
