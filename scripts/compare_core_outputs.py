"""Compare platform-independent scientific content from two completed runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _keys(directory: Path) -> set[str]:
    with (directory / "compositions.csv").open("r", encoding="utf-8", newline="") as handle:
        return {row["composition_key"] for row in csv.DictReader(handle)}


def _normalized_hypotheses(directory: Path) -> dict[str, list[tuple[Any, ...]]]:
    result: dict[str, list[tuple[Any, ...]]] = {}
    with (directory / "charge_hypotheses.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            hypotheses = [
                (
                    item["M_oxidation_state"],
                    item["z_RE_required"]["exact"],
                    item["k"],
                    item["O_oxidation_state"],
                    item["F_oxidation_state"],
                    tuple(item["Ce_allowed_oxidation_states"]),
                    tuple(item["Tb_allowed_oxidation_states"]),
                )
                for item in row["charge_hypotheses"]
            ]
            result[row["composition_key"]] = sorted(hypotheses, key=repr)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    args = parser.parse_args()
    keys_a, keys_b = _keys(args.run_a), _keys(args.run_b)
    hypotheses_a = _normalized_hypotheses(args.run_a)
    hypotheses_b = _normalized_hypotheses(args.run_b)
    if keys_a != keys_b or hypotheses_a != hypotheses_b:
        print(f"composition keys only in A: {len(keys_a - keys_b)}")
        print(f"composition keys only in B: {len(keys_b - keys_a)}")
        differing = sum(
            hypotheses_a.get(key) != hypotheses_b.get(key) for key in keys_a | keys_b
        )
        print(f"keys with differing normalized hypotheses: {differing}")
        return 1
    print(f"MATCH: {len(keys_a)} composition keys and normalized charge hypotheses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
