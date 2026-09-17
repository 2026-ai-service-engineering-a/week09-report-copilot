"""AG-UI 문 — 번역표와 계약.

그래프의 우리말 이벤트가 규격의 이벤트로 옳게 펴지는지를 본다. 규격이
자라도 고칠 곳이 `api/agui.py` 한 곳이라는 것이 이 테스트의 전제다.
"""

import json

from fastapi.testclient import TestClient

from api.agui import translate
from api.main import app


def types_of(event):
    return [e.type.value if hasattr(e.type, "value") else str(e.type)
            for e in translate(event, thread_id="t", run_id="r")]


def test_one_text_event_becomes_three():
    assert types_of({"event": "text", "text": "안녕하세요 " * 6})[:1] == ["TEXT_MESSAGE_START"]
    kinds = types_of({"event": "text", "text": "안녕하세요 " * 6})
    assert kinds[-1] == "TEXT_MESSAGE_END"
    assert kinds.count("TEXT_MESSAGE_CONTENT") > 1, "조각으로 흘러야 화면이 차오른다"


def test_one_tool_call_becomes_four():
    kinds = types_of({"event": "tool_call", "tool": "run_query",
                      "args": {"metric": "audi_cnt"}, "result": "{}"})
    assert kinds == ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"]


def test_state_events_pass_through():
    assert types_of({"event": "state_delta", "delta": []}) == ["STATE_DELTA"]
    assert types_of({"event": "state_snapshot", "snapshot": {}}) == ["STATE_SNAPSHOT"]


def test_unmapped_events_go_to_custom():
    """규격에 딱 맞는 칸이 없는 것을 다른 이벤트에 끼워 넣지 않는다."""
    assert types_of({"event": "guard", "check": "budget", "detail": "x"}) == ["CUSTOM"]


def test_agent_endpoint_streams_sse():
    with TestClient(app) as client:
        response = client.post("/agent", json={
            "thread_id": "t-test", "run_id": "r-1", "state": {},
            "messages": [{"id": "m1", "role": "user", "content": "막대로 바꿔줘"}],
            "tools": [], "context": [], "forwarded_props": {"selectedSectionId": "s1"},
        }, headers={"accept": "text/event-stream"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        frames = [json.loads(line[5:]) for line in response.text.splitlines()
                  if line.startswith("data:")]
        kinds = [f["type"] for f in frames]
        assert kinds[0] == "RUN_STARTED" and kinds[-1] == "RUN_FINISHED"
        assert "STATE_DELTA" in kinds
        # 선 위에서는 camelCase다. 파이썬 이름으로 찾으면 없다
        assert "threadId" in frames[0] and "thread_id" not in frames[0]


def test_chat_endpoint_has_no_state_in_its_contract():
    """v1의 계약에 화면이 없다는 것이 v1의 전부다."""
    from api.schemas import ChatRequest

    assert set(ChatRequest.model_fields) == {"messages"}
