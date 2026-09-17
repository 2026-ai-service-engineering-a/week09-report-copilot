"""요청마다 다른 루프가 돈다 — 같은 그래프, 다른 경로.

    docker compose exec api python examples/03_loop_routes.py

교안 7장의 표가 이 출력이다. **맨 위 둘은 모델을 한 번도 부르지 않는다.**
"""

import time

from core.schema import empty_report
from graph.run import run

CASES = [
    ("화면에서 차트 종류를 바꾼다", "", {"ui_action": {"type": "set_chart", "index": 0, "chart": "bar"}}),
    ('"막대로 바꿔줘"', "막대로 바꿔줘", {"selected": "s1"}),
    ('"8월 국적별 관객수 보여줘"', "8월 국적별 관객수 보여줘", {}),
    ('"8월 박스오피스 리포트 만들어줘"', "8월 박스오피스 리포트 만들어줘", {}),
]

print(f"{'요청':34s} {'경로':8s} {'모델':>5s} {'비용':>9s} {'벽시계':>7s}  섹션")
print("-" * 88)
for label, said, kwargs in CASES:
    doc = empty_report().dump()
    started = time.perf_counter()
    route = "?"
    for event in run(doc, said, thread_id="ex03", **kwargs):
        if event["event"] == "route":
            route = event["route"]
        elif event["event"] == "final":
            usage, report = event["usage"], event["report"]
    took = time.perf_counter() - started
    print(f"{label:34s} {route:8s} {usage['calls']:>4}회 "
          f"${usage['spent_usd']:>8.4f} {took:>6.2f}s  {len(report['sections'])}개")

print("""
루프가 늘 답은 아니다. 무엇을 할지가 이미 정해져 있으면 모델에게 물을 것이 없다.
확실한 것은 코드가 정하고 애매한 것만 모델에게 넘긴다 (7주차 라우팅 원칙).""")
