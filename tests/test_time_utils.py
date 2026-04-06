"""Tests for time utility functions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.time_utils import is_workday, count_business_days_forward, count_business_days_signed, make_age

def test_is_workday():
    assert is_workday(0) == True   # Monday
    assert is_workday(4) == True   # Friday
    assert is_workday(5) == False  # Saturday
    assert is_workday(6) == False  # Sunday
    assert is_workday(7) == True   # Monday again

def test_count_business_days_forward():
    # 7 calendar days from Monday = 5 business days
    assert count_business_days_forward(0, 7) == 5
    # 1 calendar day from Friday: day 4 (Fri) + 0 offset = Fri (workday), so 1
    assert count_business_days_forward(4, 1) == 1
    # 0 calendar days = 0 business days
    assert count_business_days_forward(0, 0) == 0

def test_make_age_fca():
    # FCA uses calendar age — cal_age should equal reg_age
    cal, biz = make_age(10, "FCA")
    assert cal == 10

def test_make_age_psd2():
    # PSD2 uses business age — biz_age should equal reg_age
    cal, biz = make_age(10, "PSD2_15")
    assert biz == 10
