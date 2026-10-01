from __future__ import annotations

from fractions import Fraction

from ce_tb_enumerator.enumerator import composition_key


def _record(records, counts):
    key = composition_key(counts)
    return next(record for record in records if record.composition_key == key)


def _hypotheses(record):
    return {(item.m_oxidation_state, item.z_re_required, item.k) for item in record.hypotheses}


def test_required_scientific_examples(default_records):
    records, _ = default_records

    ceo2 = _record(records, {"Ce": 1, "O": 2})
    assert (ceo2.x_re, ceo2.c_re, ceo2.r_ce, ceo2.y_f) == (
        Fraction(1), Fraction(1, 3), Fraction(1), Fraction(0)
    )
    assert _hypotheses(ceo2) == {(None, Fraction(4), 1)}

    ce2o3 = _record(records, {"Ce": 2, "O": 3})
    assert (ce2o3.x_re, ce2o3.c_re) == (Fraction(1), Fraction(2, 5))
    assert _hypotheses(ce2o3) == {(None, Fraction(3), 0)}

    tbof = _record(records, {"Tb": 1, "O": 1, "F": 1})
    assert (tbof.x_re, tbof.c_re, tbof.r_ce, tbof.y_f) == (
        Fraction(1), Fraction(1, 3), Fraction(0), Fraction(1, 2)
    )
    assert _hypotheses(tbof) == {(None, Fraction(3), 0)}

    mixed = _record(records, {"Ce": 1, "Tb": 1, "O": 3, "F": 1})
    assert (mixed.x_re, mixed.c_re, mixed.r_ce, mixed.y_f) == (
        Fraction(1), Fraction(1, 3), Fraction(1, 2), Fraction(1, 4)
    )
    assert _hypotheses(mixed) == {(None, Fraction(7, 2), 1)}

    calcium = _record(records, {"Ce": 2, "Ca": 1, "O": 4})
    assert (calcium.x_re, calcium.c_re) == (Fraction(2, 3), Fraction(2, 7))
    assert _hypotheses(calcium) == {(2, Fraction(3), 0)}

    potassium = _record(records, {"K": 1, "Tb": 3, "F": 12})
    assert (potassium.x_re, potassium.c_re) == (Fraction(3, 4), Fraction(3, 16))
    assert _hypotheses(potassium) == {(1, Fraction(11, 3), 2)}


def test_multivalent_m_is_merged(default_records):
    records, _ = default_records
    record = _record(records, {"Ce": 1, "Fe": 1, "O": 3})
    assert _hypotheses(record) == {
        (2, Fraction(4), 1),
        (3, Fraction(3), 0),
    }
    assert sum(item.composition_key == record.composition_key for item in records) == 1


def test_reduction_and_out_of_model_rejection(default_records):
    records, _ = default_records
    keys = {record.composition_key for record in records}
    assert composition_key({"Ce": 1, "O": 2}) in keys
    assert composition_key({"Ce": 2, "O": 4}) not in keys
    assert composition_key({"Ce": 1, "O": 1}) not in keys
    assert composition_key({"Ce": 1, "O": 1, "F": 3}) not in keys


def test_all_records_are_reduced_and_unique(default_records):
    from math import gcd
    from functools import reduce

    records, stats = default_records
    assert len({record.composition_key for record in records}) == len(records)
    assert len({record.composition_id for record in records}) == len(records)
    for record in records:
        assert reduce(gcd, [v for v in (record.a, record.b, record.c, record.m, record.n) if v]) == 1
        assert record.hypotheses
    assert stats["unique_compositions"] == len(records)
    assert stats["unique_hypotheses"] == sum(len(record.hypotheses) for record in records)
