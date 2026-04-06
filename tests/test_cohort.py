"""Tests for Cohort dataclass and merge."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.cohort import Cohort, merge_cohorts

def test_cohort_creation():
    c = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
               effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=None)
    assert c.count == 10
    assert c.last_worked_day is None  # default

def test_merge_cohorts():
    c1 = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    c2 = Cohort(count=5, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    merged = merge_cohorts([c1, c2])
    assert len(merged) == 1
    assert merged[0].count == 15

def test_merge_different_types_not_merged():
    c1 = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    c2 = Cohort(count=5, case_type="PSD2_15", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    merged = merge_cohorts([c1, c2])
    assert len(merged) == 2
