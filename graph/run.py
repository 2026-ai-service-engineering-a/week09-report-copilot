"""그래프를 돌리면서 이벤트를 흘린다 — 문이 부르는 단 하나의 진입점.

8주차 `core/service.py`의 `plan_events`와 같은 자리다. 문이 몇 개가 되든
부르는 것은 이 함수 하나이고, 나오는 것은 `graph/state.py`가 정의한 우리말
이벤트다. AG-UI로 옮기는 일은 문이 한다.

`stream(stream_mode="updates")`는 **노드 하나가 끝날 때마다** 그 노드가
돌려준 조각을 준다. 우리는 그 안의 `events`만 꺼내 순서대로 흘린다.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.harness import BudgetGuard
from graph.build import compiled
from graph.state import state_snapshot

DEFAULT_MAX_COST_USD = 0.20


def run(
    report: dict,
    text: str,
    *,
    thread_id: str = "default",
    ui_action: dict | None = None,
    selected: str | None = None,
    simulate: str | None = None,
    tool_result: dict | None = None,
    max_cost_usd: float = DEFAULT_MAX_COST_USD,
) -> Iterator[dict]:
    """요청 하나. 마지막 이벤트는 항상 `final` 하나다.

    `selected`가 이 랩의 핵심 인자다. 화면에서 무엇이 선택돼 있는지를 요청이
    실어 오기 때문에 "이거 빼줘"가 통한다. v1 챗 위젯에는 이 값이 없었다.
    """
    guard = BudgetGuard(warn_usd=max_cost_usd / 4, stop_usd=max_cost_usd)
    state = {
        "thread_id": thread_id,
        "report": report,
        "text": text,
        "ui_action": ui_action,
        "selected": selected,
        # 프런트엔드 도구의 답. 승인 카드를 누른 뒤의 두 번째 요청에 실려 온다
        "tool_result": tool_result,
        "simulate": simulate,
        "budget": guard,
        "replans": 0,
        "results": [],
        "events": [],
    }

    # 기준점을 먼저 맞춘다. 패치는 같은 문서를 보고 있어야 맞는 자리를 고친다
    yield state_snapshot(report)

    latest = report
    for update in compiled().stream(state, stream_mode="updates"):
        for node, delta in update.items():
            if not isinstance(delta, dict):
                continue
            for event in delta.get("events") or []:
                yield {**event, "node": node}
            if delta.get("report"):
                latest = delta["report"]

    yield {"event": "final", "report": latest, "usage": guard.snapshot()}
