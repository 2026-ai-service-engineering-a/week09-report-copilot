"""말로 한 기간을 날짜로 옮기는 자리.

**코드가 하는 일이라 테스트로 고정할 수 있다.** 모델에게 맡겼다면 여기에
쓸 수 있는 것은 "대체로 맞는다"뿐이었을 것이다.
"""

import datetime as dt

import pytest

from core import daterange as dr


@pytest.mark.parametrize("said,expected", [
    ("2026년도 전체 1월부터 월별 관객수를 보여줘", ("2026-01-01", "2026-08-31")),
    ("2026년 3월", ("2026-03-01", "2026-03-31")),
    ("1월부터 6월까지", ("2026-01-01", "2026-06-30")),
    ("2026-01-01부터 2026-06-30까지", ("2026-01-01", "2026-06-30")),
    ("최근 30일", ("2026-08-02", "2026-08-31")),
    ("8월", ("2026-08-01", "2026-08-31")),
])
def test_parses(said, expected, needs_db):
    start, end, _ = dr.parse(said, current=("2026-08-01", "2026-08-31"))
    assert (str(start), str(end)) == expected


def test_clamps_to_available_data(needs_db):
    """"2026년 전체"라고 해도 우리에게는 8월까지밖에 없다."""
    start, end, cut = dr.parse("2026년", current=("2026-08-01", "2026-08-31"))
    assert (str(start), str(end)) == ("2026-01-01", "2026-08-31")
    assert cut is True, "잘랐으면 잘랐다고 알려 줘야 한다"


def test_returns_none_when_there_is_no_period():
    assert dr.parse("국적별로 보여줘") is None


def test_year_is_inferred_from_the_current_report(needs_db):
    """"3월"이라고만 했을 때 엉뚱한 해로 가지 않게 한다."""
    start, _, _ = dr.parse("3월", current=("2025-09-01", "2025-09-30"))
    assert start.year == 2025
