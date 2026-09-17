"""그래프의 노드들 — 7주차의 역할 분리가 여기 있다.

분석가·작성가·검증자를 나눈 이유는 셋째에 있다. **쓴 사람이 자기 글을
검증하면 놓친다.** 3주차 5장의 크로스체크 원칙이고, 그래서 검증자는 작성자의
문장이 아니라 **분석가의 원본 숫자**를 본다.

모든 노드는 두 가지를 돌려준다.

  · 상태 조각 (`report`·`plan`·`results`…)
  · `events` — 밖으로 흘려보낼 우리말 이벤트 (`graph/state.py`)

노드는 AG-UI를 모른다. 번역은 문이 한다.
"""

from __future__ import annotations

import json

from core import config, metrics, patch, schema, tools
from core.harness import BudgetExceeded, scan_injection, wrap_untrusted
from core.llm import completion
from core.prompts import ANALYST, NARRATOR, PLANNER, VERIFIER, WRITER
from graph import router
from graph.state import (
    ReportState, state_delta, step_finished, step_started, text, tool_call,
)
from graph.state import guard as guard_event

MAX_REPLANS = 2      # 한도는 숫자로 건다. 넘으면 답으로 알린다 (6주차)


def _ask_model(state: ReportState, system: str, user: str, *, tools_on: bool = False):
    """모델 한 번. 예산 장부에 더하는 것도 여기 한 곳이다."""
    response = completion(
        model=config.pick_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **({"tools": tools.tool_schemas()} if tools_on else {}),
        simulate=state.get("simulate"),
    )
    budget = state.get("budget")
    if budget:
        budget.add_response(response)
    return response


# ── 라우터 ────────────────────────────────────────────────────────────


def route_node(state: ReportState) -> dict:
    chosen, calls = router.route(state)
    return {
        "route": chosen,
        "events": [
            step_started("route"),
            {"event": "route", "route": chosen, "llm_calls": calls},
            step_finished("route"),
        ],
    }


# ── apply: 모델을 부르지 않는 길 ──────────────────────────────────────

_CHART_WORDS = {"막대": "bar", "바": "bar", "bar": "bar",
                "선": "line", "라인": "line", "line": "line",
                "파이": "pie", "원": "pie", "pie": "pie"}


def _selected_index(state: ReportState) -> int | None:
    """화면에서 무엇이 선택돼 있는지. **이 한 줄이 v1과 v2를 가른다.**

    v1 챗 위젯에는 이 정보가 아예 오지 않았다. 그래서 "이거 빼줘"에
    되물을 수밖에 없었다. 여기서는 요청이 상태를 싣고 오므로 안다.
    """
    selected = state.get("selected")
    if not selected:
        return None
    sections = state["report"]["sections"]
    for index, section in enumerate(sections):
        if section["id"] == selected:
            return index
    return None


def apply_node(state: ReportState) -> dict:
    """화면 조작과 확실한 한마디를 패치로 옮긴다. 모델 호출 0회."""
    action = state.get("ui_action") or {}
    said = state.get("text") or ""
    index = _selected_index(state)
    ops: list[dict] = []

    if action.get("type") == "set_chart":
        ops = [patch.replace(f"/sections/{action['index']}/chart", action["chart"])]
    elif action.get("type") == "move_section":
        ops = [patch.move(f"/sections/{action['from']}", f"/sections/{action['to']}")]
    elif action.get("type") == "remove_section":
        ops = [patch.remove(f"/sections/{action['index']}")]
    elif action.get("type") == "set_filter":
        ops = [patch.replace(f"/filters/{action['field']}", action["value"])]
    elif index is not None:
        kind = next((v for k, v in _CHART_WORDS.items() if f"{k}로" in said or f"{k} 차트" in said), None)
        if kind:
            ops = [patch.replace(f"/sections/{index}/chart", kind)]
        elif any(word in said for word in ("빼", "지워", "삭제")):
            ops = [patch.remove(f"/sections/{index}")]
        elif "위로" in said:
            ops = [patch.move(f"/sections/{index}", "/sections/0")]

    if not ops:
        return {"events": [text("무엇을 바꿀지 알기 어렵습니다. 섹션을 고르고 다시 말씀해 주세요.",
                                final=True)]}

    report = patch.apply(dict(state["report"]), ops)
    return {"report": report, "events": [state_delta(ops)]}


# ── 계획 ──────────────────────────────────────────────────────────────


