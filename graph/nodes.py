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

import datetime as dt
import json

from core import config, daterange, metrics, patch, schema, tools
from core.harness import BudgetExceeded, scan_injection, strip_boundary, wrap_untrusted
from core.llm import completion
from core.prompts import ANALYST, NARRATOR, PLANNER, VERIFIER, WRITER
from graph import router
from graph.state import (
    ReportState, ask, state_delta, step_finished, step_started, text, tool_call,
)
from graph.state import guard as guard_event

MAX_REPLANS = 2      # 한도는 숫자로 건다. 넘으면 답으로 알린다 (6주차)

GROUP_AXES = frozenset(getattr(schema.GroupBy, "__args__", ()))


def _report_title(start: dt.date, end: dt.date) -> str:
    """문서 제목을 기간에서 만든다."""
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.year}년 {start.month:02d}월 박스오피스 리포트"
    if start.year == end.year:
        return f"{start.year}년 {start.month}~{end.month}월 박스오피스 리포트"
    return f"{start} ~ {end} 박스오피스 리포트"


def _chart_for(said: str | None, axis: str | None, kind: str | None) -> str | None:
    if kind == "table":
        return None
    if axis in (None, "month", "week"):
        return "line"
    return said if said in ("bar", "pie") else "bar"


def _known_metric(said: str | None) -> str:
    """모델이 넘긴 지표 이름을 우리 id로 옮긴다. 못 옮기면 기본값.

    `audiCnt`처럼 표기만 다른 것은 `metrics.lookup`이 흡수하고, 아예 없는
    것이면 조용히 기본 지표로 떨어뜨린다. 여기서 예외를 올리면 리포트 한
    장이 통째로 날아가는데, 섹션 하나가 기본 지표로 그려지는 편이 낫다.
    """
    try:
        return metrics.lookup(said or "").id
    except Exception:
        return "audi_cnt"


