"""어느 루프를 돌 것인가.

7주차 4장의 원칙이 여기서 돈을 아낀다. **확실한 것은 코드가 정하고 애매한
것만 LLM에게** 넘긴다. 사용자가 슬라이더를 움직이는 동안 모델이 다섯 번
불리는 사고는 실제로 흔하다.

    화면 조작        → 모델 0회. 코드가 곧장 패치를 만든다
    확실한 한마디     → 모델 0회. 정규식이 잡는다
    나머지          → 모델 1회. 넷 중 하나로 분류한다

`apply`로 떨어지면 이 요청의 모델 호출은 **0회로 끝난다.**
"""

from __future__ import annotations

from core import config
from core.llm import completion
from core.prompts import ROUTER
from graph import phrases

ROUTES = ("apply", "react", "plan", "publish")


def certain(said: str) -> str | None:
    """코드가 잡는 것들. 말이 짧고 뜻이 하나뿐이라 모델에게 물을 이유가 없다.

    **규칙은 `graph/phrases.py` 한 곳에 있다.** 여기에 정규식을 다시 적으면
    노드 쪽과 어긋나고, 실제로 한 번 어긋나 "막대 그래프로 해줘"가 분류
    호출로 샜다.
    """
    if phrases.PUBLISH.search(said):
        # 되돌리기 어려운 행동도 코드가 잡는다. 모델의 해석에 맡길 자리가 아니다
        return "publish"
    if phrases.edits_selection(said):
        return "apply"
    return None


def classify(text: str, *, simulate: str | None = None, budget=None) -> tuple[str, int]:
    """(경로, 모델 호출 수)를 돌려준다. 호출 수를 함께 주는 것이 요점이다.

    **장부(`budget`)를 받는 것이 중요하다.** 라우터도 모델을 부르는데 그 호출을
    세지 않으면 화면의 "모델 호출 0회"가 거짓말이 되고, 무엇보다 6주차 예산
    게이트가 그만큼을 못 본다. **장부에 안 잡히는 호출이 하나라도 있으면
    예산 게이트는 반쪽이다.**
    """
    found = certain(text or "")
    if found:
        return found, 0

    response = completion(
        model=config.pick_model(),
        messages=[{"role": "system", "content": ROUTER},
                  {"role": "user", "content": text}],
        simulate=simulate,
    )
    if budget:
        budget.add_response(response)
    answer = (response.choices[0].message.content or "").strip().lower()
    for route in ROUTES:
        if route in answer:
            return route, 1
    return "react", 1          # 못 알아들으면 가장 무난한 쪽으로


# 프런트엔드 도구의 답은 **물어본 노드로 돌아간다.** 승인 카드를 누른 뒤의
# 두 번째 요청에는 사용자가 친 말이 없으므로, 분류를 하면 엉뚱한 데로 간다
ASKED_BY = {"confirm_publish": "publish"}


def route(state: dict) -> tuple[str, int]:
    """화면에서 온 것이면 모델을 아예 부르지 않는다."""
    answer = state.get("tool_result") or {}
    if answer.get("name") in ASKED_BY:
        return ASKED_BY[answer["name"]], 0
    if state.get("ui_action"):
        return "apply", 0
    return classify(state.get("text") or "", simulate=state.get("simulate"),
                    budget=state.get("budget"))
