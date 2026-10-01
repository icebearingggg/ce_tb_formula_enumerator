"""Immutable result records and exact-number helpers."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, order=True)
class ChargeHypothesis:
    m_oxidation_state: int | None
    k: int
    z_re_required: Fraction


@dataclass
class CompositionRecord:
    composition_id: str
    formula: str
    composition_key: str
    a: int
    b: int
    c: int
    m: int
    n: int
    additional_element: str | None
    hypotheses: set[ChargeHypothesis]

    @property
    def rare_earth_count(self) -> int:
        return self.a + self.b

    @property
    def n_fu(self) -> int:
        return self.a + self.b + self.c + self.m + self.n

    @property
    def x_re(self) -> Fraction:
        return Fraction(self.rare_earth_count, self.rare_earth_count + self.c)

    @property
    def c_re(self) -> Fraction:
        return Fraction(self.rare_earth_count, self.n_fu)

    @property
    def r_ce(self) -> Fraction:
        return Fraction(self.a, self.rare_earth_count)

    @property
    def y_f(self) -> Fraction:
        return Fraction(self.n, self.m + self.n)

    @property
    def re_branch(self) -> str:
        if self.b == 0:
            return "Ce-only"
        if self.a == 0:
            return "Tb-only"
        return "Ce/Tb-mixed"

    @property
    def anion_class(self) -> str:
        if self.n == 0:
            return "oxide"
        if self.m == 0:
            return "fluoride"
        return "oxyfluoride"
