"""채팅 한 줄이 문서를 어떻게 고치는가 — JSON Patch가 흐르는 것을 본다.

    docker compose exec api python examples/02_state_delta.py

문서 전체가 아니라 **바뀐 자리만** 오간다. 그 크기 차이도 함께 잰다.
"""

import json

from core.schema import empty_report
from graph.run import run

TURNS = [
    ("8월 박스오피스 리포트 국적별로 만들어줘", None),
    ("첫 번째를 막대로 바꿔줘", "s1"),
    ("이거 빼줘", "s2"),
]

doc = empty_report().dump()
for said, selected in TURNS:
    print(f'\n💬 "{said}"   (선택: {selected or "없음"})')
    ops = []
    for event in run(doc, said, thread_id="ex02", selected=selected):
        if event["event"] == "state_delta":
            ops += event["delta"]
        elif event["event"] == "final":
            doc = event["report"]
            usage = event["usage"]
    for op in ops[:4]:
        value = json.dumps(op.get("value"), ensure_ascii=False)
        print(f"   {op['op']:8s} {op['path']:24s} {value[:58] if op.get('value') is not None else ''}")
    if len(ops) > 4:
        print(f"   … 그 밖에 {len(ops) - 4}건")

    delta_size = len(json.dumps(ops, ensure_ascii=False).encode())
    snapshot_size = len(json.dumps(doc, ensure_ascii=False).encode())
    print(f"   → 패치 {delta_size:,}B vs 스냅샷 {snapshot_size:,}B · 모델 {usage['calls']}회")

print(f"\n최종 섹션: {[s['title'] for s in doc['sections']]}")
print("""
첫 줄을 보면 패치가 스냅샷보다 크다. 리포트를 통째로 새로 만드는 요청이라
섹션 목록과 결과가 전부 실렸기 때문이다. **패치가 값을 하는 것은 그다음
줄부터다.** 차트 종류를 바꾸는 데 64바이트, 섹션 하나를 빼는 데 41바이트다.
문서가 커질수록 이 차이는 벌어진다.""")
