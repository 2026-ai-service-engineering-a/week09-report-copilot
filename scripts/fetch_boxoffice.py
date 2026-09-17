"""KOBIS 일별 박스오피스를 받아 `data/`에 CSV로 둔다.

**API 키가 필요 없다.** 영화진흥위원회 오픈API는 키 발급이 필요하지만, 통계
화면은 공개이고 한 번의 요청으로 최대 7일치를 돌려준다. 수강생이 계정을 만들지
않아도 재현되게 하려고 이쪽을 쓴다. `robots.txt`는 `allow: /`다.

받는 것은 둘이다.

  · `data/boxoffice.csv`  일자 × 영화의 실적. 1년이면 4만 행 남짓
  · `data/movies.csv`     영화 마스터. 장르·등급·국가·배급사·시놉시스

마스터는 **롱테일을 자른 뒤에** 받는다. 1년치에 등장하는 영화가 5천 편이 넘지만
누적 관객 1,000명 이상인 750편이 관객의 99.6%를 설명한다. 자르지 않으면 상세
페이지를 5천 번 긁어야 하고, 얻는 것은 0.4%다.

    docker compose exec api python -m scripts.fetch_boxoffice
    docker compose exec api python -m scripts.fetch_boxoffice --from 2026-01-01 --to 2026-03-31
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path

DAILY_URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"
DETAIL_URL = "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieDtl.do?code={}&sType="

DATA = Path(__file__).resolve().parent.parent / "data"

# 교안 2장 6절의 수치가 이 기간 기준이다. 바꾸면 교안과 달라진다.
DEFAULT_FROM = "2025-09-01"
DEFAULT_TO = "2026-08-31"

# 롱테일 컷. 근거는 교안 2장 6절의 표에 있다.
MIN_TOTAL_AUDIENCE = 1_000

DAILY_HEADER = [
    "stat_date", "movie_cd", "rank", "movie_nm_raw", "open_dt",
    "sales_amt", "sales_share", "sales_change", "sales_acc",
    "audi_cnt", "audi_change", "audi_acc", "scrn_cnt", "show_cnt",
]
MOVIE_HEADER = [
    "movie_cd", "movie_nm", "movie_type", "genre",
    "running_time", "watch_grade", "nation", "distributor", "synopsis",
]

_CAPTION = re.compile(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일")
_MOVIE_CD = re.compile(r"mstView\('movie','(\d+)'\)")

DURATION = re.compile(r"^\d+분")
# 등급은 **집합이 아니라 무늬로 잡는다.** 옛 영화가 옛 등급 이름을 달고 온다.
# 재개봉 750편 중 28편이 그랬다: `연소자관람가` · `고등학생이상관람가` ·
# `18세관람가` · `12세 미만인 자는 관람할 수 없는 등급`. 지금 쓰는 다섯 가지만
# 적어 두면 이것들이 한 칸씩 밀려 **국적 자리에 등급이 들어앉는다**
GRADE = re.compile(r"(관람가|관람불가|관람할\s*수\s*없는|제한상영)")
# 요약정보 뒤에 이어 붙는 **섹션 제목**들. 값이 아니라 칸 이름이므로 국가로
# 오해하면 안 된다. 등급이 없는 영화에서 정확히 이것들이 한 칸 앞으로 당겨진다.
SECTION_LABELS = {"등급분류", "홍보용장르", "개봉일", "제작연도", "해당정보없음"}


def _opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    op.addheaders = [("User-Agent", "Mozilla/5.0"), ("Referer", DAILY_URL)]
    return op


def _text(fragment: str) -> list[str]:
    """태그를 지우고 눈에 보이는 조각만 남긴다."""
    flat = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]*>", "|", fragment)))
    return [part.strip() for part in flat.split("|") if part.strip()]


def _cells(row_html: str) -> list[str]:
    return [
        html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]*>", "", cell))).strip()
        for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
    ]


def fetch_daily(date_from: str, date_to: str) -> list[list[str]]:
    """주 단위로 끊어 받는다. 7일을 넘기면 조회 에러 페이지가 돌아온다."""
    op = _opener()
    page = op.open(DAILY_URL, timeout=30).read().decode("utf-8", "replace")
    token = re.search(r'name="CSRFToken"[^>]*value="([^"]+)"', page).group(1)

    rows: list[list[str]] = []
    day = dt.date.fromisoformat(date_from)
    last = dt.date.fromisoformat(date_to)
    while day <= last:
        end = min(day + dt.timedelta(days=6), last)
        body = urllib.parse.urlencode({
            "CSRFToken": token, "loadEnd": "0", "searchType": "search",
            "sSearchFrom": day.isoformat(), "sSearchTo": end.isoformat(),
            "sMultiMovieYn": "", "sRepNationCd": "", "sWideAreaCd": "",
        }).encode()
        got = op.open(DAILY_URL, data=body, timeout=60).read().decode("utf-8", "replace")
        rows += _parse_daily(got)
        print(f"  {day} ~ {end}  누적 {len(rows):,}행", flush=True)
        day = end + dt.timedelta(days=1)
        time.sleep(0.8)          # 공개 통계 화면이다. 막힐 이유를 만들지 않는다
    return rows


def _parse_daily(page: str) -> list[list[str]]:
    """표 하나가 하루가 아니다. 그리고 표는 날짜순으로 오지 않는다.

    KOBIS는 하루치를 표 둘로 나눠 보낸다(1~10위 / 11위 이하). 게다가 7일을
    요청하면 날짜별로 묶이지 않고 **종류별로** 묶여서 온다. 표 인덱스로 날짜를
    계산하면 어긋나므로, 각 `<table>` 직전의 캡션에서 읽는다.
    """
    rows: list[list[str]] = []
    for table in re.finditer(r"<table[^>]*>.*?</table>", page, re.S):
        before = page[max(0, table.start() - 900):table.start()]
        captions = _CAPTION.findall(html.unescape(re.sub("<[^>]*>", " ", before)))
        if not captions:
            continue
        year, month, day = captions[-1]
        stat_date = f"{year}-{month}-{day}"
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S):
            found = _MOVIE_CD.search(tr)
            cells = _cells(tr)
            if found and len(cells) >= 12:
                rows.append([stat_date, found.group(1)] + cells[:12])
    return rows


def _number(value: str) -> int:
    digits = (value or "").replace(",", "").strip()
    return int(digits) if re.fullmatch(r"-?\d+", digits) else 0


def pick_movies(rows: list[list[str]]) -> list[str]:
    """롱테일을 자른다. 자른다는 것은 버린다는 뜻이므로 얼마를 버렸는지 찍는다."""
    total: dict[str, int] = {}
    for row in rows:
        code = row[1]
        total[code] = total.get(code, 0) + _number(row[9])
    kept = sorted(code for code, audience in total.items() if audience >= MIN_TOTAL_AUDIENCE)
    everyone = sum(total.values()) or 1
    saved = sum(total[code] for code in kept)
    print(
        f"  영화 {len(total):,}편 중 {len(kept):,}편을 남긴다 "
        f"(누적 관객 {MIN_TOTAL_AUDIENCE:,}명 이상). "
        f"관객 보존율 {saved / everyone * 100:.2f}%"
    )
    return kept


def fetch_movie(code: str) -> list[str] | None:
    """상세 페이지 하나.

    요약정보 블록의 앞 세 칸은 늘 같다.

        [형태, 영화구분, 장르, (러닝타임), (등급), (국가), …섹션 라벨]

    뒤의 셋은 **빠질 수 있다.** 등급분류를 받지 않은 영화에는 등급이 없고,
    개봉 전 등록만 된 영화에는 러닝타임도 없다. 그래서 앞 셋은 자리로 읽고
    뒤 셋은 생김새로 가린다. 인덱스로만 자르면 등급이 없는 영화에서 한 칸씩
    밀려 국가 자리에 `등급분류`라는 **섹션 제목**이 들어온다.
    """
    request = urllib.request.Request(
        DETAIL_URL.format(code), headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        parts = _text(urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace"))
    except Exception as e:                       # 한 편이 실패해도 전체를 멈추지 않는다
        print(f"    ! {code}: {e}", flush=True)
        return None

    def after(label: str) -> str:
        if label not in parts:
            return ""
        index = parts.index(label) + 1
        return parts[index] if index < len(parts) else ""

    name = parts[0] if parts else ""
    summary: list[str] = []
    if "요약정보" in parts:
        start = parts.index("요약정보") + 1
        summary = parts[start:start + 8]

    movie_type = summary[1] if len(summary) > 1 else ""   # 일반영화 · 예술영화 · 독립영화
    genre = summary[2] if len(summary) > 2 else ""
    duration = grade = nation = ""
    for item in summary[3:]:
        if not duration and DURATION.match(item):
            duration = item
        elif not grade and GRADE.search(item):
            grade = item
        elif not nation and item not in SECTION_LABELS and "자막" not in item and "해설" not in item:
            nation = item

    return [code, name, movie_type, genre, duration, grade, nation,
            after("배급사"), after("시놉시스")]


def fetch_movies(codes: list[str]) -> list[list[str]]:
    """편당 0.85초라 750편이면 11분이다. 넷씩 동시에 받아 3분으로 줄인다."""
    done = 0

    def one(code: str) -> list[str] | None:
        nonlocal done
        row = fetch_movie(code)
        done += 1
        if done % 100 == 0:
            print(f"  마스터 {done:,}/{len(codes):,}편", flush=True)
        time.sleep(0.3)
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [row for row in pool.map(one, codes) if row]


def main() -> int:
    parser = argparse.ArgumentParser(description="KOBIS 일별 박스오피스 수집")
    parser.add_argument("--from", dest="date_from", default=DEFAULT_FROM)
    parser.add_argument("--to", dest="date_to", default=DEFAULT_TO)
    parser.add_argument("--skip-movies", action="store_true", help="마스터는 건너뛴다")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    print(f"일별 박스오피스: {args.date_from} ~ {args.date_to}")
    rows = fetch_daily(args.date_from, args.date_to)
    days = len({row[0] for row in rows})
    print(f"→ {len(rows):,}행 · {days}일 · 영화 {len({row[1] for row in rows}):,}편")

    with (DATA / "boxoffice.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(DAILY_HEADER)
        writer.writerows(rows)

    if args.skip_movies:
        return 0

    print("영화 마스터")
    codes = pick_movies(rows)
    movies = fetch_movies(codes)
    with (DATA / "movies.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(MOVIE_HEADER)
        writer.writerows(movies)
    print(f"→ {len(movies):,}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
