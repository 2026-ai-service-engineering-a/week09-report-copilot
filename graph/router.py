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

import re

from core import config
from core.llm import completion
from core.prompts import ROUTER

ROUTES = ("apply", "one", "react", "plan")

# 코드가 잡는 것들. 말이 짧고 뜻이 하나뿐이라 모델에게 물을 이유가 없다
CERTAIN = [
    (re.compile(r"(막대|바|bar)\s*(차트)?로"), "apply"),
    (re.compile(r"(선|라인|line)\s*(차트)?로"), "apply"),
    (re.compile(r"(파이|원|pie)\s*(차트)?로"), "apply"),
    (re.compile(r"(맨\s*)?(위|아래)로\s*(올려|내려)"), "apply"),
    (re.compile(r"(빼|지워|삭제)\s*(줘|주세요)?$"), "apply"),
]


def classify(text: str, *, simulate: str | None = None) -> tuple[str, int]:
    """(경로, 모델 호출 수)를 돌려준다. 호출 수를 함께 주는 것이 요점이다."""
    for pattern, route in CERTAIN:
        if pattern.search(text or ""):
            return route, 0

    response = completion(
        model=config.pick_model(),
        messages=[{"role": "system", "content": ROUTER},
                  {"role": "user", "content": text}],
        simulate=simulate,
    )
    answer = (response.choices[0].message.content or "").strip().lower()
    for route in ROUTES:
        if route in answer:
            return route, 1
    return "react", 1          # 못 알아들으면 가장 무난한 쪽으로


def route(state: dict) -> tuple[str, int]:
    """화면 조작이면 모델을 아예 부르지 않는다."""
    if state.get("ui_action"):
        return "apply", 0
    return classify(state.get("text") or "", simulate=state.get("simulate"))
