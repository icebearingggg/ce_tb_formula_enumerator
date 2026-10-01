"""Complete bounded integer enumeration and composition validation."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from functools import reduce
from hashlib import sha256
from math import gcd
from typing import Iterable

from pymatgen.core import Composition, Element

from .config import Settings
from .model import ChargeHypothesis, CompositionRecord


def _gcd_nonzero(values: Iterable[int]) -> int:
    nonzero = [value for value in values if value]
    return reduce(gcd, nonzero)


def _counts_by_symbol(
    a: int, b: int, c: int, m: int, n: int, additional_element: str | None
) -> dict[str, int]:
    counts = {"Ce": a, "Tb": b, "O": m, "F": n}
    if additional_element is not None and c:
        counts[additional_element] = c
    return {symbol: count for symbol, count in counts.items() if count}


def composition_key(counts: dict[str, int]) -> str:
    return "|".join(f"{symbol}:{counts[symbol]}" for symbol in sorted(counts))


def formula_from_counts(
    a: int, b: int, c: int, m: int, n: int, additional_element: str | None
) -> str:
    # The domain-specific order is explicit and is not used as the uniqueness key.
    parts: list[tuple[str, int]] = [("Ce", a), ("Tb", b)]
    if additional_element is not None:
        parts.append((additional_element, c))
    parts.extend([("O", m), ("F", n)])
    return "".join(symbol + (str(count) if count != 1 else "") for symbol, count in parts if count)


def _pymatgen_cross_check(formula: str, counts: dict[str, int]) -> None:
    expected = Composition(counts)
    parsed = Composition(formula)
    if parsed != expected:
        raise RuntimeError(f"pymatgen formula cross-check failed for {formula}")
    reduced, factor = expected.get_reduced_composition_and_factor()
    if factor != 1 or reduced != expected:
        raise RuntimeError(f"composition is not reduced: {formula}")
    parsed_integer = {symbol: int(amount) for symbol, amount in parsed.get_el_amt_dict().items()}
    if parsed_integer != counts:
        raise RuntimeError(f"pymatgen count cross-check failed for {formula}")


def _filter_reason(
    settings: Settings, a: int, b: int, c: int, m: int, n: int
) -> str | None:
    budgets = settings.budgets
    rare_earth = a + b
    if rare_earth < budgets.rare_earth_count_min or rare_earth > budgets.rare_earth_count_max:
        return "rare_earth_count"
    if c < budgets.additional_element_count_min:
        return "additional_element_count_min"
    if Fraction(c, rare_earth) > budgets.additional_element_to_re_max:
        return "additional_element_to_re_max"
    if a + b + c + m + n > budgets.formula_unit_atom_max:
        return "formula_unit_atom_max"
    if Fraction(rare_earth, rare_earth + c) < budgets.x_re_min:
        return "x_re_min"
    return None


def _sort_key(record: CompositionRecord) -> tuple[object, ...]:
    branch_order = {"Ce-only": 0, "Tb-only": 1, "Ce/Tb-mixed": 2}
    anion_order = {"oxide": 0, "fluoride": 1, "oxyfluoride": 2}
    m_number = 0 if record.additional_element is None else Element(record.additional_element).Z
    return (
        branch_order[record.re_branch],
        anion_order[record.anion_class],
        m_number,
        record.a,
        record.b,
        record.c,
        record.m,
        record.n,
        record.composition_key,
    )


def enumerate_compositions(settings: Settings) -> tuple[list[CompositionRecord], dict[str, object]]:
    """Enumerate every formal-charge construction within the configured reduced bounds."""
    records: dict[str, CompositionRecord] = {}
    stats: Counter[str] = Counter()
    filter_counts: Counter[str] = Counter()
    max_re = settings.budgets.rare_earth_count_max

    for rare_earth in range(1, max_re + 1):
        for a in range(rare_earth + 1):
            b = rare_earth - a
            # The no-M branch is handled exactly once.
            branches: list[tuple[str | None, int, int | None]] = [(None, 0, None)]
            c_max = (rare_earth * settings.budgets.additional_element_to_re_max.numerator) // (
                settings.budgets.additional_element_to_re_max.denominator
            )
            for symbol, oxidation_states in settings.m_pool.items():
                for c in range(1, c_max + 1):
                    for oxidation_state in oxidation_states:
                        branches.append((symbol, c, oxidation_state))

            for symbol, c, oxidation_state in branches:
                m_charge = 0 if oxidation_state is None else c * oxidation_state
                for k_raw in range(rare_earth + 1):
                    positive_charge = 3 * rare_earth + k_raw + m_charge
                    for oxygen_raw in range(positive_charge // 2 + 1):
                        fluorine_raw = positive_charge - 2 * oxygen_raw
                        if oxygen_raw + fluorine_raw == 0:
                            continue
                        stats["raw_charge_constructions"] += 1
                        divisor = _gcd_nonzero((a, b, c, oxygen_raw, fluorine_raw))
                        ar, br, cr, mr, nr = (
                            a // divisor,
                            b // divisor,
                            c // divisor,
                            oxygen_raw // divisor,
                            fluorine_raw // divisor,
                        )
                        reason = _filter_reason(settings, ar, br, cr, mr, nr)
                        if reason is not None:
                            filter_counts[reason] += 1
                            continue

                        reduced_re = ar + br
                        reduced_m_charge = 0 if oxidation_state is None else cr * oxidation_state
                        k = 2 * mr + nr - reduced_m_charge - 3 * reduced_re
                        if not 0 <= k <= reduced_re:
                            raise RuntimeError("internal exact-charge invariant failed after reduction")
                        z_re = Fraction(2 * mr + nr - reduced_m_charge, reduced_re)
                        hypothesis = ChargeHypothesis(oxidation_state, k, z_re)
                        counts = _counts_by_symbol(ar, br, cr, mr, nr, symbol)
                        key = composition_key(counts)
                        formula = formula_from_counts(ar, br, cr, mr, nr, symbol)
                        if key not in records:
                            _pymatgen_cross_check(formula, counts)
                            records[key] = CompositionRecord(
                                composition_id=sha256(key.encode("utf-8")).hexdigest(),
                                formula=formula,
                                composition_key=key,
                                a=ar,
                                b=br,
                                c=cr,
                                m=mr,
                                n=nr,
                                additional_element=symbol,
                                hypotheses=set(),
                            )
                        before = len(records[key].hypotheses)
                        records[key].hypotheses.add(hypothesis)
                        if len(records[key].hypotheses) == before:
                            stats["duplicate_hypothesis_observations"] += 1
                        else:
                            stats["unique_hypotheses"] += 1

    ordered = sorted(records.values(), key=_sort_key)
    stats["unique_compositions"] = len(ordered)
    return ordered, {
        "definitions": {
            "raw_charge_constructions": "Generated (a,b,c,M,z_M,k,m,n) paths before reduction and filtering.",
            "filter_counts": "Generated paths rejected after integer reduction; one first-failing reason per path.",
            "duplicate_hypothesis_observations": "Accepted reduced paths duplicating an existing composition-level charge hypothesis.",
            "unique_hypotheses": "Distinct (M oxidation state, reduced k, exact z_RE_required) records summed over compositions.",
            "unique_compositions": "Distinct reduced elemental-count keys.",
        },
        "raw_charge_constructions": stats["raw_charge_constructions"],
        "filter_counts": dict(sorted(filter_counts.items())),
        "duplicate_hypothesis_observations": stats["duplicate_hypothesis_observations"],
        "unique_hypotheses": stats["unique_hypotheses"],
        "unique_compositions": stats["unique_compositions"],
    }
