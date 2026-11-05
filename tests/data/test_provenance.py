from pathlib import Path

import pytest

from app.data import data_freeze_id, head_commit
from app.data.exceptions import FeaturesNotFoundError

COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def backup(tmp_path: Path) -> Path:
    features = tmp_path / "thesis_2026-10-30" / "features"
    features.mkdir(parents=True)
    (features / "features_revenue_usd_m_h1.parquet").write_bytes(b"one")
    (features / "features_revenue_usd_m_h2.parquet").write_bytes(b"two")
    return features.parent


def test_a_freeze_is_named_by_its_directory_and_stable(backup: Path) -> None:
    freeze = data_freeze_id(backup)

    assert freeze.startswith("thesis_2026-10-30-")
    assert data_freeze_id(backup) == freeze


def test_changing_a_feature_file_changes_the_freeze(backup: Path) -> None:
    before = data_freeze_id(backup)

    (backup / "features" / "features_revenue_usd_m_h2.parquet").write_bytes(b"2")

    assert data_freeze_id(backup) != before


def test_a_backup_without_feature_files_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FeaturesNotFoundError, match="No feature files"):
        data_freeze_id(tmp_path)


@pytest.mark.parametrize(
    ("files", "kind"),
    [
        ({"HEAD": "ref: refs/heads/main\n", "refs/heads/main": f"{COMMIT}\n"}, "loose"),
        (
            {
                "HEAD": "ref: refs/heads/main\n",
                "packed-refs": f"# pack-refs\n{COMMIT} refs/heads/main\n",
            },
            "packed",
        ),
        ({"HEAD": f"{COMMIT}\n"}, "detached"),
    ],
)
def test_head_commit_reads_every_kind_of_ref(
    tmp_path: Path, files: dict[str, str], kind: str
) -> None:
    for name, content in files.items():
        path = tmp_path / ".git" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assert head_commit(tmp_path) == COMMIT, kind
