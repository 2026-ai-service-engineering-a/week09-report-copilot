"""그래프 — 요청마다 다른 경로가 돈다.

**모델 호출 수를 테스트로 박아 둔다.** 교안 7장의 표가 이 숫자이고, 누가
라우터에 손을 대 버튼 한 번에 모델을 부르게 만들면 여기서 깨진다.
"""

import pytest

from core.schema import empty_report
from graph.run import run


def collect(said, **kwargs):
    doc = kwargs.pop("doc", None) or empty_report().dump()
    events = list(run(doc, said, thread_id="test", **kwargs))
    final = next(e for e in events if e["event"] == "final")
    routes = [e["route"] for e in events if e["event"] == "route"]
    return events, final, routes[0] if routes else None


def test_ui_action_never_calls_the_model():
    """화면 조작에 모델을 부르면 돈과 지연을 둘 다 버린다."""
    _, final, route = collect("", ui_action={"type": "set_chart", "index": 0, "chart": "bar"})
    assert route == "apply"
    assert final["usage"]["calls"] == 0
    assert final["report"]["sections"][0]["chart"] == "bar"


def test_certain_phrases_are_caught_by_code():
    _, final, route = collect("막대로 바꿔줘", selected="s1")
    assert (route, final["usage"]["calls"]) == ("apply", 0)


def test_pronoun_works_when_the_request_carries_the_selection():
    """v2가 v1과 갈리는 자리. 선택이 실려 오면 "이거"가 무엇인지 안다."""
    events, final, _ = collect("이거 빼줘", selected="s2")
    deltas = [e for e in events if e["event"] == "state_delta"]
    assert deltas[0]["delta"] == [{"op": "remove", "path": "/sections/1"}]
    assert [s["id"] for s in final["report"]["sections"]] == ["s1"]


def test_pronoun_fails_without_the_selection():
    """같은 한마디, 선택이 없으면 되묻는다. **v1이 무너지는 그 자리다.**"""
    events, final, _ = collect("이거 빼줘", selected=None)
    assert not [e for e in events if e["event"] == "state_delta"]
    assert len(final["report"]["sections"]) == 2


def test_report_request_plans_and_fans_out(needs_db):
    events, final, route = collect("8월 박스오피스 리포트 국적별로 만들어줘")
    assert route == "plan"
    sections = final["report"]["sections"]
    assert 3 <= len(sections) <= 5
    assert all(s["rows"] for s in sections), "섹션이 비어 있다"
    assert final["report"]["conclusion"]
    # 라우팅 1 + 계획 1 + 섹션마다 작성 1 + 결론 1.
    # **분석가는 happy path에 없다.** 질의 스펙이 이미 정해져 있으므로 도구를
    # 직접 부르고, 모델은 실패했을 때만 낀다 (graph/nodes.py section_node)
    assert final["usage"]["calls"] == 3 + len(sections)


def test_sections_are_filled_with_real_numbers(needs_db):
    _, final, _ = collect("8월 국적별 관객수 보여줘")
    rows = final["report"]["sections"][-1]["rows"]
    assert rows and any(label == "미국" for label, _ in rows)


def test_budget_stop_is_reported_not_raised(needs_db):
    """예산 초과는 예외가 아니라 **상태**다. 화면이 말할 수 있어야 한다.

    멈추는 자리는 둘이다. 라우터의 첫 호출에서 이미 넘으면 문 앞에서 끊고,
    섹션을 돌다 넘으면 그 섹션에 배지가 남는다. **어느 쪽이든 500으로 터지지
    않고 사용자에게 무슨 일이 났는지 말해야 한다.**
    """
    events, final, _ = collect("8월 리포트 만들어줘", simulate="budget", max_cost_usd=0.2)

    guards = [e for e in events if e["event"] == "guard" and e["check"] == "budget"]
    assert guards and guards[0]["stopped"] is True, "예산 초과를 알리지 않았다"

    told = [e["text"] for e in events if e["event"] == "text"]
    statuses = {s["status"] for s in final["report"]["sections"]}
    assert any("중단" in t for t in told) or "stopped_by_budget" in statuses


def test_publish_asks_before_doing():
    """되돌리기 어려운 행동 앞에는 카드가 선다. **묻기만 하고 실행을 끝낸다.**"""
    events, final, route = collect("이 리포트 발행해줘")
    asks = [e for e in events if e["event"] == "ask"]
    assert route == "publish"
    assert asks and asks[0]["tool"] == "confirm_publish"
    assert final["report"]["publishedAt"] is None, "묻기만 해야 하는데 발행됐다"
    assert final["usage"]["calls"] == 0, "되돌리기 어려운 행동을 모델 해석에 맡기지 않는다"


def test_approval_comes_back_as_a_second_request():
    """프런트엔드 도구는 루프를 멈춰 기다리지 않는다. 두 번 돈다."""
    _, final, route = collect("", tool_result={"name": "confirm_publish", "value": "approved"})
    assert route == "publish"
    assert final["report"]["publishedAt"], "승인했는데 발행되지 않았다"


