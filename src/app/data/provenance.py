import hashlib
from pathlib import Path

from app.data.exceptions import FeaturesNotFoundError


def data_freeze_id(backup: Path) -> str:
    """Name a data freeze by its directory and the bytes of its feature files.

    Returns:
        ``<directory name>-<first 12 hex digits of a SHA-256>``.

    Raises:
        FeaturesNotFoundError: The backup holds no feature files.
    """
    features = backup / "features"
    feature_files = sorted(features.glob("*.parquet"))
    if not feature_files:
        message = f"No feature files under {features}"
        raise FeaturesNotFoundError(message)
    digest = hashlib.sha256()
    for path in feature_files:
        digest.update(path.read_bytes())
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
