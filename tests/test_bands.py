# tests/test_bands.py
"""Tests for band definitions and case-to-band assignment."""
import pytest
from complaints_model.cohort import Cohort
from complaints_model.bands import (
    Band, FCA_BANDS, PSD2_BANDS, COMBINED_BANDS,
    get_bands_for_model, assign_band, detect_transitions,
)


def _make_cohort(case_type: str, cal_age: int, biz_age: int) -> Cohort:
    return Cohort(
        count=1.0, case_type=case_type, cal_age=cal_age, biz_age=biz_age,
        effort_per_case=1.0, is_src=False, arrival_day=0,
        allocation_day=None, seeded=False, last_worked_day=None,
    )


class TestFCABandAssignment:
    def test_fresh_case_goes_to_f1(self):
        c = _make_cohort("FCA", cal_age=1, biz_age=1)
        assert assign_band(c, FCA_BANDS) == "F1"

    def test_day3_goes_to_f2(self):
        c = _make_cohort("FCA", cal_age=3, biz_age=3)
        assert assign_band(c, FCA_BANDS) == "F2"

    def test_day20_goes_to_f3(self):
        c = _make_cohort("FCA", cal_age=20, biz_age=15)
        assert assign_band(c, FCA_BANDS) == "F3"

    def test_day40_goes_to_f4(self):
        c = _make_cohort("FCA", cal_age=40, biz_age=29)
        assert assign_band(c, FCA_BANDS) == "F4"

    def test_day56_goes_to_f5(self):
        c = _make_cohort("FCA", cal_age=56, biz_age=40)
        assert assign_band(c, FCA_BANDS) == "F5"

    def test_day100_goes_to_f5(self):
        c = _make_cohort("FCA", cal_age=100, biz_age=72)
        assert assign_band(c, FCA_BANDS) == "F5"


class TestPSD2BandAssignment:
    def test_fresh_psd2_goes_to_p1(self):
        c = _make_cohort("PSD2_15", cal_age=1, biz_age=1)
        assert assign_band(c, PSD2_BANDS) == "P1"

    def test_biz3_goes_to_p2(self):
        c = _make_cohort("PSD2_15", cal_age=5, biz_age=3)
        assert assign_band(c, PSD2_BANDS) == "P2"

    def test_biz10_goes_to_p3(self):
        c = _make_cohort("PSD2_15", cal_age=14, biz_age=10)
        assert assign_band(c, PSD2_BANDS) == "P3"

    def test_psd2_15_at_biz15_goes_to_p5_not_p4(self):
        """PSD2_15 (not extended) skips P4, goes straight to P5."""
        c = _make_cohort("PSD2_15", cal_age=21, biz_age=15)
        assert assign_band(c, PSD2_BANDS) == "P5"

    def test_psd2_35_at_biz15_goes_to_p4(self):
        """PSD2_35 (extended) enters P4."""
        c = _make_cohort("PSD2_35", cal_age=21, biz_age=15)
        assert assign_band(c, PSD2_BANDS) == "P4"

    def test_psd2_35_at_biz35_goes_to_p5(self):
        c = _make_cohort("PSD2_35", cal_age=49, biz_age=35)
        assert assign_band(c, PSD2_BANDS) == "P5"


class TestCombinedBandAssignment:
    def test_fresh_fca_goes_to_c1(self):
        c = _make_cohort("FCA", cal_age=2, biz_age=2)
        assert assign_band(c, COMBINED_BANDS) == "C1"

    def test_mid_fca_goes_to_c3(self):
        c = _make_cohort("FCA", cal_age=35, biz_age=25)
        assert assign_band(c, COMBINED_BANDS) == "C3"

    def test_breached_fca_goes_to_c5(self):
        c = _make_cohort("FCA", cal_age=60, biz_age=43)
        assert assign_band(c, COMBINED_BANDS) == "C5"

    def test_fresh_psd2_goes_to_c1(self):
        c = _make_cohort("PSD2_15", cal_age=1, biz_age=1)
        assert assign_band(c, COMBINED_BANDS) == "C1"

    def test_breached_psd2_goes_to_c5(self):
        c = _make_cohort("PSD2_15", cal_age=21, biz_age=16)
        assert assign_band(c, COMBINED_BANDS) == "C5"


class TestGetBandsForModel:
    def test_separate_returns_10_bands(self):
        bands = get_bands_for_model("separate")
        assert len(bands) == 10
        names = [b.name for b in bands]
        assert names == ["F1", "F2", "F3", "F4", "F5", "P1", "P2", "P3", "P4", "P5"]

    def test_combined_returns_5_bands(self):
        bands = get_bands_for_model("combined")
        assert len(bands) == 5
        names = [b.name for b in bands]
        assert names == ["C1", "C2", "C3", "C4", "C5"]

    def test_hybrid_returns_6_bands(self):
        bands = get_bands_for_model("hybrid")
        assert len(bands) == 6
        names = [b.name for b in bands]
        assert names == ["F1", "F2", "F3", "F4", "F5", "PSD2"]


class TestDetectTransitions:
    def test_fca_ages_past_band_boundary(self):
        """A case in F1 that aged to cal_age=3 should transition to F2."""
        c = _make_cohort("FCA", cal_age=3, biz_age=3)
        c.allocation_day = 0
        current_band = "F1"
        new_band = assign_band(c, FCA_BANDS)
        assert new_band != current_band
        assert new_band == "F2"

    def test_fca_stays_in_band(self):
        c = _make_cohort("FCA", cal_age=2, biz_age=2)
        assert assign_band(c, FCA_BANDS) == "F1"

    def test_detect_transitions_returns_movers(self):
        """detect_transitions identifies cohorts that need to move."""
        cohorts = [
            _make_cohort("FCA", cal_age=3, biz_age=3),   # should leave F1
            _make_cohort("FCA", cal_age=2, biz_age=2),   # stays in F1
        ]
        bands = FCA_BANDS
        stayers, movers = detect_transitions(cohorts, "F1", bands)
        assert len(stayers) == 1
        assert stayers[0].cal_age == 2
        assert len(movers) == 1
        assert movers[0].cal_age == 3