def plan_node(state: ReportState) -> dict:
    """무엇을 만들지 먼저 정하고 **화면에 얹는다.**

    계획이 상태에 들어가는 순간 사용자가 볼 수 있고, 비싼 실행 전에 고칠 수
    있다. ReAct는 다 끝나야 전모가 보인다 (교안 7장 3절).
    """
    period = state["report"]["period"]
    prompt = f"{state.get('text') or ''}\n기간: {period['from']} ~ {period['to']}"
    try:
        response = _ask_model(state, PLANNER, prompt)
    except BudgetExceeded as e:
        return {"plan": [], "events": [guard_event("budget", str(e), stopped=True)]}

    raw = (response.choices[0].message.content or "[]").strip()
    try:
        sections = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        sections = []

    # **리포트를 새로 만들라는 요청이므로 섹션 목록을 갈아 끼운다.**
    # 붙이기만 하면 옛 섹션이 빈 채로 남아 사용자가 무엇이 새것인지 모른다.
    # 섹션 하나를 더하는 것은 react 쪽(`react_plan_node`)의 일이다
    plan: list[dict] = []
    for index, spec in enumerate(sections[:5], start=1):
        plan.append(schema.Section(
            id=f"s{index}",
            kind=spec.get("kind", "chart"),
            title=spec.get("title", "제목 없음"),
            metric=spec.get("metric", "audi_cnt"),
            chart=spec.get("chart"),
            group_by=spec.get("groupBy"),
            status="pending",
        ).model_dump(mode="json", by_alias=True))

    ops = [patch.replace("/sections", plan)]
    report = patch.apply(dict(state["report"]), ops)
    return {
        "report": report, "plan": plan, "results": [],
        "events": [step_started("plan"), state_delta(ops), step_finished("plan")],
    }


# ── 섹션 하나 (병렬로 돈다) ───────────────────────────────────────────


def section_node(state: dict) -> dict:
    """분석가가 숫자를 가져오고 작성가가 한 문장을 쓴다.

    섹션끼리 서로를 참조하지 않으므로 순서대로 돌 이유가 없다. 7주차
    코딩 에이전트와 달리 **파일을 만지지 않아 worktree도 필요 없다.**
    병렬화는 모델의 문제가 아니라 작업 공간의 문제다.
    """
    section = state["section"]
    period = state["period"]
    events: list[dict] = [step_started(f"section:{section['id']}")]

    spec = {
        "metric": section["metric"], "date_from": period["from"], "date_to": period["to"],
        "group_by": section.get("groupBy"), "limit": section.get("limit", 10),
    }
    try:
        response = _ask_model(state, ANALYST, json.dumps(spec, ensure_ascii=False), tools_on=True)
    except BudgetExceeded as e:
        events.append(guard_event("budget", str(e), stopped=True))
        return {"results": [{"id": section["id"], "status": "stopped_by_budget",
                             "rows": [], "note": f"[중단] {e}"}], "events": events}

    calls = getattr(response.choices[0].message, "tool_calls", None) or []
    observation, rows, total = "", [], None
    for call in calls:
        observation = tools.run_tool(call.function.name, call.function.arguments)
        events.append(tool_call(call.function.name, json.loads(call.function.arguments or "{}"),
                                observation))
        parsed = json.loads(observation)
        rows = parsed.get("rows") or rows
        total = parsed.get("total", total)

    findings = scan_injection(observation)
    if findings:
        events.append(guard_event("injection_scan", ", ".join(findings)))

    try:
        written = _ask_model(
            state, WRITER,
            f"{section['title']}\n"
            + wrap_untrusted("run_query", observation or "{}"),
        )
        note = written.choices[0].message.content or ""
    except BudgetExceeded as e:
        events.append(guard_event("budget", str(e), stopped=True))
        note = f"[중단] {e}"

    events.append(step_finished(f"section:{section['id']}"))
    return {
        "results": [{"id": section["id"], "status": "ok", "rows": rows,
                     "total": total, "note": note}],
        "events": events,
    }


# ── 모으기 · 검증 · 결론 ──────────────────────────────────────────────


def collect_node(state: ReportState) -> dict:
    """섹션 결과를 문서에 얹는다. 패치 한 묶음으로 나간다."""
    report = dict(state["report"])
    by_id = {r["id"]: r for r in state.get("results") or []}
    ops: list[dict] = []
    for index, section in enumerate(report["sections"]):
        result = by_id.get(section["id"])
        if not result:
            continue
        ops += [
            patch.replace(f"/sections/{index}/rows", result["rows"]),
            patch.replace(f"/sections/{index}/note", result["note"]),
            patch.replace(f"/sections/{index}/status", result["status"]),
        ]
    if not ops:
        return {"events": []}
    report = patch.apply(report, ops)
    return {"report": report, "events": [state_delta(ops)]}


