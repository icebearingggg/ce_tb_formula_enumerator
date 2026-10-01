from __future__ import annotations

import json
from pathlib import Path

import pytest

from ce_tb_enumerator.config import load_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default_config.json"


@pytest.fixture(scope="session")
def default_records():
    from ce_tb_enumerator.enumerator import enumerate_compositions

    settings = load_settings(DEFAULT_CONFIG, PROJECT_ROOT / "test-output-unused")
    records, stats = enumerate_compositions(settings)
    return records, stats


@pytest.fixture
def make_config(tmp_path):
    config_number = 0

    def factory(*, max_re: int = 2, m_pool: dict[str, list[int]] | None = None, **changes):
        nonlocal config_number
        config_number += 1
        raw = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        raw["budgets"]["rare_earth_count_max"] = max_re
        raw["budgets"]["formula_unit_atom_max"] = 12
        raw["elements"]["additional_element_pool"] = (
            {"Fe": [2, 3]} if m_pool is None else m_pool
        )
        for dotted, value in changes.items():
            section, field = dotted.split("__", 1)
            raw[section][field] = value
        path = tmp_path / f"config-{config_number}.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return path

    return factory
