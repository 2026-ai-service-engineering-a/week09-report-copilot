"""도구 — 5주차 계보 그대로다. pydantic 모델 하나가 스키마이자 검증이다.

이 랩의 도구는 셋이다.

  · `run_query`     제한된 스펙으로 집계한다. **SQL은 우리가 만든다**
  · `run_sql`       모델이 짠 SQL을 그대로 돈다. 랩 전용 스위치로만 열린다
  · `lookup_metric` 업무 용어의 뜻을 지표 사전에서 찾는다

앞의 둘이 같은 일을 하는 것이 일부러다. **모델에게 질의를 짜게 할 것인가,
고르게 할 것인가.** 이 선택이 교안 9장 1절의 주제이고, 둘을 나란히 두어야
차이를 보여줄 수 있다.

| | run_query (고르게) | run_sql (짜게) |
| 모델이 내놓는 것 | 지표 이름과 축 | SQL 문자열 |
| 무엇이 막나 | **스키마가 막는다** | 게이트와 DB 권한이 막는다 |
| 할 수 있는 질문 | 우리가 설계한 만큼 | 모델이 상상한 만큼 |
| 사고의 가짓수 | 적다 | 많다 |

기본은 `run_query`다. 스키마에 없는 축으로는 애초에 나눌 수 없으므로 막을
일이 생기지 않는다. `run_sql`은 `ALLOW_RAW_SQL=1`일 때만 등록된다.
"""

from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from core import db, metrics
from core.errors import BlockedQuery, UnknownMetric
from core.harness import gate_query

# 나눌 수 있는 축 → 실제 컬럼. 여기 없는 축으로는 group by가 되지 않는다.
# 이것이 `run_query`의 게이트다. 검사가 아니라 **표에 없으면 끝**이다
GROUP_COLUMNS: dict[str, str] = {
    # 시간 축. `group_by`를 비우면 일자별이고, 기간이 길면 점이 너무 많아진다.
    # 1년치를 일자별로 그리면 365개 점이라 아무것도 안 보인다
    "month": "to_char(date_trunc('month', d.stat_date), 'YYYY-MM')",
    "week": "to_char(date_trunc('week', d.stat_date), 'YYYY-MM-DD')",
    # 요일은 로케일에 기대지 않고 직접 붙인다. 컨테이너의 로케일이 바뀌면
    # `to_char(…, 'TMDy')`의 결과가 달라지고, 그러면 교안의 출력과 어긋난다
    "weekday": ("CASE EXTRACT(ISODOW FROM d.stat_date)"
                " WHEN 1 THEN '월' WHEN 2 THEN '화' WHEN 3 THEN '수' WHEN 4 THEN '목'"
                " WHEN 5 THEN '금' WHEN 6 THEN '토' ELSE '일' END"),
    "nation": "m.nation",
    "genre": "split_part(m.genre, ',', 1)",     # '사극, 액션'의 대표 장르 하나
    "movieType": "m.movie_type",
    "watchGrade": "m.watch_grade",
    "distributor": "m.distributor",
    "movieNm": "m.movie_nm",
}

# 지표 → 집계식. metrics.yaml의 expr을 SQL로 옮긴 것이고, 사전이 진실이다
METRIC_SQL: dict[str, str] = {
    "audi_cnt": "SUM(d.audi_cnt)",
    "audi_acc": "MAX(d.audi_acc)",
    "sales_amt": "SUM(d.sales_amt)",
    "scrn_cnt": "MAX(d.scrn_cnt)",
    "show_cnt": "SUM(d.show_cnt)",
    "audi_per_screen": "SUM(d.audi_cnt)::numeric / NULLIF(SUM(d.scrn_cnt), 0)",
    "turnover": "SUM(d.show_cnt)::numeric / NULLIF(SUM(d.scrn_cnt), 0)",
}


class RunQueryArgs(BaseModel):
    """박스오피스 집계 결과를 가져온다. 리포트 섹션 하나의 내용이 된다."""

    metric: str = Field(description="지표 id. 모르면 lookup_metric으로 먼저 찾는다")
    date_from: str = Field(description="시작 일자 (YYYY-MM-DD)")
    date_to: str = Field(description="종료 일자 (YYYY-MM-DD)")
    group_by: Literal["month", "week", "weekday", "nation", "genre", "movieType",
                      "watchGrade", "distributor", "movieNm"] | None = Field(
        default=None,
        description=(
            "나눌 축. 생략하면 일자별. 기간이 한 달을 넘으면 month나 week를 쓴다. "
            "weekday는 요일 패턴을 볼 때"
        ),
    )
    nation: str | None = Field(default=None, description="제작 국가로 거른다")
    movie_type: str | None = Field(default=None, description="영화 구분으로 거른다")
    limit: int = Field(default=10, ge=1, le=50, description="돌려줄 행 수")


