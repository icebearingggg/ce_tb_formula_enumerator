from __future__ import annotations

from fractions import Fraction
from functools import reduce
from math import gcd

from ce_tb_enumerator.config import load_settings
from ce_tb_enumerator.enumerator import composition_key, enumerate_compositions


def test_small_space_matches_independent_direct_enumeration(make_config):
    settings = load_settings(make_config(max_re=2, m_pool={"Fe": [2, 3]}))
    records, _ = enumerate_compositions(settings)
    actual = {
        (record.composition_key, hypothesis.m_oxidation_state, hypothesis.k)
        for record in records
        for hypothesis in record.hypotheses
    }

    expected = set()
    max_atoms = settings.budgets.formula_unit_atom_max
    for a in range(3):
        for b in range(3):
            rare_earth = a + b
            if not 1 <= rare_earth <= 2:
                continue
            for symbol, states, c_values in [(None, [None], [0]), ("Fe", [2, 3], range(1, rare_earth + 1))]:
                for c in c_values:
                    if Fraction(rare_earth, rare_earth + c) < settings.budgets.x_re_min:
                        continue
                    for oxygen in range(max_atoms + 1):
                        for fluorine in range(max_atoms + 1):
                            if oxygen + fluorine < 1 or a + b + c + oxygen + fluorine > max_atoms:
                                continue
                            if reduce(gcd, [v for v in (a, b, c, oxygen, fluorine) if v]) != 1:
                                continue
                            for state in states:
                                m_charge = 0 if state is None else c * state
                                k = 2 * oxygen + fluorine - m_charge - 3 * rare_earth
                                if 0 <= k <= rare_earth:
                                    counts = {"Ce": a, "Tb": b, "O": oxygen, "F": fluorine}
                                    if symbol is not None:
                                        counts[symbol] = c
                                    counts = {key: value for key, value in counts.items() if value}
                                    expected.add((composition_key(counts), state, k))
    assert actual == expected