def test_rejection_is_a_result_not_an_error():
    """거절도 결과다. 예외로 처리하면 사용자는 무슨 일이 났는지 모른다."""
    events, final, _ = collect("", tool_result={"name": "confirm_publish", "value": "rejected"})
    replies = [e["text"] for e in events if e["event"] == "text"]
    assert final["report"]["publishedAt"] is None
    assert replies and "발행하지 않았습니다" in replies[0]


def test_period_is_parsed_by_code_not_the_model(needs_db):
    """"2026년 1월부터"를 읽는 것은 코드다. 날짜를 틀리면 리포트 전체가 틀린다."""
    events, final, route = collect("2026년도 전체 1월부터 월별 관객수를 보여줘")
    assert final["report"]["period"] == {"from": "2026-01-01", "to": "2026-08-31"}
    # 없는 구간을 요청했으므로 잘랐다고 알려 줘야 한다
    assert any(e["event"] == "guard" and e["check"] == "period" for e in events)
    month = [s for s in final["report"]["sections"] if s["groupBy"] == "month"]
    assert month and len(month[0]["rows"]) == 8


def test_period_only_request_refreshes_instead_of_adding(needs_db):
    """기간만 바꾼 요청에 섹션을 새로 만들면 같은 그림이 두 장이 된다."""
    doc = empty_report().dump()
    _, first, _ = collect("월별 관객수 보여줘", doc=doc)
    _, second, route = collect("3월부터 6월까지", doc=first["report"])
    assert route == "refresh"
    assert len(second["report"]["sections"]) == len(first["report"]["sections"])


def test_axis_retunes_when_the_period_grows(needs_db):
    """한 달짜리 일별 차트를 1년으로 늘리면 점이 365개가 된다."""
    doc = empty_report().dump()
    assert doc["sections"][0]["groupBy"] is None          # 처음에는 일자별
    _, final, _ = collect("2026년 1월부터 보여줘", doc=doc)
    assert final["report"]["sections"][0]["groupBy"] == "month"
    assert final["report"]["sections"][0]["title"] == "월별 관객수"


def test_the_same_chart_is_not_drawn_twice(needs_db):
    doc = empty_report().dump()
    _, first, _ = collect("국적별로 보여줘", doc=doc)
    _, second, _ = collect("국적별 관객수 보여줘", doc=first["report"])
    axes = [s["groupBy"] for s in second["report"]["sections"]]
    assert axes.count("nation") == 1


def test_phrase_rules_live_in_one_place(needs_db):
    """라우터와 노드가 **같은 규칙**을 본다.

    두 벌이었다가 한쪽만 고쳐 "막대 그래프로 해줘"가 분류 호출로 샜다.
    같은 말이 라우터에서 apply로 잡히고 노드에서도 같은 뜻으로 읽혀야 한다.
    """
    from graph import phrases

    for said in ("막대 그래프로 해줘", "막대로 바꿔줘", "파이 차트로", "선 그래프로"):
        assert phrases.chart_word(said), f"노드가 못 읽는다: {said}"
        assert phrases.edits_selection(said), f"라우터가 못 잡는다: {said}"


@pytest.mark.parametrize("said,expected", [
    ("막대 그래프로 해줘", "bar"),
    ("파이로 해줘", "pie"),
    ("선 그래프로 바꿔줘", "line"),
])
def test_chart_change_costs_nothing(said, expected, needs_db):
    doc = empty_report().dump()
    _, final, route = collect(said, doc=doc, selected="s1")
    assert (route, final["usage"]["calls"]) == ("apply", 0)
    assert final["report"]["sections"][0]["chart"] == expected


def test_retarget_changes_the_axis_of_the_selected_section(needs_db):
    """"요일별로 바꿔줘" — 새로 만들지 않고 고른 섹션을 고친다."""
    doc = empty_report().dump()
    _, first, _ = collect("2026년 1월부터 월별 관객수 보여줘", doc=doc)
    before = len(first["report"]["sections"])

    _, final, route = collect("요일별로 바꿔줘", doc=first["report"], selected="s1")
    section = final["report"]["sections"][0]
    assert route == "retarget"
    assert len(final["report"]["sections"]) == before, "섹션이 늘었다"
    assert section["groupBy"] == "weekday"
    assert section["title"] == "요일별 관객수"
    assert len(section["rows"]) == 7, "축을 바꿨으면 숫자도 다시 가져와야 한다"


def test_the_router_call_is_on_the_ledger(needs_db):
    """**장부에 안 잡히는 호출이 하나라도 있으면 예산 게이트는 반쪽이다.**"""
    doc = empty_report().dump()
    _, final, route = collect("국적별 관객수 보여줘", doc=doc)
    assert route == "react"
    # 라우팅 1 + 작성 1 + 결론 1. 라우터의 호출이 빠지면 2가 된다
    assert final["usage"]["calls"] == 3