def _numbers(text_: str) -> set[int]:
    """문장에 박힌 수를 뽑는다. 천 단위 쉼표를 걷어 낸다."""
    import re

    return {int(t.replace(",", "")) for t in re.findall(r"\d[\d,]{2,}", text_ or "")}


def verify_node(state: ReportState) -> dict:
    """검증자는 **분석가의 원본 숫자**를 본다. 작성자의 요약을 보면 같이 틀린다.

    판정은 코드가 한다. 문장에 있는 수가 집계 결과에도 있는지를 대조할 뿐이라
    모델이 설득당할 여지가 없다. 이것이 인젝션에 대한 마지막 방어선이다
    (교안 9장 2절).
    """
    events: list[dict] = [step_started("verify")]
    report = dict(state["report"])
    mismatched: list[str] = []
    ops: list[dict] = []

    for index, section in enumerate(report["sections"]):
        claimed = _numbers(section.get("note") or "")
        if not claimed:
            continue
        rows = section.get("rows") or []
        actual = {int(round(value)) for _, value in rows if isinstance(value, (int, float))}
        # 라벨에 박힌 수도 집계에서 온 것이다. 일자별 차트의 `2026-08-01`이
        # 그렇다. 값만 보고 대조하면 연도가 "집계에 없는 수치"로 잡힌다
        for label, _ in rows:
            actual |= _numbers(str(label))
        # 비율(0~100)은 총합에서 나온 것이라 행 값에 없다. 대조 대상에서 뺀다
        stray = {n for n in claimed if n > 100} - actual
        if stray:
            mismatched.append(section["id"])
            ops.append(patch.replace(f"/sections/{index}/status", "unverified"))
            events.append(guard_event(
                "verify", f"{section['id']}: 집계에 없는 수치 {sorted(stray)[:3]}"))

    if ops:
        report = patch.apply(report, ops)
        events.append(state_delta(ops))
    events.append(step_finished("verify"))
    return {"report": report, "events": events,
            "replans": (state.get("replans") or 0) + (1 if mismatched else 0)}


def narrate_node(state: ReportState) -> dict:
    """결론 한 문단. 확인하지 못한 섹션이 있으면 그 사실을 함께 적는다."""
    report = dict(state["report"])
    notes = "\n".join(f"- {s['title']}: {s.get('note') or ''}" for s in report["sections"])
    unverified = [s["id"] for s in report["sections"] if s.get("status") == "unverified"]
    try:
        response = _ask_model(state, NARRATOR, notes)
        conclusion = response.choices[0].message.content or ""
    except BudgetExceeded as e:
        conclusion = f"[중단] {e}"
    if unverified:
        conclusion += f" (확인하지 못한 섹션: {', '.join(unverified)})"

    ops = [patch.replace("/conclusion", conclusion)]
    report = patch.apply(report, ops)
    return {
        "report": report,
        "events": [step_started("narrate"), state_delta(ops),
                   text(conclusion, final=True), step_finished("narrate")],
    }


# ── react: 한 섹션만 만드는 짧은 길 ───────────────────────────────────


def react_plan_node(state: ReportState) -> dict:
    """조회 한 번이면 끝나는 요청. 계획 없이 섹션 하나를 세운다."""
    said = state.get("text") or ""
    try:
        metric = metrics.lookup(said).id
    except Exception:
        metric = "audi_cnt"
    axis = None
    for key, words in (("nation", ("국적", "나라")), ("genre", ("장르",)),
                       ("distributor", ("배급",)), ("movieNm", ("영화", "상위", "순위"))):
        if any(word in said for word in words):
            axis = key
            break

    report = dict(state["report"])
    section = schema.Section(
        id=schema.next_section_id(schema.Report.model_validate(report)),
        kind="table" if axis == "movieNm" else "chart",
        chart=None if axis == "movieNm" else "bar",
        title=said[:40] or "조회 결과", metric=metric, group_by=axis, status="pending",
    ).model_dump(mode="json", by_alias=True)
    ops = [patch.add("/sections/-", section)]
    report = patch.apply(report, ops)
    return {"report": report, "plan": [section],
            "events": [state_delta(ops)]}
