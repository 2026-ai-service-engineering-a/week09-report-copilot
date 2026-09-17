"""도구 — 스키마가 막는 것과 게이트가 막는 것.

`run_query`는 애초에 막을 일이 생기지 않는다. 축이 enum이라 스키마에 없는
축으로는 인자가 만들어지지 않기 때문이다. `run_sql`은 반대로 게이트와 DB
권한 두 층이 지킨다 (교안 9장 1절).
"""

import json

import pytest

from core import tools


def test_group_axis_is_rejected_by_the_schema():
    """"감독별로 나눠줘"는 게이트가 아니라 **스키마**가 막는다."""
    out = json.loads(tools.run_tool("run_query", json.dumps(
        {"metric": "audi_cnt", "date_from": "2026-08-01",
         "date_to": "2026-08-31", "group_by": "director"})))
    assert "인자 검증 실패" in out["error"]


def test_uncomputable_metric_says_so(needs_db):
    """계산할 수 없는 지표는 비슷한 것으로 바꾸지 않고 그렇다고 말한다."""
    out = json.loads(tools.run_tool("run_query", json.dumps(
        {"metric": "seat_sales_rate", "date_from": "2026-08-01", "date_to": "2026-08-31"})))
    assert "계산할 수 없다" in out["error"]


def test_unknown_term_returns_the_catalog():
    """빈손으로 돌려보내면 모델이 지어낸다. 목록을 함께 준다."""
    out = json.loads(tools.run_tool("lookup_metric", json.dumps({"term": "흥행지수"})))
    assert out["available"], "고를 수 있는 지표 목록이 없다"


def test_run_query_gives_the_true_total(needs_db):
    """비율을 잘라 낸 목록으로 계산하지 않도록 전체 합을 함께 준다."""
    out = json.loads(tools.run_tool("run_query", json.dumps(
        {"metric": "audi_cnt", "date_from": "2026-08-01", "date_to": "2026-08-31",
         "group_by": "nation", "limit": 3})))
    assert len(out["rows"]) == 3
    assert out["total"] > sum(value for _, value in out["rows"])


def test_raw_sql_is_off_by_default():
    assert "run_sql" not in [t["function"]["name"] for t in tools.tool_schemas()]


def test_raw_sql_is_blocked_then_refused_by_the_database(monkeypatch, needs_db):
    """게이트를 통과해도 **쓰기 권한이 없어 실패한다.** 층이 둘이라는 증거다."""
    monkeypatch.setenv("ALLOW_RAW_SQL", "1")
    blocked = json.loads(tools.run_tool("run_sql", json.dumps({"sql": "DELETE FROM movie"})))
    assert blocked["blocked"] is True

    # 게이트가 못 잡는 모양으로 쓰기를 시도해도 DB가 막는다
    from core import db
    with pytest.raises(Exception):
        db.fetch("CREATE TEMP TABLE t AS SELECT 1")
