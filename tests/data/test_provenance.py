import importlib
import os
import time
from pathlib import Path

import pytest

from app.data import data_freeze_id, head_commit, modules_edited_since
from app.data.exceptions import FeaturesNotFoundError, PanelNotFoundError

COMMIT = "0123456789abcdef0123456789abcdef01234567"
STALE_PACKAGE = "stale_kernel_probe"


@pytest.fixture
def backup(tmp_path: Path) -> Path:
    features = tmp_path / "thesis_2026-10-30" / "features"
    features.mkdir(parents=True)
    (features / "features_revenue_usd_m_h1.parquet").write_bytes(b"one")
    (features / "features_revenue_usd_m_h2.parquet").write_bytes(b"two")
    processed = features.parent / "processed"
    processed.mkdir()
    (processed / "panel_long.parquet").write_bytes(b"panel")
    (processed / "macro_q.parquet").write_bytes(b"macro")
    return features.parent


def test_a_freeze_is_named_by_its_directory_and_stable(backup: Path) -> None:
    freeze = data_freeze_id(backup)

    assert freeze.startswith("thesis_2026-10-30-")
    assert data_freeze_id(backup) == freeze


@pytest.mark.parametrize(
    "input_path",
    [
        "features/features_revenue_usd_m_h2.parquet",
        "processed/panel_long.parquet",
        "processed/macro_q.parquet",
    ],
)
def test_changing_an_evaluation_input_changes_the_freeze(
    backup: Path, input_path: str
) -> None:
    before = data_freeze_id(backup)

    (backup / input_path).write_bytes(b"revised")

    assert data_freeze_id(backup) != before


def test_renaming_a_feature_file_changes_the_freeze(backup: Path) -> None:
    before = data_freeze_id(backup)
    feature = backup / "features" / "features_revenue_usd_m_h2.parquet"
    feature.rename(feature.with_name("features_revenue_usd_m_h3.parquet"))

    assert data_freeze_id(backup) != before


def test_per_company_panel_files_do_not_change_the_freeze(backup: Path) -> None:
    before = data_freeze_id(backup)
    (backup / "processed" / "AAPL_panel.parquet").write_bytes(b"per-company")

    assert data_freeze_id(backup) == before


@pytest.mark.parametrize("filename", ["panel_long.parquet", "macro_q.parquet"])
def test_a_backup_without_a_consolidated_file_is_refused(
    backup: Path, filename: str
) -> None:
    (backup / "processed" / filename).unlink()

    with pytest.raises(PanelNotFoundError, match=filename.removesuffix(".parquet")):
        data_freeze_id(backup)


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


def test_a_module_edited_after_it_was_loaded_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / STALE_PACKAGE
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "baselines.py").write_text("DRIFT = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.import_module(f"{STALE_PACKAGE}.baselines")
    loaded_at = time.time()

    assert modules_edited_since(loaded_at, package=STALE_PACKAGE) == []

    edited_later = loaded_at + 60
    os.utime(package / "baselines.py", (edited_later, edited_later))

    assert modules_edited_since(loaded_at, package=STALE_PACKAGE) == [
        f"{STALE_PACKAGE}.baselines"
    ]
