from __future__ import annotations

import csv
import json
from argparse import Namespace

import pytest
from pymatgen.core import Composition

from ce_tb_enumerator.cli import run
from ce_tb_enumerator.errors import OutputExistsError


def _core_bytes(path):
    return tuple((path / name).read_bytes() for name in (
        "compositions.csv", "charge_hypotheses.jsonl", "formulas.txt"
    ))


def test_chinese_space_path_roundtrip_reproducibility_and_overwrite(make_config, tmp_path, monkeypatch):
    config = make_config(max_re=2, m_pool={"Fe": [2, 3]})
    working = tmp_path / "含中文 的工作目录"
    working.mkdir()
    monkeypatch.chdir(working)
    first = working / "结果 一"
    second = working / "结果 二"

    summary = run(Namespace(config=config, output_dir=first.relative_to(working), overwrite=False))
    run(Namespace(config=config, output_dir=second.relative_to(working), overwrite=False))
    assert summary["results"]["unique_compositions"] > 0
    assert _core_bytes(first) == _core_bytes(second)

    before = _core_bytes(first)
    with pytest.raises(OutputExistsError):
        run(Namespace(config=config, output_dir=first.relative_to(working), overwrite=False))
    assert _core_bytes(first) == before
    run(Namespace(config=config, output_dir=first.relative_to(working), overwrite=True))
    assert _core_bytes(first) == before

    with (first / "compositions.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == summary["results"]["unique_compositions"]
    assert "\r\r\n" not in (first / "compositions.csv").read_bytes().decode("utf-8")
    for row in rows:
        parsed = {k: int(v) for k, v in Composition(row["formula"]).get_el_amt_dict().items()}
        key = "|".join(f"{symbol}:{parsed[symbol]}" for symbol in sorted(parsed))
        assert key == row["composition_key"]

    lines = (first / "charge_hypotheses.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(rows)
    assert all(json.loads(line)["charge_hypotheses"] for line in lines)


def test_import_does_not_run_enumeration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import ce_tb_enumerator  # noqa: F401

    assert list(tmp_path.iterdir()) == []
