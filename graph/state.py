"""그래프가 들고 다니는 것, 그리고 밖으로 내보내는 이벤트의 모양.

**그래프는 AG-UI를 모른다.** 여기서 만드는 이벤트는 우리말 딕셔너리이고,
그것을 AG-UI 이벤트로 옮기는 일은 문(`api/agui.py`)이 한다. 8주차에 코어가
HTTP를 모르고 `api/errors.py`가 상태 코드로 번역했던 것과 같은 자리다.

이 분리가 있어야 두 가지가 가능하다.

  · 그래프를 터미널에서 그냥 돌려 볼 수 있다 (`examples/03_loop_routes.py`)
  · AG-UI 규격이 바뀌어도 고칠 곳이 번역표 한 곳이다
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def step_started(name: str) -> dict:
    return {"event": "step_started", "name": name}


def step_finished(name: str) -> dict:
    return {"event": "step_finished", "name": name}


def text(content: str, *, final: bool = False) -> dict:
    """모델이 쓴 문장. 문이 토큰 이벤트 셋으로 펼친다."""
    return {"event": "text", "text": content, "final": final}


def tool_call(name: str, args: dict, result: str) -> dict:
    """도구 한 번. 문이 START·ARGS·END·RESULT 넷으로 펼친다."""
    return {"event": "tool_call", "tool": name, "args": args, "result": result}


def state_delta(ops: list[dict]) -> dict:
    """공유 상태의 변경. JSON Patch(RFC 6902) 연산 배열 그대로다."""
    return {"event": "state_delta", "delta": ops}


def state_snapshot(doc: dict) -> dict:
    return {"event": "state_snapshot", "snapshot": doc}


def guard(check: str, detail: str, *, stopped: bool = False) -> dict:
    """하네스가 무언가를 막았다. 막힌 것도 사용자에게 보여 준다."""
    return {"event": "guard", "check": check, "detail": detail, "stopped": stopped}


def ask(name: str, args: dict) -> dict:
    """사람에게 묻는다. 문이 프런트엔드 도구 호출로 옮기고 답을 기다린다."""
    return {"event": "ask", "tool": name, "args": args}


class ReportState(TypedDict, total=False):
    """그래프의 상태.

    `report`가 공유 상태 그 자체이고 나머지는 이번 실행에만 쓰는 작업 메모다.
    화면으로 건너가는 것은 `report`와 `events`뿐이다.
    """

    thread_id: str
    report: dict                 # 공유 상태 (core.schema.Report의 dump)
    text: str                    # 사용자가 친 한 줄
    ui_action: dict | None       # 화면 조작 (버튼·드래그). 있으면 모델을 안 부른다
    selected: str | None         # 화면에서 고른 섹션 id. **"이거"가 무엇인지가 여기 있다**
    route: str                   # apply · one · react · plan · publish · refresh
    period_changed: bool         # 기간이 바뀌었으면 있던 섹션도 낡는다
    plan: list[dict]             # 계획 노드가 만든 섹션 목록
    results: Annotated[list[dict], operator.add]   # 섹션별 결과 (병렬로 쌓인다)
    events: Annotated[list[dict], operator.add]    # 밖으로 내보낼 이벤트
    replans: int                 # 재계획 횟수. 한도는 숫자로 건다
    budget: Any                  # core.harness.BudgetGuard
    tool_result: dict | None     # 프런트엔드 도구가 돌려준 답 (승인 여부 등)
    simulate: str | None         # 랩 전용 스위치
