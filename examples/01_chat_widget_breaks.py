"""v1이 무너지는 장면 — 같은 한마디, 다른 요청.

    docker compose exec api python examples/01_chat_widget_breaks.py

사용자는 화면에서 섹션을 골라 놓고 "이거 빼줘"라고 말한다. 두 경우의 차이는
**요청이 그 선택을 실어 오느냐** 하나뿐이다. 모델도 그래프도 같은 것을 쓴다.
"""

from core.schema import empty_report
from graph.run import run


def try_it(label: str, selected: str | None) -> None:
    doc = empty_report().dump()
    print(f"\n{label}")
    print(f"  요청에 실린 선택: {selected or '없음'}")
    deltas, reply = [], ""
    for event in run(doc, "이거 빼줘", thread_id="ex01", selected=selected):
        if event["event"] == "state_delta":
            deltas += event["delta"]
        elif event["event"] == "text":
            reply = event["text"]
        elif event["event"] == "final":
            left = [s["id"] for s in event["report"]["sections"]]
    print(f"  패치: {deltas or '없음'}")
    if reply:
        print(f"  답: {reply}")
    print(f"  남은 섹션: {left}")


print("화면에는 섹션이 둘 있고, 사용자는 s2를 골라 놓은 상태다.")
try_it("① v1 · 챗 위젯 (POST /chat)", None)
try_it("② v2 · 공유 상태 (POST /agent)", "s2")

print("""
같은 모델, 같은 그래프, 같은 한마디다. 갈린 것은 요청의 모양 하나다.
프롬프트를 아무리 다듬어도 없는 정보는 생기지 않는다.""")
