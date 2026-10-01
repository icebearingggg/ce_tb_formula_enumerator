from __future__ import annotations

import csv
import json
from argparse import Namespace
from pathlib import Path

import pytest

from ce_tb_enumerator import output as output_module
from ce_tb_enumerator.cli import main, run
from ce_tb_enumerator.errors import (
    OutputExistsError,
    OutputRecoveryError,
    OutputTransactionError,
)
from ce_tb_enumerator.output import OUTPUT_NAMES, RECOVERY_DIRECTORY_NAME


def _run(config: Path, output_dir: Path, *, overwrite: bool = False):
    return run(Namespace(config=config, output_dir=output_dir, overwrite=overwrite))


def _snapshot(output_dir: Path) -> dict[str, bytes | None]:
    return {
        name: (output_dir / name).read_bytes() if (output_dir / name).is_file() else None
        for name in OUTPUT_NAMES
    }


def _fail_second_publication(monkeypatch, *, fail_compositions_restore: bool = False):
    real_replace = output_module._replace_output
    publication_count = 0

    def injected_replace(source: Path, target: Path) -> None:
        nonlocal publication_count
        if source.parent.name.startswith(output_module.STAGING_DIRECTORY_PREFIX):
            publication_count += 1
            if publication_count == 2:
                raise OSError("injected publication failure")
        if (
            fail_compositions_restore
            and target.name == "compositions.csv"
            and ".restore-" in source.name
        ):
            raise OSError("injected rollback failure")
        real_replace(source, target)

    monkeypatch.setattr(output_module, "_replace_output", injected_replace)


