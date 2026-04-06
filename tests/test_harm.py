# tests/test_harm.py
"""Tests for harm score accumulation."""
import pytest
from complaints_model.cohort import Cohort
from complaints_model.harm import score_case_harm, accumulate_daily_harm


def _make_cohort(case_type: str, cal_age: int, biz_age: int,
                 count: float = 1.0, last_worked_day: int | None = None,
                 arrival_day: int = 0) -> Cohort:
    return Cohort(
        count=count, case_type=case_type, cal_age=cal_age, biz_age=biz_age,
        effort_per_case=1.0, is_src=False, arrival_day=arrival_day,
        allocation_day=None, seeded=False, last_worked_day=last_worked_day,
    )


class TestScoreCaseHarm:
    def test_non_breached_fca_no_breach_harm(self):
        """FCA at 30 cal days — not breached (deadline 56)."""
        c = _make_cohort("FCA", cal_age=30, biz_age=22, last_worked_day=95, arrival_day=70)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 0 (not breached), neglect = 100-95=5, wip = 1
        assert harm == pytest.approx(0 + 5.0 + 1.0)

    def test_breached_fca_has_breach_harm(self):
        """FCA at 60 cal days — 4 days past 56 deadline."""
        c = _make_cohort("FCA", cal_age=60, biz_age=43, last_worked_day=95, arrival_day=40)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 3*(60-56)=12, neglect = 100-95=5, wip = 1
        assert harm == pytest.approx(12.0 + 5.0 + 1.0)

    def test_breached_psd2_uses_biz_age(self):
        """PSD2_15 at 18 biz days — 3 days past 15 deadline."""
        c = _make_cohort("PSD2_15", cal_age=25, biz_age=18, last_worked_day=98, arrival_day=75)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 3*(18-15)=9, neglect = 100-98=2, wip = 1
        assert harm == pytest.approx(9.0 + 2.0 + 1.0)

    def test_never_touched_uses_arrival_day(self):
        """Case never worked on — neglect = sim_day - arrival_day."""
        c = _make_cohort("FCA", cal_age=10, biz_age=8, last_worked_day=None, arrival_day=90)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 0, neglect = 100-90=10, wip = 1
        assert harm == pytest.approx(0 + 10.0 + 1.0)

    def test_count_multiplies_harm(self):
        """A cohort of 5 cases produces 5x the harm."""
        c = _make_cohort("FCA", cal_age=10, biz_age=8, count=5.0, last_worked_day=99, arrival_day=90)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # per case: breach=0, neglect=1, wip=1 → 2.  × 5 = 10
        assert harm == pytest.approx(10.0)


class TestAccumulateDailyHarm:
    def test_empty_pools_return_zero(self):
        assert accumulate_daily_harm([], 100, 3.0, 1.0, 1.0) == 0.0

    def test_sums_across_all_cohorts(self):
        cohorts = [
            _make_cohort("FCA", cal_age=10, biz_age=8, count=2.0, last_worked_day=99, arrival_day=90),
            _make_cohort("FCA", cal_age=60, biz_age=43, count=1.0, last_worked_day=95, arrival_day=40),
        ]
        total = accumulate_daily_harm(cohorts, 100, 3.0, 1.0, 1.0)
        # cohort 1: per case breach=0 neglect=1 wip=1 → 2 × 2 = 4
        # cohort 2: per case breach=3*4=12 neglect=5 wip=1 → 18 × 1 = 18
        assert total == pytest.approx(22.0)
