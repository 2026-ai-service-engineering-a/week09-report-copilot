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
    # 계획 1 + 섹션마다 (분석 1 + 작성 1) + 결론 1 + 라우팅 1
    assert final["usage"]["calls"] == 2 + len(sections) * 2


def test_sections_are_filled_with_real_numbers(needs_db):
    _, final, _ = collect("8월 국적별 관객수 보여줘")
    rows = final["report"]["sections"][-1]["rows"]
    assert rows and any(label == "미국" for label, _ in rows)


def test_budget_stop_is_reported_not_raised(needs_db):
    """예산 초과는 예외가 아니라 **상태**다. 화면이 말할 수 있어야 한다."""
    _, final, _ = collect("8월 리포트 만들어줘", simulate="budget", max_cost_usd=0.2)
    statuses = {s["status"] for s in final["report"]["sections"]}
    assert "stopped_by_budget" in statuses or "[중단]" in final["report"]["conclusion"]
