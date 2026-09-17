"""말로 한 기간을 날짜 둘로 바꾼다.

"2026년 전체 1월부터"를 `2026-01-01 ~ 2026-08-31`로 옮기는 자리다.

**왜 모델이 아니라 코드인가.** 7주차 라우팅 원칙 그대로다. 기간 표현은
가짓수가 정해져 있고 뜻이 하나뿐이다. 모델에게 물으면 매번 요금이 나가고,
무엇보다 **가끔 틀린다.** 날짜를 틀리면 리포트 전체가 틀린다.

그리고 여기서 하는 일이 하나 더 있다. **데이터가 없는 구간으로 나가지 않게
잘라 준다.** "2026년 전체"라고 해도 우리에게는 8월까지밖에 없고, 그 사실을
말해 주지 않으면 사용자는 9월부터 12월이 0이라고 오해한다.
"""

from __future__ import annotations

import datetime as dt
import re

from core import db

# 데이터가 없는 구간을 요청하면 여기로 자른다. 적재 전에도 돌아야 하므로
# 기본값을 두고, 실제 범위는 DB에서 읽는다
FALLBACK = (dt.date(2025, 9, 1), dt.date(2026, 8, 31))

_QUARTERS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def available() -> tuple[dt.date, dt.date]:
    """적재된 데이터의 실제 범위. 없으면 기본값."""
    try:
        row = db.fetch_one("SELECT MIN(stat_date), MAX(stat_date) FROM daily_boxoffice")
        if row and row[0]:
            return row[0], row[1]
    except Exception:
        pass
    return FALLBACK


def _end_of_month(year: int, month: int) -> dt.date:
    return (dt.date(year, month, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


def clamp(start: dt.date, end: dt.date) -> tuple[dt.date, dt.date, bool]:
    """데이터가 있는 구간으로 자른다. 잘렸는지도 함께 알려 준다."""
    low, high = available()
    cut = start < low or end > high
    return max(start, low), min(end, high), cut


def parse(text: str, *, current: tuple[str, str] | None = None) -> tuple[dt.date, dt.date, bool] | None:
    """말에서 기간을 읽는다. 못 읽으면 None.

    연도를 말하지 않으면 지금 리포트가 보고 있는 연도를 쓰고, 그것도 없으면
    데이터의 마지막 연도를 쓴다. "8월"이라고만 했을 때 엉뚱한 해로 가지
    않게 하려는 것이다.
    """
    said = (text or "").replace(" ", "")
    if not said:
        return None

    low, high = available()
    base_year = high.year
    if current:
        try:
            base_year = dt.date.fromisoformat(current[0]).year
        except ValueError:
            pass

    # ① 2026-01-01부터 2026-06-30까지
    iso = re.findall(r"(\d{4})-(\d{2})-(\d{2})", said)
    if len(iso) >= 2:
        return clamp(dt.date(*map(int, iso[0])), dt.date(*map(int, iso[1])))

    year_said = re.search(r"(\d{4})년", said)
    year = int(year_said.group(1)) if year_said else base_year

    # ② 분기
    quarter = re.search(r"([1-4])분기", said)
    if quarter:
        first, last = _QUARTERS[int(quarter.group(1))]
        return clamp(dt.date(year, first, 1), _end_of_month(year, last))

    # ③ 최근 N개월 · 지난 N일
    recent = re.search(r"(?:최근|지난)(\d+)(개월|달|일|주)", said)
    if recent:
        size, unit = int(recent.group(1)), recent.group(2)
        days = {"일": size, "주": size * 7, "개월": size * 30, "달": size * 30}[unit]
        return clamp(high - dt.timedelta(days=days - 1), high)

    # ④ N월부터 M월까지 · N월~M월
    span = re.search(r"(\d{1,2})월[부터~-]+(\d{1,2})월", said)
    if span:
        first, last = int(span.group(1)), int(span.group(2))
        return clamp(dt.date(year, first, 1), _end_of_month(year, last))

    # ⑤ N월부터 (끝이 없다)
    #
    # 연도를 함께 말했으면 **그 해의 끝까지**로 읽는다. "2026년 1월부터"는
    # 2026년을 말한 것이지 오늘까지를 말한 것이 아니다. 자르는 것은 clamp가
    # 하고, 잘랐다는 사실은 그때 알려 준다
    open_end = re.search(r"(\d{1,2})월부터", said)
    if open_end:
        start = dt.date(year, int(open_end.group(1)), 1)
        return clamp(start, dt.date(year, 12, 31) if year_said else high)

    # ⑥ N월 하나
    single = re.search(r"(\d{1,2})월", said)
    if single:
        month = int(single.group(1))
        return clamp(dt.date(year, month, 1), _end_of_month(year, month))

    # ⑦ 연도만. "2026년" · "2026년 전체" · "올해" · "작년"
    if year_said or re.search(r"(올해|작년|전체기간|전기간)", said):
        if "작년" in said:
            year = high.year - 1
        return clamp(dt.date(year, 1, 1), dt.date(year, 12, 31))

    return None


def describe(start: dt.date, end: dt.date, *, cut: bool) -> str:
    """사용자에게 무엇을 봤는지 말해 준다. **잘렸으면 잘렸다고 말한다.**"""
    body = f"{start} ~ {end}"
    if not cut:
        return body
    low, high = available()
    return f"{body} (데이터가 있는 구간으로 잘랐습니다. 전체 범위는 {low} ~ {high})"
