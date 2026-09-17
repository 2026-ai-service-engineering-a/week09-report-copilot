"""AG-UI 문 — 그래프의 이벤트를 규격의 이벤트로 옮긴다.

8주차 `api/errors.py`가 코어의 실패를 HTTP 상태 코드로 옮겼다. 이 파일은
같은 일을 이벤트에 한다. **그래프는 AG-UI를 모르고, 여기가 번역표다.**

| 우리 이벤트 (`graph/state.py`) | AG-UI |
| --- | --- |
| `step_started` · `step_finished` | `STEP_STARTED` · `STEP_FINISHED` |
| `text` | `TEXT_MESSAGE_START` · `CONTENT`×N · `END` |
| `tool_call` | `TOOL_CALL_START` · `ARGS` · `END` · `RESULT` |
| `state_snapshot` · `state_delta` | `STATE_SNAPSHOT` · `STATE_DELTA` |
| `ask` | `TOOL_CALL_START` · `ARGS` · `END` (**RESULT는 화면이 만든다**) |
| `guard` · `route` | `CUSTOM` |
| `final` | `RUN_FINISHED` |

번역표가 한 곳에 있으면 규격이 자라도 고칠 자리가 하나다. 9주차 기준으로
AG-UI 이벤트는 36종이고 **우리가 쓰는 것은 열두 종**이다. 규격이 크다고 다
써야 하는 것은 아니다.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from ag_ui.core import (
    CustomEvent, RunAgentInput, RunErrorEvent, RunFinishedEvent, RunStartedEvent,
    StateDeltaEvent, StateSnapshotEvent, StepFinishedEvent, StepStartedEvent,
    TextMessageContentEvent, TextMessageEndEvent, TextMessageStartEvent,
    ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent, ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from api import store
from core.errors import CoreError
from graph.run import run

router = APIRouter()

# 완성된 문장을 이만큼씩 끊어 흘린다. 각본 대역은 한 번에 답을 내놓으므로
# 여기서 조각내야 화면이 차오르는 것이 보인다. 진짜 모델을 붙일 때는
# litellm의 stream=True가 만든 조각이 그대로 이 자리에 온다
CHUNK = 12


def _short() -> str:
    return uuid.uuid4().hex[:8]


def translate(event: dict, *, thread_id: str, run_id: str) -> list:
    """우리말 이벤트 하나를 AG-UI 이벤트 여럿으로 편다."""
    kind = event["event"]

    if kind == "state_snapshot":
        return [StateSnapshotEvent(snapshot=event["snapshot"])]
    if kind == "state_delta":
        return [StateDeltaEvent(delta=event["delta"])]
    if kind == "step_started":
        return [StepStartedEvent(step_name=event["name"])]
    if kind == "step_finished":
        return [StepFinishedEvent(step_name=event["name"])]

    if kind == "text":
        message_id = _short()
        body = event["text"] or ""
        out = [TextMessageStartEvent(message_id=message_id, role="assistant")]
        out += [
            TextMessageContentEvent(message_id=message_id, delta=body[i:i + CHUNK])
            for i in range(0, len(body), CHUNK)
        ]
        return out + [TextMessageEndEvent(message_id=message_id)]

    if kind == "tool_call":
        call_id = _short()
        return [
            ToolCallStartEvent(tool_call_id=call_id, tool_call_name=event["tool"]),
            ToolCallArgsEvent(tool_call_id=call_id,
                              delta=json.dumps(event["args"], ensure_ascii=False)),
            ToolCallEndEvent(tool_call_id=call_id),
            ToolCallResultEvent(message_id=_short(), tool_call_id=call_id,
                                content=event["result"]),
        ]

    if kind == "ask":
        # **프런트엔드 도구**는 결과를 여기서 만들지 않는다. 호출만 내보내고
        # 실행을 끝낸다. 화면이 카드를 띄우고, 사용자가 누르면 그 답을 실은
        # 새 요청이 온다. 루프가 멈춰 기다리는 것이 아니라 두 번 도는 것이다
        call_id = _short()
        return [
            ToolCallStartEvent(tool_call_id=call_id, tool_call_name=event["tool"]),
            ToolCallArgsEvent(tool_call_id=call_id,
                              delta=json.dumps(event["args"], ensure_ascii=False)),
            ToolCallEndEvent(tool_call_id=call_id),
        ]

    if kind in ("guard", "route"):
        # 규격에 딱 맞는 칸이 없는 것은 CUSTOM으로 보낸다. 억지로 다른 이벤트에
        # 끼워 넣으면 받는 쪽이 그것을 표준 의미로 읽는다
        return [CustomEvent(name=kind, value={k: v for k, v in event.items()
                                              if k != "event"})]

    if kind == "final":
        return [RunFinishedEvent(thread_id=thread_id, run_id=run_id,
                                 result={"usage": event["usage"]})]
    return []


@router.post("/agent")
async def agent(input: RunAgentInput, request: Request):
    """AG-UI 엔드포인트. 이 랩에 문은 이것 하나다.

    요청이 실어 오는 것 중 둘이 9주차의 전부다.

      · `state`           지금 화면이 들고 있는 리포트 문서
      · `forwarded_props` 무엇이 선택돼 있는지, 화면에서 무엇을 조작했는지

    v1 챗 위젯에는 이 둘이 없었다. 그래서 "이거 빼줘"에 되물을 수밖에 없었다.
    """
    encoder = EventEncoder(accept=request.headers.get("accept"))
    props = input.forwarded_props or {}
    said = next((m.content for m in reversed(input.messages)
                 if getattr(m, "role", None) == "user" and getattr(m, "content", None)), "")

    # 화면이 문서를 보냈으면 그것을 쓰고, 비어 있으면 저장된 것을 꺼낸다.
    # 새 대화의 첫 요청이 이 경우다
    doc = input.state if isinstance(input.state, dict) and input.state else store.load(input.thread_id)

    def stream_events():
        return run(
            doc, said or "",
            thread_id=input.thread_id,
            ui_action=props.get("uiAction"),
            selected=props.get("selectedSectionId"),
            simulate=props.get("simulate"),
            # 승인 카드를 누른 뒤의 두 번째 요청이 이것을 실어 온다.
            # **브라우저에서 오는 값이므로 그대로 믿지 않는다.** 무엇을 할지는
            # 서버의 publish_node가 다시 정한다 (교안 9장 4절)
            tool_result=props.get("toolResult"),
            max_cost_usd=float(props.get("maxCostUsd") or 0.20),
        )

    async def source() -> AsyncIterator[str]:
        """`EventEncoder`가 SSE 프레임을 만든다. `data: {…}` 한 줄에 빈 줄 하나다.

        3주차에 배운 SSE 그대로이고 새 전송 규약이 아니다. 선 위에서는
        필드가 camelCase가 된다. 파이썬에서 `thread_id`인 것이 `threadId`로
        나가고, 붙는 쪽이 자바스크립트라서 그렇다.
        """
        yield encoder.encode(RunStartedEvent(thread_id=input.thread_id, run_id=input.run_id))
        try:
            # 동기 제너레이터를 async 안에서 그냥 돌리면 이벤트 루프가 멈춘다.
            # 8주차 4장 6절에서 본 그 함정이고, 처방도 같다
            async for event in iterate_in_threadpool(stream_events()):
                if event["event"] == "final":
                    store.save(input.thread_id, event["report"])
                for out in translate(event, thread_id=input.thread_id, run_id=input.run_id):
                    yield encoder.encode(out)
        except CoreError as e:
            # 스트림이 시작된 뒤에는 상태 코드로 실패를 알릴 수 없다. 헤더가
            # 이미 200으로 나갔기 때문이다. **실패도 이벤트로 보낸다**
            # (8주차 4장 6절)
            yield encoder.encode(RunErrorEvent(message=str(e), code=type(e).__name__))

    return StreamingResponse(
        source(),
        media_type=encoder.get_content_type(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