def _asks_metric(said: str) -> bool:
    """지표를 말했는가. 기간만 바꾼 요청과 새 섹션 요청을 가른다."""
    try:
        metrics.lookup(said)
        return True
    except Exception:
        return any(word in said for word in ("리포트", "보고서", "차트", "표", "섹션"))


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
    """무엇을 할지 고르기 전에 **언제를 볼지부터 정한다.**

    "2026년 1월부터"를 읽어 기간을 고치는 일은 코드가 한다. 표현의 가짓수가
    정해져 있고 뜻이 하나뿐이라 모델에게 물을 이유가 없고, 무엇보다 날짜를
    틀리면 리포트 전체가 틀린다 (`core/daterange.py`).

    그리고 이 패치가 **화면 위쪽 칩을 바꿉니다.** 공유 상태가 눈에 보이는
    가장 흔한 순간이 이것이다.
    """
    events: list[dict] = [step_started("route")]
    report = dict(state["report"])
    period = report["period"]

    changed = False
    found = daterange.parse(state.get("text") or "", current=(period["from"], period["to"]))
    if found:
        start, end, cut = found
        if (str(start), str(end)) != (period["from"], period["to"]):
            ops = [patch.replace("/period/from", str(start)),
                   patch.replace("/period/to", str(end)),
                   # **제목도 기간의 일부다.** 8월 리포트를 1~8월로 늘려 놓고
                   # 제목만 "2026년 08월"로 두면 문서가 스스로 거짓말을 한다
                   patch.replace("/title", _report_title(start, end))]
            report = patch.apply(report, ops)
            events.append(state_delta(ops))
            changed = True
            if cut:
                # 잘렸으면 잘렸다고 말한다. 조용히 자르면 사용자는 없는 구간이
                # 0이라고 오해한다
                events.append(guard_event("period", daterange.describe(start, end, cut=True)))

    chosen, calls = router.route({**state, "report": report})
    # **기간이 바뀌면 문서 전체가 낡는다.** 다른 할 일이 없으면 다시 채우는
    # 것이 할 일이다. 절반은 1월, 절반은 8월인 리포트를 내놓지 않는다
    # 기간 말고는 아무것도 말하지 않았으면 다시 채우기만 한다. 축도 지표도
    # 말하지 않았는데 섹션을 새로 만들면 같은 그림이 두 장이 된다
    only_period = changed and not said_axis(state.get("text") or "") and not _asks_metric(
        state.get("text") or "")
    if changed and (chosen == "apply" or only_period) and not state.get("ui_action"):
        chosen = "refresh"
    events += [{"event": "route", "route": chosen, "llm_calls": calls}, step_finished("route")]
    return {"route": chosen, "report": report, "period_changed": changed, "events": events}


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
        # 모델이 무엇을 빼먹어도 문서는 성립해야 한다. **제목을 못 받으면
        # 지표와 축에서 만든다.** 진짜 모델을 붙이자 "제목 없음"이 세 줄
        # 늘어섰다. 빠진 값을 메우는 자리는 스키마 바로 뒤가 맞다
        metric = _known_metric(spec.get("metric"))
        axis = spec.get("groupBy") if spec.get("groupBy") in GROUP_AXES else None
        plan.append(schema.Section(
            id=f"s{index}",
            kind=spec.get("kind") if spec.get("kind") in ("chart", "table") else "chart",
            title=(spec.get("title") or "").strip() or _title(metric, axis),
            metric=metric,
            # 시간 축에는 선이 맞는다. 추세를 보려고 만든 축인데 막대로
            # 그리면 앞뒤 관계가 보이지 않는다. 모델이 bar를 골라도 고친다
            chart=_chart_for(spec.get("chart"), axis, spec.get("kind")),
            group_by=axis,
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
    observation, rows, total, failed = "", [], None, None
    for call in calls:
        observation = tools.run_tool(call.function.name, call.function.arguments)
        events.append(tool_call(call.function.name, json.loads(call.function.arguments or "{}"),
                                observation))
        parsed = json.loads(observation)
        rows = parsed.get("rows") or rows
        total = parsed.get("total", total)
        failed = parsed.get("error") or failed

    if failed or not rows:
        # **조회가 실패하면 작성가를 부르지 않는다.** 부르면 오류 문자열을
        # 문장으로 옮겨 적고, 그 문장이 리포트 본문이 된다. 모델 호출도
        # 한 번 아낀다
        events.append(step_finished(f"section:{section['id']}"))
        return {"results": [{"id": section["id"], "status": "unverified", "rows": [],
                             "total": None,
                             "note": f"이 구간의 값을 가져오지 못했습니다: {failed or '결과 없음'}"}],
                "events": events}

    findings = scan_injection(observation)
    if findings:
        events.append(guard_event("injection_scan", ", ".join(findings)))

    try:
        written = _ask_model(
            state, WRITER,
            f"{section['title']}\n"
            + wrap_untrusted("run_query", observation or "{}"),
        )
        # 경계 마커는 모델에게 주는 표시다. 따라 적은 것을 그대로 두면
        # 리포트 본문에 `<<<DATA …>>>`가 실려 나간다
        note = strip_boundary(written.choices[0].message.content or "")
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
            patch.replace(f"/sections/{index}/total", result.get("total")),
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
        rows = section.get("rows") or []
        # **대조할 것이 없으면 판정하지 않는다.** 행이 비어 있으면 문장 속
        # 모든 수가 "집계에 없는 수치"가 되고, 실패한 섹션 다섯 개가 전부
        # 불일치로 잡혀 재계획을 두 번 더 돌았다
        if not rows or section.get("status") != "ok":
            continue
        claimed = _numbers(section.get("note") or "")
        if not claimed:
            continue
        actual = {int(round(value)) for _, value in rows if isinstance(value, (int, float))}
        # 라벨에 박힌 수도 집계에서 온 것이다. 일자별 차트의 `2026-08-01`이
        # 그렇다. 값만 보고 대조하면 연도가 "집계에 없는 수치"로 잡힌다
        for label, _ in rows:
            actual |= _numbers(str(label))
        # **총합도 집계에서 온 값이다.** 도구가 `total`로 함께 주고 작성가가
        # 그것으로 비율을 계산한다. 행에만 있는 수로 대조하면 "전체 관객
        # 86,977,809명"이 통째로 집계에 없는 수치가 된다
        if section.get("total"):
            actual.add(int(round(section["total"])))
        # 행 값들의 합도 정당하다. 작성가가 직접 더했을 수 있다
        actual.add(sum(int(round(v)) for _, v in rows if isinstance(v, (int, float))))
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
        conclusion = strip_boundary(response.choices[0].message.content or "")
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

_AXIS_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("month", ("월별", "달별", "월간")),
    ("week", ("주별", "주간", "주차별")),
    ("weekday", ("요일", "요일별")),
    ("nation", ("국적", "나라", "국가")),
    ("genre", ("장르",)),
    ("distributor", ("배급",)),
    ("watchGrade", ("등급",)),
    ("movieType", ("영화구분", "예술영화", "독립영화")),
    ("movieNm", ("영화별", "작품별", "상위", "순위", "톱")),
]


def said_axis(said: str) -> str | None:
    """말에 **명시된** 축만 돌려준다. 없으면 None."""
    for axis, words in _AXIS_WORDS:
        if any(word in said for word in words):
            return axis
    return axis_for_span(said) if False else None


def _span_days(period: dict) -> int:
    try:
        return (dt.date.fromisoformat(period["to"]) - dt.date.fromisoformat(period["from"])).days
    except (ValueError, KeyError):
        return 0


def axis_for_span(period: dict) -> str | None:
    """기간을 보고 시간 축을 고른다.

    한 달이면 일자별이 읽히지만 1년치를 일자별로 그리면 점이 365개라 아무것도
    안 보인다. 사용자가 축을 말하지 않았다고 해서 읽을 수 없는 그림을 내놓는
    것은 도움이 아니다.
    """
    span = _span_days(period)
    if span > 180:
        return "month"
    if span > 45:
        return "week"
    return None


def _axis_of(said: str, period: dict) -> str | None:
    return said_axis(said) or axis_for_span(period)


def retune(section: dict, period: dict) -> dict | None:
    """기간이 바뀐 뒤 섹션의 시간 축을 다시 고른다.

    한 달짜리 리포트에서 만든 일자별 차트를 1년으로 늘리면 점이 365개가 된다.
    **범주 축(국적·장르 같은 것)은 건드리지 않는다.** 기간이 바뀌어도 나누는
    기준이 달라질 이유가 없기 때문이다.
    """
    if section.get("groupBy") not in (None, "month", "week"):
        return None
    wanted = axis_for_span(period)
    if wanted == section.get("groupBy"):
        return None
    return {**section, "groupBy": wanted,
            "title": _title(section["metric"], wanted)}


def _title(metric_id: str, axis: str | None) -> str:
    """제목은 지표와 축에서 만든다. **사용자가 친 문장을 그대로 쓰지 않는다.**

    "2026년도 전체 1월부터 월별 관객수를 보여줘"가 섹션 제목이 되면 문서가
    아니라 대화 기록이 된다.
    """
    try:
        name = metrics.by_id(metric_id).name
    except Exception:
        name = metric_id
    label = {"month": "월별", "week": "주별", "weekday": "요일별", "nation": "국적별",
             "genre": "장르별", "movieType": "구분별", "watchGrade": "등급별",
             "distributor": "배급사별", "movieNm": "영화별"}.get(axis or "", "일별")
    return f"{label} {name}"


def react_plan_node(state: ReportState) -> dict:
    """조회 한 번이면 끝나는 요청. 계획 없이 섹션 하나를 세운다."""
    said = state.get("text") or ""
    try:
        metric = metrics.lookup(said).id
    except Exception:
        metric = "audi_cnt"
    axis = _axis_of(said, state["report"]["period"])
    report = dict(state["report"])
    retuned: list[list[dict]] = []
    # 기간이 바뀌었으면 이미 있던 섹션도 낡았다. 새 섹션과 함께 다시 채운다
    stale = []
    if state.get("period_changed"):
        for index, old in enumerate(report["sections"]):
            tuned = retune(old, report["period"])
            if tuned:
                ops = [patch.replace(f"/sections/{index}/groupBy", tuned["groupBy"]),
                       patch.replace(f"/sections/{index}/title", tuned["title"])]
                report = patch.apply(report, ops)
                retuned.append(ops)
            stale.append(report["sections"][index])
    section = schema.Section(
        id=schema.next_section_id(schema.Report.model_validate(report)),
        kind="table" if axis == "movieNm" else "chart",
        chart=None if axis == "movieNm" else ("line" if axis in ("month", "week", None) else "bar"),
        title=_title(metric, axis), metric=metric, group_by=axis, status="pending",
    ).model_dump(mode="json", by_alias=True)
    # **같은 것을 두 번 그리지 않는다.** 지표와 축이 같으면 이미 있는 섹션이고,
    # 기간이 바뀌어 다시 채우는 중이라면 그것으로 충분하다. 이 확인이 없으면
    # "월별 관객수"가 두 장 생긴다
    twin = next((sec for sec in report["sections"]
                 if sec["metric"] == metric and sec.get("groupBy") == axis), None)
    if twin:
        plan = stale or [twin]
        if twin not in plan:
            plan = plan + [twin]
        return {"report": report, "plan": plan, "results": [],
                "events": [state_delta(sum(retuned, []))] if retuned else []}

    ops = [patch.add("/sections/-", section)]
    report = patch.apply(report, ops)
    return {"report": report, "plan": stale + [section], "results": [],
            "events": [state_delta(sum(retuned, []) + ops)]}


# ── 발행: 되돌리기 어려운 행동 앞의 승인 카드 ────────────────────────


def publish_node(state: ReportState) -> dict:
    """공유 링크를 만들기 전에 **사람에게 묻는다.**

    6주차에 터미널에서 `y/n`을 받던 승인 게이트이고, 7주차 코딩 에이전트에서
    비용을 보여 주고 물었던 그 자리다. 오늘 그것이 화면의 카드가 된다.

    승인을 묻는 방식이 AG-UI에서는 이렇다. 에이전트가 **프런트엔드 도구**를
    부르고 실행을 끝낸다. 화면이 카드를 띄우고, 사용자가 누르면 그 답을 실은
    **새 요청**이 온다. 루프가 멈춰 기다리는 것이 아니라 두 번 도는 것이다.

    묻는 이유는 둘뿐이어야 한다. 되돌리기 어렵거나 돈이 나가거나. 이유 없이
    묻기 시작하면 사용자는 읽지 않고 누르게 되고, 그러면 게이트가 없는 것과
    같아진다 (교안 6장 3절).
    """
    answer = state.get("tool_result") or {}
    report = dict(state["report"])
    sections = report["sections"]

    if answer.get("name") != "confirm_publish":
        # 아직 안 물어봤다. 묻고 이번 실행을 끝낸다
        return {"events": [
            step_started("publish"),
            ask("confirm_publish", {
                "summary": report["title"],
                "sectionCount": len(sections),
                "period": f"{report['period']['from']} ~ {report['period']['to']}",
            }),
            step_finished("publish"),
        ]}

    if answer.get("value") != "approved":
        # **거절도 결과다.** 예외로 처리하면 사용자는 무슨 일이 났는지 모른다
        return {"events": [text("발행하지 않았습니다. 고칠 곳을 알려 주세요.", final=True)]}

    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    ops = [patch.replace("/publishedAt", stamp)]
    report = patch.apply(report, ops)
    return {"report": report, "events": [
        state_delta(ops),
        text(f"발행했습니다. 섹션 {len(sections)}개가 공유 링크에 담겼습니다.", final=True),
    ]}


# ── refresh: 기간이 바뀌어 문서 전체가 낡은 경우 ─────────────────────


def refresh_node(state: ReportState) -> dict:
    """섹션을 새로 만들지 않고 **있던 것을 다시 채운다.**

    사용자가 "1월부터 보여줘"라고만 했을 때 여기로 온다. 무엇을 볼지는 그대로고
    언제를 볼지만 바뀐 것이므로, 계획을 다시 세울 이유가 없다. 계획 노드를
    부르지 않으므로 모델 호출도 그만큼 줄어든다.
    """
    report = dict(state["report"])
    sections = report["sections"]
    if not sections:
        return {"plan": [], "events": [text("먼저 볼 것을 정해 주세요.", final=True)]}

    ops: list[dict] = []
    for index, old in enumerate(sections):
        tuned = retune(old, report["period"])
        if tuned:
            ops += [patch.replace(f"/sections/{index}/groupBy", tuned["groupBy"]),
                    patch.replace(f"/sections/{index}/title", tuned["title"])]
        ops.append(patch.replace(f"/sections/{index}/status", "pending"))
    report = patch.apply(report, ops)
    sections = report["sections"]
    return {"report": report, "plan": list(sections), "results": [],
            "events": [step_started("refresh"), state_delta(ops), step_finished("refresh")]}
