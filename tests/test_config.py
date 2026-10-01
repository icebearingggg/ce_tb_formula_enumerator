from __future__ import annotations

import json

import pytest

from ce_tb_enumerator.config import load_settings
from ce_tb_enumerator.enumerator import enumerate_compositions
from ce_tb_enumerator.errors import ConfigurationError


def _mutate(path, callback):
    data = json.loads(path.read_text(encoding="utf-8"))
    callback(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    "mutation, match",
    [
        (lambda d: d.update({"mystery": 1}), "unknown field"),
        (lambda d: d["budgets"].update({"x_re_min": 1.1}), "between 0 and 1"),
        (lambda d: d["budgets"].update({"formula_unit_atom_max": 0}), "positive integer"),
        (lambda d: d["elements"]["additional_element_pool"].update({"Xx": [2]}), "unknown element"),
        (lambda d: d["elements"]["additional_element_pool"].update({"Ce": [3]}), "not allowed"),
        (lambda d: d["elements"]["additional_element_pool"].update({"Pb": [2]}), "conflicts"),
        (lambda d: d["elements"]["additional_element_pool"].update({"Fe": []}), "missing oxidation"),
        (lambda d: d["elements"]["additional_element_pool"].update({"Fe": [2.5]}), "positive integers"),
        (lambda d: d["elements"].update({"additional_element_pool": []}), "JSON object"),
    ],
)
def test_invalid_configuration_is_rejected(make_config, mutation, match):
    path = make_config()
    _mutate(path, mutation)
    with pytest.raises(ConfigurationError, match=match):
        load_settings(path)


def test_utf8_bom_and_config_relative_output(make_config):
    path = make_config()
    text = path.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8-sig")
    settings = load_settings(path)
    assert settings.config_path == path.resolve()
    assert settings.output_directory == (path.parent / "../results/default_run").resolve()


def _hypothesis_set(records):
    return {
        (
            record.composition_key,
            hypothesis.m_oxidation_state,
            hypothesis.k,
            hypothesis.z_re_required,
        )
        for record in records
        for hypothesis in record.hypotheses
    }


def test_empty_m_pool_enumerates_exactly_the_no_m_subset(make_config):
    empty_settings = load_settings(make_config(m_pool={}))
    assert empty_settings.m_pool == {}
    empty_records, _ = enumerate_compositions(empty_settings)
    assert empty_records
    assert all(record.c == 0 and record.additional_element is None for record in empty_records)
    assert all(
        hypothesis.m_oxidation_state is None
        for record in empty_records
        for hypothesis in record.hypotheses
    )

    full_settings = load_settings(make_config(m_pool={"Fe": [2, 3]}))
    full_records, _ = enumerate_compositions(full_settings)
    full_no_m = [record for record in full_records if record.additional_element is None]
    assert {record.composition_key for record in empty_records} == {
        record.composition_key for record in full_no_m
    }
    assert _hypothesis_set(empty_records) == _hypothesis_set(full_no_m)