def _fail_recovery_cleanup_after_removing_one_backup(monkeypatch):
    real_rmtree = output_module.shutil.rmtree

    def injected_rmtree(path, *args, **kwargs):
        path = Path(path)
        if path.name == RECOVERY_DIRECTORY_NAME:
            (path / "compositions.csv.backup").unlink(missing_ok=True)
            raise OSError("injected recovery cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(output_module.shutil, "rmtree", injected_rmtree)


def _core_bytes(output_dir: Path) -> tuple[bytes, bytes, bytes]:
    return tuple(
        (output_dir / name).read_bytes()
        for name in ("compositions.csv", "charge_hypotheses.jsonl", "formulas.txt")
    )


def test_staging_failure_leaves_existing_outputs_unchanged(make_config, tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    _run(make_config(m_pool={"Fe": [2, 3]}), output_dir)
    before = _snapshot(output_dir)
    new_config = make_config(m_pool={"Ca": [2]})
    real_write = output_module._write_text_file
    calls = 0

    def injected_write(path, writer, newline=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        real_write(path, writer, newline)

    monkeypatch.setattr(output_module, "_write_text_file", injected_write)
    with pytest.raises(OSError, match="injected staging failure"):
        _run(new_config, output_dir, overwrite=True)
    assert _snapshot(output_dir) == before
    assert not (output_dir / RECOVERY_DIRECTORY_NAME).exists()


def test_mid_publication_failure_rolls_back_all_outputs(make_config, tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    _run(make_config(m_pool={"Fe": [2, 3]}), output_dir)
    before = _snapshot(output_dir)
    _fail_second_publication(monkeypatch)

    with pytest.raises(OutputTransactionError, match="all named outputs were restored"):
        _run(make_config(m_pool={"Ca": [2]}), output_dir, overwrite=True)
    assert _snapshot(output_dir) == before
    assert not (output_dir / RECOVERY_DIRECTORY_NAME).exists()


def test_failed_first_publication_leaves_no_partial_outputs(make_config, tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    _fail_second_publication(monkeypatch)

    with pytest.raises(OutputTransactionError, match="all named outputs were restored"):
        _run(make_config(m_pool={"Ca": [2]}), output_dir)
    assert _snapshot(output_dir) == {name: None for name in OUTPUT_NAMES}


def test_failed_publication_restores_partial_original_state(make_config, tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    _run(make_config(m_pool={"Fe": [2, 3]}), output_dir)
    (output_dir / "charge_hypotheses.jsonl").unlink()
    (output_dir / "run_summary.json").unlink()
    before = _snapshot(output_dir)
    _fail_second_publication(monkeypatch)

    with pytest.raises(OutputTransactionError, match="all named outputs were restored"):
        _run(make_config(m_pool={"Ca": [2]}), output_dir, overwrite=True)
    assert _snapshot(output_dir) == before


def test_rollback_failure_preserves_recovery_material_and_blocks_writes(
    make_config, tmp_path, monkeypatch
):
    output_dir = tmp_path / "outputs"
    old_config = make_config(m_pool={"Fe": [2, 3]})
    _run(old_config, output_dir)
    _fail_second_publication(monkeypatch, fail_compositions_restore=True)

    with pytest.raises(OutputRecoveryError, match="recovery material") as caught:
        _run(make_config(m_pool={"Ca": [2]}), output_dir, overwrite=True)
    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    assert str(recovery_dir) in str(caught.value)
    assert (recovery_dir / "manifest.json").is_file()
    assert (recovery_dir / "RECOVERY_REQUIRED.txt").is_file()
    assert (recovery_dir / "compositions.csv.backup").is_file()
    manifest = json.loads((recovery_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "recovery_failed"
    assert manifest["recovery_errors"]

    monkeypatch.undo()
    with pytest.raises(OutputRecoveryError, match="unfinished output recovery state"):
        _run(old_config, output_dir, overwrite=True)


def test_published_cleanup_failure_keeps_complete_new_outputs_and_accurate_guidance(
    make_config, tmp_path, monkeypatch
):
    output_dir = tmp_path / "outputs"
    reference_dir = tmp_path / "new-reference"
    old_config = make_config(m_pool={"Fe": [2, 3]})
    new_config = make_config(m_pool={"Ca": [2]})
    _run(old_config, output_dir)
    reference_summary = _run(new_config, reference_dir)
    _fail_recovery_cleanup_after_removing_one_backup(monkeypatch)

    with pytest.raises(OutputRecoveryError, match="all new outputs were published successfully"):
        _run(new_config, output_dir, overwrite=True)

    assert _core_bytes(output_dir) == _core_bytes(reference_dir)
    summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["results"] == reference_summary["results"]
    assert summary["effective_config"]["elements"]["additional_element_pool"] == {"Ca": [2]}

    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    manifest = json.loads((recovery_dir / "manifest.json").read_text(encoding="utf-8"))
    report = (recovery_dir / "RECOVERY_REQUIRED.txt").read_text(encoding="utf-8")
    assert manifest["status"] == "published_cleanup_failed"
    assert "cleanup_error" in manifest
    assert not (recovery_dir / "compositions.csv.backup").exists()
    assert (recovery_dir / "charge_hypotheses.jsonl.backup").is_file()
    assert "All new outputs were published successfully" in report
    assert "Do not restore old backups" in report
    assert "rollback was incomplete" not in report

    monkeypatch.undo()
    with pytest.raises(OutputRecoveryError, match="unfinished output recovery state"):
        _run(new_config, output_dir, overwrite=True)


def test_rolled_back_cleanup_failure_reports_restored_originals(
    make_config, tmp_path, monkeypatch
):
    output_dir = tmp_path / "outputs"
    old_config = make_config(m_pool={"Fe": [2, 3]})
    new_config = make_config(m_pool={"Ca": [2]})
    _run(old_config, output_dir)
    before = _snapshot(output_dir)
    _fail_second_publication(monkeypatch)
    _fail_recovery_cleanup_after_removing_one_backup(monkeypatch)

    with pytest.raises(OutputRecoveryError, match="original outputs were restored successfully"):
        _run(new_config, output_dir, overwrite=True)

    assert _snapshot(output_dir) == before
    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    manifest = json.loads((recovery_dir / "manifest.json").read_text(encoding="utf-8"))
    report = (recovery_dir / "RECOVERY_REQUIRED.txt").read_text(encoding="utf-8")
    assert manifest["status"] == "rolled_back_cleanup_failed"
    assert "publish_error" in manifest
    assert "cleanup_error" in manifest
    assert "automatic rollback completed" in report
    assert "Do not restore them again" in report
    assert "rollback was incomplete" not in report

    monkeypatch.undo()
    with pytest.raises(OutputRecoveryError, match="unfinished output recovery state"):
        _run(old_config, output_dir, overwrite=True)


def test_successful_overwrite_publishes_one_complete_new_run_and_preserves_unrelated_file(
    make_config, tmp_path
):
    output_dir = tmp_path / "outputs"
    old_config = make_config(m_pool={"Fe": [2, 3]})
    new_config = make_config(m_pool={"Ca": [2]})
    _run(old_config, output_dir)
    before = _snapshot(output_dir)
    unrelated = output_dir / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")

    summary = _run(new_config, output_dir, overwrite=True)
    after = _snapshot(output_dir)
    assert all(after[name] != before[name] for name in OUTPUT_NAMES)
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert not (output_dir / RECOVERY_DIRECTORY_NAME).exists()
    assert not list(output_dir.glob(f"{output_module.STAGING_DIRECTORY_PREFIX}*"))

    with (output_dir / "compositions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    hypotheses = [
        json.loads(line)
        for line in (output_dir / "charge_hypotheses.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    formulas = (output_dir / "formulas.txt").read_text(encoding="utf-8").splitlines()
    disk_summary = json.loads((output_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert [row["formula"] for row in rows] == formulas
    assert [row["composition_key"] for row in rows] == [
        item["composition_key"] for item in hypotheses
    ]
    assert len(rows) == summary["results"]["unique_compositions"]
    assert disk_summary["results"] == summary["results"]
    assert disk_summary["effective_config"]["elements"]["additional_element_pool"] == {
        "Ca": [2]
    }


def test_default_overwrite_refusal_preserves_all_outputs(make_config, tmp_path):
    output_dir = tmp_path / "outputs"
    _run(make_config(m_pool={"Fe": [2, 3]}), output_dir)
    before = _snapshot(output_dir)

    with pytest.raises(OutputExistsError, match="refusing to overwrite"):
        _run(make_config(m_pool={"Ca": [2]}), output_dir)
    assert _snapshot(output_dir) == before


def test_non_file_target_is_rejected_before_other_outputs_change(
    make_config, tmp_path, capsys
):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    target_directory = output_dir / "charge_hypotheses.jsonl"
    target_directory.mkdir()
    existing = output_dir / "compositions.csv"
    existing.write_text("old", encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        main(
            [
                "--config",
                str(make_config(m_pool={})),
                "--output-dir",
                str(output_dir),
                "--overwrite",
            ]
        )
    assert caught.value.code == 2
    assert "output filesystem operation failed" in capsys.readouterr().err
    assert existing.read_text(encoding="utf-8") == "old"
    assert target_directory.is_dir()
