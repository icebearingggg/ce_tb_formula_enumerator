"""Atomic, cross-platform serialization of enumeration results."""

from __future__ import annotations

import csv
import json
import os
import platform
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable, TextIO

from . import __version__
from .config import Settings
from .errors import OutputExistsError
from .model import CompositionRecord


OUTPUT_NAMES = (
    "compositions.csv",
    "charge_hypotheses.jsonl",
    "formulas.txt",
    "run_summary.json",
)


def _number(value: Fraction) -> str:
    return format(float(value), ".12g")


def _fraction_payload(value: Fraction) -> dict[str, Any]:
    return {
        "value": float(value),
        "exact": str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}",
    }


def _atomic_text_write(path: Path, writer: Callable[[TextIO], None], newline: str | None = None) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _preflight(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise OutputExistsError(f"output path exists and is not a directory: {output_dir}")
    existing = [output_dir / name for name in OUTPUT_NAMES if (output_dir / name).exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise OutputExistsError(f"refusing to overwrite existing output file(s): {joined}")
    output_dir.mkdir(parents=True, exist_ok=True)


def write_outputs(
    records: list[CompositionRecord],
    settings: Settings,
    enumeration_stats: dict[str, object],
    overwrite: bool,
    started_at: datetime,
    elapsed_seconds: float,
) -> dict[str, Any]:
    output_dir = settings.output_directory
    _preflight(output_dir, overwrite)

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

    # Preflight occurs before every write; each individual file is replaced atomically.
    _atomic_text_write(output_dir / "compositions.csv", write_csv, newline="")
    _atomic_text_write(output_dir / "charge_hypotheses.jsonl", write_hypotheses, newline="\n")
    _atomic_text_write(output_dir / "formulas.txt", write_formulas, newline="\n")
    _atomic_text_write(output_dir / "run_summary.json", write_summary, newline="\n")
    return summary
