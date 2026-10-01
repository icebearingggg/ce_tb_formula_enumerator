"""Atomic, cross-platform serialization of enumeration results."""

from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable, TextIO

from . import __version__
from .config import Settings
from .errors import OutputExistsError, OutputRecoveryError, OutputTransactionError
from .model import CompositionRecord


OUTPUT_NAMES = (
    "compositions.csv",
    "charge_hypotheses.jsonl",
    "formulas.txt",
    "run_summary.json",
)
RECOVERY_DIRECTORY_NAME = ".ce-tb-output-recovery"
STAGING_DIRECTORY_PREFIX = ".ce-tb-output-stage-"
RECOVERY_MANIFEST_NAME = "manifest.json"


def _number(value: Fraction) -> str:
    return format(float(value), ".12g")


def _fraction_payload(value: Fraction) -> dict[str, Any]:
    return {
        "value": float(value),
        "exact": str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}",
    }


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _write_text_file(
    path: Path, writer: Callable[[TextIO], None], newline: str | None = None
) -> None:
    with path.open("x", encoding="utf-8", newline=newline) as handle:
        writer(handle)
        handle.flush()
        os.fsync(handle.fileno())


def _write_manifest(recovery_dir: Path, manifest: dict[str, Any]) -> None:
    temporary = recovery_dir / f".{RECOVERY_MANIFEST_NAME}.tmp"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, recovery_dir / RECOVERY_MANIFEST_NAME)


def _replace_output(source: Path, target: Path) -> None:
    """Replace one named output; kept separate for deterministic fault injection."""
    os.replace(source, target)


