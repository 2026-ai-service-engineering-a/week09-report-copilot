"""각본 대역 — 키 없이도 그래프가 진짜로 도는 가짜 모델.

8주차 `core/offline.py`와 같은 자리다. 다른 점은 이 랩의 모델이 **역할이
여럿**이라는 것. 그래서 대역도 역할을 구분해야 하고, 그 열쇠가 시스템
프롬프트의 `[[node:…]]` 표지다 (`core/prompts.py`).

가짜인 것은 모델뿐이다.

  · 도구는 진짜로 실행된다 (`core/tools.py` → PostgreSQL)
  · 숫자는 진짜 박스오피스 데이터다
  · 상태 패치도, 예산도, 게이트도 진짜로 일어난다

수강생이 보는 화면에서 가짜인 부분은 **무엇을 부를지 정하는 판단** 하나뿐이다.
"""

from __future__ import annotations

import json
import os
import re
import time
from types import SimpleNamespace

from core import config
from core.harness import BOUNDARY_OPEN as BOUNDARY

# 한 번 답하는 데 매기는 가짜 비용(USD). BudgetGuard가 이 값을 장부에 더한다.
# 키 없이도 예산 게이트를 시연하려는 장치다
FAKE_COST_PER_CALL = 0.0012
FAKE_COST_BUDGET_BOMB = 0.5      # simulate="budget"일 때 한 번에 상한을 넘긴다

MARK = "[각본 대역] "

# 즉시 답할 수도 있지만 그러면 스트리밍이 흐르는 것이 눈에 보이지 않는다
LATENCY_MS = int(os.environ.get("OFFLINE_LATENCY_MS", "400"))


def _node_of(messages: list[dict]) -> str:
    """시스템 프롬프트의 표지를 읽어 어느 역할인지 가린다."""
    system = next((m.get("content") or "" for m in messages if m.get("role") == "system"), "")
    found = re.search(r"\[\[node:(\w+)\]\]", system)
    return found.group(1) if found else "writer"


def _user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


def _tool_results(messages: list[dict]) -> list[dict]:
    """지금까지 도구가 돌려준 것들. 대역이 '결과를 보고' 판단하게 한다.

    role이 `tool`인 것만 보지 않는다. 작성가에게는 집계 결과가 **경계로 감싸인
    사용자 메시지**로 들어오기 때문이다 (`core/harness.wrap_untrusted`).
    데이터가 어느 자리로 오든 대역은 같은 것을 읽어야 한다.
    """
    out = []
    for message in messages:
        body = message.get("content") or ""
        if message.get("role") == "tool" or BOUNDARY in body:
            body = re.sub(r"<<<[^>]*>>>", "", body).strip()
            start, end = body.find("{"), body.rfind("}")
            if start < 0 or end < start:
                continue
            try:
                out.append(json.loads(body[start:end + 1]))
            except json.JSONDecodeError:
                pass
    return out


def _call(name: str, arguments: dict, call_id: str):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


def _response(*, content=None, tool_calls=None, cost=FAKE_COST_PER_CALL,
              prompt_tokens=700, completion_tokens=120):
    message = SimpleNamespace(
        role="assistant", content=content, tool_calls=tool_calls,
        model_dump=lambda: {
            "role": "assistant", "content": content,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in (tool_calls or [])
            ] or None,
        },
    )
    response = SimpleNamespace(
        model=config.OFFLINE_MODEL,
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )
    response.fake_cost_usd = cost
    return response


# ── 역할별 대본 ───────────────────────────────────────────────────────

_AXIS_WORDS = [
    ("nation", ("국적", "나라", "국가", "한국", "외국")),
    ("genre", ("장르",)),
    ("distributor", ("배급", "배급사")),
    ("watchGrade", ("등급", "관람등급")),
    ("movieType", ("구분", "예술", "독립")),
    ("movieNm", ("영화별", "작품별", "상위", "순위", "톱", "top")),
]


def _guess_axis(text: str) -> str | None:
    for axis, words in _AXIS_WORDS:
        if any(word in text for word in words):
            return axis
    return None


def _route(text: str) -> str:
    if any(word in text for word in ("리포트", "보고서", "정리해", "만들어줘", "분석해")):
        return "plan"
    if any(word in text for word in ("보여줘", "알려줘", "얼마", "몇", "상위", "순위")):
        return "react"
    return "one"