def run_query(args: RunQueryArgs) -> dict:
    """SQL을 **우리가** 만든다. 모델은 지표와 축을 고를 뿐이다."""
    try:
        metric = metrics.by_id(args.metric)
    except UnknownMetric:
        metric = metrics.lookup(args.metric)       # 별칭으로 한 번 더 시도한다
    if not metric.computable:
        return {"error": f"'{metric.name}'은(는) 이 데이터로 계산할 수 없다: {metric.desc}"}
    if metric.id not in METRIC_SQL:
        return {"error": f"집계식이 없는 지표: {metric.id}"}

    expr = METRIC_SQL[metric.id]
    axis = GROUP_COLUMNS.get(args.group_by or "", "d.stat_date::text")
    label = args.group_by or "stat_date"

    where = ["d.stat_date BETWEEN %(f)s AND %(t)s"]
    # 시간 축에서는 `limit`이 화면에 보일 점의 수가 아니라 **기간을 자르는 칼**이
    # 된다. 12개월을 10으로 자르면 두 달이 조용히 사라지므로 넉넉히 연다
    cap = 400 if args.group_by in (None, "month", "week") else args.limit
    params: dict = {"f": args.date_from, "t": args.date_to, "n": cap}
    if args.nation and args.nation != "전체":
        where.append("m.nation = %(nation)s")
        params["nation"] = args.nation
    if args.movie_type and args.movie_type != "전체":
        where.append("m.movie_type = %(mtype)s")
        params["mtype"] = args.movie_type

    # 시간 축은 값이 아니라 **시간 순서**로 정렬한다. 추세를 보려고 만든 축인데
    # 큰 값부터 늘어놓으면 선이 뒤죽박죽이 된다
    time_axis = args.group_by in (None, "month", "week")
    if args.group_by == "weekday":
        # 요일도 시간 축이다. 값이 큰 순서로 늘어놓으면 주말이 앞으로 와서
        # 한 주의 모양이 보이지 않는다
        order = "MIN(EXTRACT(ISODOW FROM d.stat_date)) ASC"
    else:
        order = "1 ASC" if time_axis else "2 DESC NULLS LAST"
    sql = (
        f"SELECT {axis} AS label, {expr} AS value "
        f"FROM daily_boxoffice d JOIN movie m USING (movie_cd) "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY 1 ORDER BY {order} LIMIT %(n)s"
    )
    rows = db.fetch(sql, params)

    # 잘라 낸 뒤의 합이 아니라 **전체 합**을 함께 준다.
    # 이것이 없으면 작성가가 `limit 10`짜리 목록으로 비율을 계산하고,
    # 그 비율은 조금씩 틀린다. 틀린 줄도 모르는 종류의 오류다
    total = None
    if args.group_by is not None and metric.id in ("audi_cnt", "sales_amt", "show_cnt"):
        totals = db.fetch(
            f"SELECT {expr} FROM daily_boxoffice d JOIN movie m USING (movie_cd) "
            f"WHERE {' AND '.join(where)}",
            {k: v for k, v in params.items() if k != "n"},
        )
        total = float(totals[0][0]) if totals and totals[0][0] is not None else None

    return {
        "metric": metric.id,
        "unit": metric.unit,
        "groupBy": label,
        "total": total,
        "rows": [[row[0], float(row[1]) if row[1] is not None else None] for row in rows],
    }


class RunSqlArgs(BaseModel):
    """직접 짠 SQL로 조회한다. SELECT만 가능하고 limit이 있어야 한다."""

    sql: str = Field(min_length=10, max_length=2000, description="SELECT 문 하나")


def run_sql(args: RunSqlArgs) -> dict:
    """모델이 짠 SQL. 게이트가 첫째 층, 읽기 전용 계정이 둘째 층이다."""
    try:
        sql = gate_query(args.sql)
    except BlockedQuery as e:
        # 막힌 것도 결과다. 예외로 올리면 루프가 끊기고 모델이 고칠 기회를 잃는다
        return {"error": f"질의가 막혔다: {e}", "blocked": True}
    rows = db.fetch(sql)
    return {"rows": [[*row] for row in rows[:50]]}


class LookupMetricArgs(BaseModel):
    """업무 용어의 뜻과 계산식을 지표 사전에서 찾는다."""

    term: str = Field(description='찾을 용어 (예: "스크린당 관객수", "드롭률")')


def lookup_metric(args: LookupMetricArgs) -> dict:
    try:
        return metrics.lookup(args.term).to_dict()
    except UnknownMetric:
        # **지어내지 않게** 목록을 함께 준다. 빈손으로 돌려보내면 모델이 만든다
        return {
            "error": f"지표 사전에 '{args.term}'이(가) 없다",
            "available": [m.name for m in metrics.all_metrics()],
        }


def registry() -> dict[str, tuple[type[BaseModel], object]]:
    """이름 → (인자 모델, 함수). `run_sql`은 랩 스위치가 켜졌을 때만 낀다."""
    table: dict[str, tuple[type[BaseModel], object]] = {
        "run_query": (RunQueryArgs, run_query),
        "lookup_metric": (LookupMetricArgs, lookup_metric),
    }
    if os.environ.get("ALLOW_RAW_SQL") == "1":
        table["run_sql"] = (RunSqlArgs, run_sql)
    return table


def tool_schemas() -> list[dict]:
    """모델에게 보여줄 도구 명세 — pydantic 모델에서 자동 생성한다."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": (model.__doc__ or "").strip(),
                "parameters": model.model_json_schema(),
            },
        }
        for name, (model, _fn) in registry().items()
    ]


def run_tool(name: str, raw_arguments: str) -> str:
    """도구 실행의 단일 관문: 검증 → 실행 → JSON 문자열.

    검증 실패도 예외를 올리지 않고 에러를 '결과'로 돌려준다. 모델이 그것을
    읽고 스스로 고치는 것이 tool calling의 복구 패턴이다 (5주차).
    """
    entry = registry().get(name)
    if entry is None:
        return json.dumps({"error": f"없는 도구: {name}"}, ensure_ascii=False)
    args_model, fn = entry
    try:
        args = args_model.model_validate(json.loads(raw_arguments or "{}"))
    except (ValidationError, json.JSONDecodeError) as e:
        return json.dumps({"error": f"인자 검증 실패: {e}"}, ensure_ascii=False)
    try:
        return json.dumps(fn(args), ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