def _preflight(output_dir: Path, overwrite: bool) -> dict[str, bool]:
    if output_dir.exists() and not output_dir.is_dir():
        raise OutputExistsError(f"output path exists and is not a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    if _path_present(recovery_dir):
        raise OutputRecoveryError(
            "unfinished output recovery state exists; inspect its manifest and resolve it "
            f"before another write: {recovery_dir}"
        )

    original_state: dict[str, bool] = {}
    existing: list[Path] = []
    for name in OUTPUT_NAMES:
        target = output_dir / name
        present = _path_present(target)
        original_state[name] = present
        if present:
            if target.is_symlink() or not target.is_file():
                raise OutputTransactionError(
                    f"output target exists but is not a regular file: {target}"
                )
            existing.append(target)
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise OutputExistsError(f"refusing to overwrite existing output file(s): {joined}")
    return original_state


def _copy_backup(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)
    with destination.open("rb+") as handle:
        os.fsync(handle.fileno())


def _restore_from_backup(backup: Path, target: Path) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.restore-", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    os.close(fd)
    try:
        shutil.copy2(backup, temporary)
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        _replace_output(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _record_recovery_state(
    recovery_dir: Path,
    manifest: dict[str, Any],
    *,
    status: str,
    summary: str,
    details: dict[str, Any],
    instructions: str,
) -> None:
    manifest["status"] = status
    manifest.update(details)
    try:
        _write_manifest(recovery_dir, manifest)
    except OSError:
        pass
    report = recovery_dir / "RECOVERY_REQUIRED.txt"
    try:
        detail_lines = [
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in details.items()
        ]
        report.write_text(
            f"Status: {status}\n"
            f"{summary}\n"
            "Preserve this directory and inspect "
            f"{RECOVERY_MANIFEST_NAME} plus the remaining files before writing again.\n"
            f"Action: {instructions}\n"
            + "\n".join(detail_lines)
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _rollback_outputs(
    output_dir: Path,
    recovery_dir: Path,
    original_state: dict[str, bool],
) -> list[str]:
    errors: list[str] = []
    for name in OUTPUT_NAMES:
        target = output_dir / name
        try:
            if original_state[name]:
                _restore_from_backup(recovery_dir / f"{name}.backup", target)
            elif _path_present(target):
                if target.is_dir() and not target.is_symlink():
                    raise IsADirectoryError(f"cannot remove unexpected directory {target}")
                target.unlink()
        except OSError as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return errors


def _publish_staged_outputs(
    output_dir: Path,
    staging_dir: Path,
    original_state: dict[str, bool],
) -> None:
    current_state = {name: _path_present(output_dir / name) for name in OUTPUT_NAMES}
    if current_state != original_state:
        raise OutputTransactionError(
            "named output files changed while new results were being prepared; refusing to publish"
        )

    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    try:
        recovery_dir.mkdir()
    except FileExistsError as exc:
        raise OutputRecoveryError(
            "another writer or unfinished recovery state is present; inspect: "
            f"{recovery_dir}"
        ) from exc

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "preparing_backups",
        "output_directory": str(output_dir),
        "staging_directory": str(staging_dir),
        "outputs": {
            name: {
                "originally_existed": original_state[name],
                "backup": f"{name}.backup" if original_state[name] else None,
            }
            for name in OUTPUT_NAMES
        },
    }
    try:
        _write_manifest(recovery_dir, manifest)
        for name in OUTPUT_NAMES:
            if original_state[name]:
                _copy_backup(output_dir / name, recovery_dir / f"{name}.backup")
        manifest["status"] = "publishing"
        _write_manifest(recovery_dir, manifest)
    except OSError as exc:
        try:
            shutil.rmtree(recovery_dir)
        except OSError as cleanup_exc:
            cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            _record_recovery_state(
                recovery_dir,
                manifest,
                status="prepublish_cleanup_failed",
                summary=(
                    "New outputs were not published and the named outputs were not changed; "
                    "only cleanup of recovery material failed."
                ),
                details={
                    "backup_preparation_error": f"{type(exc).__name__}: {exc}",
                    "cleanup_error": cleanup_error,
                },
                instructions=(
                    "Keep the current named outputs. Do not restore from partial backups; "
                    "after verification, remove only the leftover recovery material."
                ),
            )
            raise OutputRecoveryError(
                "new outputs were not published and named outputs remain unchanged, but "
                f"recovery-material cleanup failed; inspect {recovery_dir}"
            ) from exc
        raise OutputTransactionError(
            f"could not prepare output backups; named outputs were not changed: {exc}"
        ) from exc

    try:
        for name in OUTPUT_NAMES:
            _replace_output(staging_dir / name, output_dir / name)
    except OSError as exc:
        recovery_errors = _rollback_outputs(output_dir, recovery_dir, original_state)
        if recovery_errors:
            _record_recovery_state(
                recovery_dir,
                manifest,
                status="recovery_failed",
                summary="Automatic output rollback was incomplete.",
                details={
                    "publish_error": f"{type(exc).__name__}: {exc}",
                    "recovery_errors": recovery_errors,
                },
                instructions=(
                    "Inspect the original-existence map and remaining *.backup files, then "
                    "restore the original output state before removing recovery material."
                ),
            )
            raise OutputRecoveryError(
                "output publication failed and automatic rollback was incomplete; preserve "
                f"and inspect recovery material at {recovery_dir}"
            ) from exc
        try:
            shutil.rmtree(recovery_dir)
        except OSError as cleanup_exc:
            _record_recovery_state(
                recovery_dir,
                manifest,
                status="rolled_back_cleanup_failed",
                summary=(
                    "Publication failed, but automatic rollback completed and the original "
                    "outputs were restored; only cleanup of recovery material failed."
                ),
                details={
                    "publish_error": f"{type(exc).__name__}: {exc}",
                    "cleanup_error": f"{type(cleanup_exc).__name__}: {cleanup_exc}",
                },
                instructions=(
                    "Keep and verify the restored original outputs. Do not restore them again "
                    "from backups; after verification, remove only the leftover recovery material."
                ),
            )
            raise OutputRecoveryError(
                "publication failed and original outputs were restored successfully; only "
                f"recovery-material cleanup failed, so do not restore again; inspect {recovery_dir}"
            ) from exc
        raise OutputTransactionError(
            f"output publication failed; all named outputs were restored: {exc}"
        ) from exc

    manifest["status"] = "published"
    try:
        _write_manifest(recovery_dir, manifest)
        shutil.rmtree(recovery_dir)
    except OSError as exc:
        _record_recovery_state(
            recovery_dir,
            manifest,
            status="published_cleanup_failed",
            summary=(
                "All new outputs were published successfully; failure occurred only while "
                "cleaning obsolete recovery material."
            ),
            details={"cleanup_error": f"{type(exc).__name__}: {exc}"},
            instructions=(
                "Keep and verify the complete new outputs in the formal output directory. "
                "Do not restore old backups; after verification, remove only the leftover "
                "recovery material."
            ),
        )
        raise OutputRecoveryError(
            "all new outputs were published successfully; only recovery-material cleanup "
            f"failed, so keep the new outputs and do not restore old backups; inspect "
            f"{recovery_dir} before another overwrite"
        ) from exc


def write_outputs(
    records: list[CompositionRecord],
    settings: Settings,
    enumeration_stats: dict[str, object],
    overwrite: bool,
    started_at: datetime,
    elapsed_seconds: float,
) -> dict[str, Any]:
    output_dir = settings.output_directory
    original_state = _preflight(output_dir, overwrite)

    csv_fields = [
        "composition_id", "formula", "composition_key", "a", "b", "c", "m", "n", "M",
        "n_fu", "x_RE", "c_RE", "r_Ce", "y_F", "re_branch", "anion_class",
        "charge_hypothesis_count",
    ]

    def write_csv(handle: TextIO) -> None:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({
                "composition_id": record.composition_id,
                "formula": record.formula,
                "composition_key": record.composition_key,
                "a": record.a, "b": record.b, "c": record.c, "m": record.m, "n": record.n,
                "M": record.additional_element or "",
                "n_fu": record.n_fu,
                "x_RE": _number(record.x_re),
                "c_RE": _number(record.c_re),
                "r_Ce": _number(record.r_ce),
                "y_F": _number(record.y_f),
                "re_branch": record.re_branch,
                "anion_class": record.anion_class,
                "charge_hypothesis_count": len(record.hypotheses),
            })

    def write_hypotheses(handle: TextIO) -> None:
        for record in records:
            hypotheses = []
            for hypothesis in sorted(record.hypotheses):
                hypotheses.append({
                    "M_oxidation_state": hypothesis.m_oxidation_state,
                    "z_RE_required": _fraction_payload(hypothesis.z_re_required),
                    "k": hypothesis.k,
                    "O_oxidation_state": -2,
                    "F_oxidation_state": -1,
                    "Ce_allowed_oxidation_states": [3, 4],
                    "Tb_allowed_oxidation_states": [3, 4],
                    "interpretation": "k is the total number of formal Ce/Tb +4 contributions; no site or element assignment is implied.",
                })
            payload = {
                "composition_id": record.composition_id,
                "formula": record.formula,
                "composition_key": record.composition_key,
                "charge_hypotheses": hypotheses,
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    def write_formulas(handle: TextIO) -> None:
        for record in records:
            handle.write(record.formula + "\n")

    branch_counts = Counter(record.re_branch for record in records)
    anion_counts = Counter(record.anion_class for record in records)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "program": {
            "name": "ce-tb-formula-enumerator",
            "version": __version__,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "pymatgen_version": version("pymatgen"),
        },
        "effective_config": settings.effective_config,
        "results": {
            "unique_compositions": len(records),
            "feasible_charge_hypotheses": sum(len(record.hypotheses) for record in records),
            "composition_counts_by_re_branch": dict(sorted(branch_counts.items())),
            "composition_counts_by_anion_class": dict(sorted(anion_counts.items())),
        },
        "enumeration_statistics": enumeration_stats,
        "run_metadata": {
            "started_at_utc": started_at.astimezone(timezone.utc).isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed_seconds, 6),
            "platform": platform.platform(),
            "sys_executable": sys.executable,
            "config_path": str(settings.config_path),
            "output_directory": str(output_dir),
        },
        "reproducibility": {
            "core_outputs": ["compositions.csv", "charge_hypotheses.jsonl", "formulas.txt"],
            "note": "Core outputs are deterministic for an identical effective scientific configuration and program version; run metadata may differ.",
        },
    }

    def write_summary(handle: TextIO) -> None:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    staging_dir = Path(tempfile.mkdtemp(prefix=STAGING_DIRECTORY_PREFIX, dir=output_dir))
    recovery_dir = output_dir / RECOVERY_DIRECTORY_NAME
    try:
        _write_text_file(staging_dir / "compositions.csv", write_csv, newline="")
        _write_text_file(
            staging_dir / "charge_hypotheses.jsonl", write_hypotheses, newline="\n"
        )
        _write_text_file(staging_dir / "formulas.txt", write_formulas, newline="\n")
        _write_text_file(staging_dir / "run_summary.json", write_summary, newline="\n")
        _publish_staged_outputs(output_dir, staging_dir, original_state)
    except BaseException:
        if not _path_present(recovery_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    try:
        shutil.rmtree(staging_dir)
    except OSError as exc:
        raise OutputTransactionError(
            f"outputs were published but temporary staging cleanup failed at {staging_dir}: {exc}"
        ) from exc
    return summary
