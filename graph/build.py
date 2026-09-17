"""그래프 조립 — 7주차에 배운 표기법 그대로다.

6주차에 for 루프로 손수 만든 제어 흐름을 LangGraph는 그래프로 선언한다.
모델 호출은 여전히 litellm이 한다(`core/llm.py`). 프레임워크가 대신해 주는
것은 **흐름의 표기**이지 호출이 아니다.

    route ─┬─ apply ──────────────────────────────────── END
           ├─ publish ── (승인 카드를 띄우고 끝낸다) ────── END
           ├─ one ───── section ─ collect ─ verify ───── END
           ├─ react ─── section ─ collect ─ verify ───── narrate ─ END
           └─ plan ──── section × N ─ collect ─ verify ─┬ narrate ─ END
                        (Send로 동시에)                 └ plan (재계획, 2회까지)

`Send`가 7주차 6장에서 본 그 물건이다. 계획이 태스크를 만들어 동시에 던진다.

**그래프는 뜰 때 한 번만 compile한다.** 요청마다 만들면 매번 준비를 다시
한다 (8주차 4장 4절).
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from graph.nodes import (
    MAX_REPLANS, apply_node, collect_node, narrate_node, plan_node,
    publish_node, react_plan_node, route_node, section_node, verify_node,
)
from graph.state import ReportState


def _after_route(state: ReportState) -> str:
    return {"apply": "apply", "plan": "plan", "react": "react",
            "one": "react", "publish": "publish"}.get(state.get("route") or "react", "react")


def _fan_out(state: ReportState):
    """계획을 태스크로 쪼개 동시에 던진다.

    섹션끼리 서로를 참조하지 않아 순서가 필요 없다. 하나도 없으면 바로
    모으기로 건너뛴다.
    """
    plan = state.get("plan") or []
    if not plan:
        return "collect"
    return [
        Send("section", {
            "section": section,
            "period": state["report"]["period"],
            "budget": state.get("budget"),
            "simulate": state.get("simulate"),
        })
        for section in plan
    ]


def _after_verify(state: ReportState) -> str:
    """불일치가 있으면 다시 계획한다. 단, **한도는 숫자로 건다.**

    2회까지 시도하고 그 뒤에는 "확인하지 못했습니다"를 답으로 알린다.
    6주차 budget guard와 같은 자리다.
    """
    unverified = any(s.get("status") == "unverified" for s in state["report"]["sections"])
    if unverified and (state.get("replans") or 0) <= MAX_REPLANS:
        return "plan"
    return "narrate"


def build():
    graph = StateGraph(ReportState)
    graph.add_node("route", route_node)
    graph.add_node("apply", apply_node)
    graph.add_node("plan", plan_node)
    graph.add_node("react", react_plan_node)
    graph.add_node("publish", publish_node)
    graph.add_node("section", section_node)
    graph.add_node("collect", collect_node)
    graph.add_node("verify", verify_node)
    graph.add_node("narrate", narrate_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", _after_route,
                                {"apply": "apply", "plan": "plan", "react": "react",
                                 "publish": "publish"})
    graph.add_edge("apply", END)
    graph.add_edge("publish", END)
    graph.add_conditional_edges("plan", _fan_out, ["section", "collect"])
    graph.add_conditional_edges("react", _fan_out, ["section", "collect"])
    graph.add_edge("section", "collect")
    graph.add_edge("collect", "verify")
    graph.add_conditional_edges("verify", _after_verify, {"plan": "plan", "narrate": "narrate"})
    graph.add_edge("narrate", END)
    return graph.compile()


@lru_cache(maxsize=1)
def compiled():
    """뜰 때 한 번. 요청마다 compile하지 않는다."""
    return build()
