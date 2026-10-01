"""Strict configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from pymatgen.core import Element

from .errors import ConfigurationError


_TOP_KEYS = {"schema_version", "budgets", "elements", "exclusions", "output_directory"}
_BUDGET_KEYS = {
    "rare_earth_count_min",
    "rare_earth_count_max",
    "additional_element_count_min",
    "additional_element_to_re_max",
    "formula_unit_atom_max",
    "x_re_min",
}
_ELEMENT_KEYS = {
    "rare_earth_oxidation_states",
    "anion_oxidation_states",
    "additional_element_pool",
}
_EXCLUSION_KEYS = {"symbols", "atomic_number_at_least"}


@dataclass(frozen=True)
class Budgets:
    rare_earth_count_min: int
    rare_earth_count_max: int
    additional_element_count_min: int
    additional_element_to_re_max: Fraction
    formula_unit_atom_max: int
    x_re_min: Fraction


@dataclass(frozen=True)
class Settings:
    schema_version: int
    budgets: Budgets
    m_pool: dict[str, tuple[int, ...]]
    excluded_symbols: tuple[str, ...]
    atomic_number_at_least: int
    output_directory: Path
    config_path: Path
    effective_config: dict[str, Any]


def _reject_unknown(mapping: Any, allowed: set[str], location: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ConfigurationError(f"{location} must be a JSON object")
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ConfigurationError(f"unknown field(s) in {location}: {', '.join(unknown)}")
    missing = sorted(allowed - set(mapping))
    if missing:
        raise ConfigurationError(f"missing field(s) in {location}: {', '.join(missing)}")
    return mapping


def _positive_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{location} must be a positive integer")
    return value


def _nonnegative_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{location} must be a non-negative integer")
    return value


def _fraction(value: Any, location: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigurationError(f"{location} must be a finite number")
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ConfigurationError(f"{location} must be a finite number") from exc
    if not decimal_value.is_finite():
        raise ConfigurationError(f"{location} must be a finite number")
    return Fraction(decimal_value)


def _element(symbol: Any, location: str) -> Element:
    if not isinstance(symbol, str) or not symbol:
        raise ConfigurationError(f"{location} must be an element symbol")
    try:
        element = Element(symbol)
    except ValueError as exc:
        raise ConfigurationError(f"unknown element at {location}: {symbol!r}") from exc
    if element.symbol != symbol:
        raise ConfigurationError(f"element symbol at {location} must use canonical case: {element.symbol}")
    return element


def load_settings(config_path: Path, output_override: Path | None = None) -> Settings:
    """Load a UTF-8 or UTF-8-BOM JSON configuration and validate every field."""
    path = config_path.resolve()
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read configuration {path}: {exc}") from exc

    top = _reject_unknown(raw, _TOP_KEYS, "configuration")
    if top["schema_version"] != 1:
        raise ConfigurationError("schema_version must be 1")

    b = _reject_unknown(top["budgets"], _BUDGET_KEYS, "budgets")
    re_min = _positive_int(b["rare_earth_count_min"], "budgets.rare_earth_count_min")
    re_max = _positive_int(b["rare_earth_count_max"], "budgets.rare_earth_count_max")
    if re_min > re_max:
        raise ConfigurationError("rare_earth_count_min cannot exceed rare_earth_count_max")
    c_min = _nonnegative_int(
        b["additional_element_count_min"], "budgets.additional_element_count_min"
    )
    c_ratio = _fraction(
        b["additional_element_to_re_max"], "budgets.additional_element_to_re_max"
    )
    if c_ratio < 0:
        raise ConfigurationError("additional_element_to_re_max must be non-negative")
    n_fu_max = _positive_int(b["formula_unit_atom_max"], "budgets.formula_unit_atom_max")
    x_re_min = _fraction(b["x_re_min"], "budgets.x_re_min")
    if not 0 <= x_re_min <= 1:
        raise ConfigurationError("x_re_min must be between 0 and 1 inclusive")
    budgets = Budgets(re_min, re_max, c_min, c_ratio, n_fu_max, x_re_min)

    elements = _reject_unknown(top["elements"], _ELEMENT_KEYS, "elements")
    expected_re = {"Ce": [3, 4], "Tb": [3, 4]}
    if elements["rare_earth_oxidation_states"] != expected_re:
        raise ConfigurationError("Ce and Tb oxidation states must each be exactly [3, 4] in schema 1")
    if elements["anion_oxidation_states"] != {"O": -2, "F": -1}:
        raise ConfigurationError("O and F oxidation states must be exactly -2 and -1 in schema 1")

    exclusions = _reject_unknown(top["exclusions"], _EXCLUSION_KEYS, "exclusions")
    symbols_raw = exclusions["symbols"]
    if not isinstance(symbols_raw, list) or any(not isinstance(item, str) for item in symbols_raw):
        raise ConfigurationError("exclusions.symbols must be a list of element symbols")
    excluded_elements = [_element(symbol, "exclusions.symbols") for symbol in symbols_raw]
    if len({item.symbol for item in excluded_elements}) != len(excluded_elements):
        raise ConfigurationError("exclusions.symbols contains duplicates")
    z_limit = _positive_int(exclusions["atomic_number_at_least"], "exclusions.atomic_number_at_least")

    pool_raw = elements["additional_element_pool"]
    if not isinstance(pool_raw, dict):
        raise ConfigurationError("elements.additional_element_pool must be a JSON object")
    forbidden_m = {"Ce", "Tb", "O", "F"}
    excluded_set = {item.symbol for item in excluded_elements}
    m_pool: dict[str, tuple[int, ...]] = {}
    for symbol, states in pool_raw.items():
        element = _element(symbol, "elements.additional_element_pool")
        if symbol in forbidden_m:
            raise ConfigurationError(f"{symbol} is not allowed as additional element M")
        if symbol in excluded_set or element.Z >= z_limit:
            raise ConfigurationError(f"allowed M element {symbol} conflicts with exclusions")
        if not isinstance(states, list) or not states:
            raise ConfigurationError(f"missing oxidation state for M element {symbol}")
        checked: list[int] = []
        for state in states:
            if isinstance(state, bool) or not isinstance(state, int) or state <= 0:
                raise ConfigurationError(f"oxidation states for M element {symbol} must be positive integers")
            checked.append(state)
        if len(set(checked)) != len(checked):
            raise ConfigurationError(f"duplicate oxidation state for M element {symbol}")
        m_pool[symbol] = tuple(sorted(checked))

    output_raw = top["output_directory"]
    if not isinstance(output_raw, str) or not output_raw.strip():
        raise ConfigurationError("output_directory must be a non-empty path string")
    if output_override is None:
        configured_output = Path(output_raw)
        output_dir = configured_output if configured_output.is_absolute() else path.parent / configured_output
    else:
        output_dir = output_override
    output_dir = output_dir.resolve()

    effective = json.loads(json.dumps(top, ensure_ascii=False))
    effective["output_directory"] = str(output_dir)
    return Settings(
        schema_version=1,
        budgets=budgets,
        m_pool=dict(sorted(m_pool.items(), key=lambda item: Element(item[0]).Z)),
        excluded_symbols=tuple(sorted(excluded_set)),
        atomic_number_at_least=z_limit,
        output_directory=output_dir,
        config_path=path,
        effective_config=effective,
    )
