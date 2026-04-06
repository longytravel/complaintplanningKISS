# complaints_model/bands.py
"""Band definitions — case-age ranges for pool-based FTE allocation."""
from __future__ import annotations

from dataclasses import dataclass

from .cohort import Cohort
from .regulatory import REGULATORY_DEADLINES


@dataclass(frozen=True)
class Band:
    name: str
    case_types: tuple[str, ...]   # which case types this band accepts
    age_min: int                   # inclusive lower bound
    age_max: int | None            # exclusive upper bound, None = unbounded
    use_biz_age: bool              # True → compare biz_age; False → compare cal_age
    requires_extension: bool = False  # only PSD2_35 can enter


# --- Separate model: 5 FCA bands + 5 PSD2 bands ---

FCA_BANDS: list[Band] = [
    Band("F1", ("FCA",), 0, 3, False),
    Band("F2", ("FCA",), 3, 20, False),
    Band("F3", ("FCA",), 20, 40, False),
    Band("F4", ("FCA",), 40, 56, False),
    Band("F5", ("FCA",), 56, None, False),
]

PSD2_BANDS: list[Band] = [
    Band("P1", ("PSD2_15", "PSD2_35"), 0, 3, True),
    Band("P2", ("PSD2_15", "PSD2_35"), 3, 10, True),
    Band("P3", ("PSD2_15", "PSD2_35"), 10, 15, True),
    Band("P4", ("PSD2_35",), 15, 35, True, requires_extension=True),
    Band("P5", ("PSD2_15", "PSD2_35"), 15, None, True),  # PSD2_15 jumps here from P3
]

# --- Combined model: 5 urgency tiers based on fraction of deadline elapsed ---
# Urgency = relevant_age / regulatory_deadline
# Thresholds: 0–20%, 20–50%, 50–80%, 80–100%, 100%+

_ALL_CASE_TYPES = ("FCA", "PSD2_15", "PSD2_35")

COMBINED_BANDS: list[Band] = [
    Band("C1", _ALL_CASE_TYPES, 0, 20, False),   # urgency 0–20%
    Band("C2", _ALL_CASE_TYPES, 20, 50, False),   # urgency 20–50%
    Band("C3", _ALL_CASE_TYPES, 50, 80, False),   # urgency 50–80%
    Band("C4", _ALL_CASE_TYPES, 80, 100, False),  # urgency 80–100%
    Band("C5", _ALL_CASE_TYPES, 100, None, False), # urgency 100%+ (breached)
]

# --- Hybrid model: dedicated PSD2 single pool + 5 FCA bands ---

_HYBRID_PSD2_BAND = Band("PSD2", ("PSD2_15", "PSD2_35"), 0, None, True)

HYBRID_BANDS: list[Band] = FCA_BANDS + [_HYBRID_PSD2_BAND]


def _urgency_pct(cohort: Cohort) -> int:
    """Return urgency as integer percentage of deadline elapsed (0–999)."""
    deadline = REGULATORY_DEADLINES[cohort.case_type]
    if cohort.case_type == "FCA":
        age = cohort.cal_age
    else:
        age = cohort.biz_age
    if deadline == 0:
        return 999
    return int(age * 100 / deadline)


def assign_band(cohort: Cohort, bands: list[Band]) -> str:
    """Return the band name a cohort belongs to given a list of bands.

    For combined bands (C1-C5), uses urgency-based assignment.
    For separate/hybrid bands, uses raw age-based assignment.
    """
    # Combined model: urgency-based
    if bands and bands[0].name.startswith("C"):
        pct = _urgency_pct(cohort)
        for band in bands:
            if band.age_max is None or pct < band.age_max:
                return band.name
        return bands[-1].name

    # Separate / Hybrid: type + age based
    for band in bands:
        if cohort.case_type not in band.case_types:
            continue
        if band.requires_extension and cohort.case_type != "PSD2_35":
            continue
        age = cohort.biz_age if band.use_biz_age else cohort.cal_age
        if band.age_max is None:
            if age >= band.age_min:
                return band.name
        elif band.age_min <= age < band.age_max:
            return band.name

    # Fallback: last matching-type band
    for band in reversed(bands):
        if cohort.case_type in band.case_types:
            if not band.requires_extension or cohort.case_type == "PSD2_35":
                return band.name
    raise ValueError(f"No band found for {cohort.case_type} age cal={cohort.cal_age} biz={cohort.biz_age}")


def get_bands_for_model(pooling_model: str) -> list[Band]:
    """Return the band list for a given pooling model."""
    if pooling_model == "separate":
        return FCA_BANDS + PSD2_BANDS
    elif pooling_model == "combined":
        return COMBINED_BANDS
    elif pooling_model == "hybrid":
        return HYBRID_BANDS
    raise ValueError(f"Unknown pooling model: {pooling_model}")


def detect_transitions(
    cohorts: list[Cohort],
    current_band_name: str,
    bands: list[Band],
) -> tuple[list[Cohort], list[Cohort]]:
    """Split cohorts into stayers (still in current_band_name) and movers (need reassignment).

    Movers lose their SRC flag and allocation status — they re-enter the new band's queue.
    """
    stayers: list[Cohort] = []
    movers: list[Cohort] = []
    for c in cohorts:
        if assign_band(c, bands) == current_band_name:
            stayers.append(c)
        else:
            # Reset allocation state for band transition
            movers.append(Cohort(
                count=c.count,
                case_type=c.case_type,
                cal_age=c.cal_age,
                biz_age=c.biz_age,
                effort_per_case=c.effort_per_case,
                is_src=False,  # SRC window missed — no longer SRC
                arrival_day=c.arrival_day,
                allocation_day=None,  # must be re-allocated in new band
                seeded=c.seeded,
                last_worked_day=c.last_worked_day,
            ))
    return stayers, movers