def _plan_sections(text: str) -> list[dict]:
    """계획 노드의 대본. 요청에 실린 말에서 축을 고른다."""
    axis = _guess_axis(text)
    sections = [
        {"kind": "chart", "chart": "line", "metric": "audi_cnt",
         "title": "일별 관객수", "groupBy": None},
        {"kind": "chart", "chart": "bar", "metric": "audi_cnt",
         "title": "국적별 관객수", "groupBy": "nation"},
        {"kind": "table", "metric": "audi_cnt",
         "title": "관객수 상위 10편", "groupBy": "movieNm"},
    ]
    if axis and axis not in ("nation", "movieNm"):
        sections.insert(2, {"kind": "chart", "chart": "bar", "metric": "audi_cnt",
                            "title": f"{axis}별 관객수", "groupBy": axis})
    return sections


def _analyst(messages: list[dict]):
    """분석가의 대본: 아직 조회하지 않았으면 조회하고, 했으면 요약한다."""
    results = _tool_results(messages)
    text = _user_text(messages)
    if not results:
        spec = json.loads(re.search(r"\{.*\}", text, re.S).group(0)) if "{" in text else {}
        return _response(tool_calls=[_call("run_query", spec, "call_analyst_1")])
    rows = results[-1].get("rows") or []
    top = ", ".join(f"{r[0]} {r[1]:,.0f}" for r in rows[:3] if r[1] is not None)
    return _response(content=f"{MARK}상위 항목: {top}" if top else f"{MARK}결과가 비어 있습니다.")


def _writer(messages: list[dict]) -> str:
    """작성가의 대본.

    비율은 **도구가 준 `total`로만** 계산한다. 화면에 보이는 상위 몇 줄을
    더해서 나누면 조금씩 틀리고, 그 틀림은 아무도 못 알아챈다. 프롬프트에
    "비율을 직접 계산하지 말라"고 적어 두었지만 부탁은 부탁이고, 도구가
    총합을 함께 주는 것이 구조적 해결이다.
    """
    rows, total = [], None
    for result in _tool_results(messages):
        rows = result.get("rows") or rows
        total = result.get("total", total)
    if not rows:
        return f"{MARK}이 구간에서 집계된 값이 없습니다."

    # **"가장 많다"고 쓰려면 실제로 가장 큰 행을 골라야 한다.**
    # 첫 행을 집으면 일자별 결과에서 "8월 1일이 가장 많다"가 되는데, 그건
    # 그냥 기간의 첫날이다. 집계는 맞는데 문장이 틀리는 종류의 오류이고,
    # 검증자가 숫자만 대조해서는 잡히지 않는다
    scored = [r for r in rows if isinstance(r[1], (int, float))]
    if not scored:
        return f"{MARK}이 구간에서 집계된 값이 없습니다."
    top = max(scored, key=lambda r: r[1])
    if total:
        return (f"{MARK}{top[0]}이(가) {top[1]:,.0f}으로 가장 많고, "
                f"전체의 {top[1] / total * 100:.1f}%를 차지합니다.")
    return f"{MARK}{top[0]}이(가) {top[1]:,.0f}으로 가장 많습니다."


def _narrate(notes: str) -> str:
    """결론의 대본. 섹션 메모에서 문장 하나씩 골라 이어 붙인다."""
    lines = [
        line.split(": ", 1)[1].replace(MARK, "").strip()
        for line in (notes or "").splitlines()
        if line.startswith("- ") and ": " in line
    ]
    said = [line for line in lines if line][:2]
    if not said:
        return f"{MARK}이 기간에는 결론으로 삼을 만한 수치가 없습니다."
    return MARK + " ".join(said)


def completion(*, simulate: str | None = None, **kwargs):
    """litellm.completion과 같은 모양의 응답을 돌려준다."""
    if LATENCY_MS:
        time.sleep(LATENCY_MS / 1000)

    messages: list[dict] = kwargs.get("messages") or []
    node = _node_of(messages)
    text = _user_text(messages)
    cost = FAKE_COST_BUDGET_BOMB if simulate == "budget" else FAKE_COST_PER_CALL

    if node == "router":
        return _response(content=_route(text), cost=cost, completion_tokens=3)
    if node == "plan":
        return _response(content=json.dumps(_plan_sections(text), ensure_ascii=False), cost=cost)
    if node == "analyst":
        response = _analyst(messages)
        response.fake_cost_usd = cost
        return response
    if node == "verify":
        # 대역은 늘 통과시킨다. 불일치 재현은 examples/에서 일부러 만든다
        return _response(content="ok", cost=cost, completion_tokens=2)
    if node == "narrate":
        return _response(content=_narrate(text), cost=cost)
    return _response(content=_writer(messages), cost=cost)
