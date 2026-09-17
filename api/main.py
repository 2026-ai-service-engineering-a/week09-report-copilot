"""문 — 화면 모드 넷이 부르는 자리.

이 랩의 재미는 **네 모드가 같은 코어를 부른다**는 데 있다. 갈리는 것은
요청이 무엇을 실어 오느냐뿐이다.

  POST /report      v0 폼형.    조건만 온다. 대화가 없다
  POST /chat        v1 챗 위젯. 대화만 온다. **화면 상태가 없다**
  POST /agent       v2·v3.      대화 + 상태 + 선택이 함께 온다 (api/agui.py)

`/chat`과 `/agent`가 같은 그래프를 부른다는 것을 봐 두자. v1이 무너지는
것은 모델이 나빠서가 아니라 **요청에 화면이 없어서**다. 코드로는
`selected=None` 한 줄의 차이다 (교안 3장 3절).
"""

from __future__ import annotations

import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api import agui, errors, store
from api.schemas import ChatRequest, ChatResponse, ReportRequest
from core import config, db, schema
from graph.run import run

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("report-copilot")

app = FastAPI(
    title="report-copilot — 박스오피스 리포트",
    version="1.0",
    description=(
        "화면과 에이전트가 같은 문서를 본다. 같은 그래프를 v0·v1·v2·v3 네 화면이 "
        "부르고, 갈리는 것은 요청이 무엇을 실어 오느냐뿐이다."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o],
    allow_methods=["*"],
    allow_headers=["*"],
)
errors.install(app)
app.include_router(agui.router)


@app.middleware("http")
async def request_id_and_log(request: Request, call_next):
    """요청 하나에 이름표를 붙이고 끝나면 한 줄을 남긴다 (8주차 4장 3절)."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    took_ms = round((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %s %sms request_id=%s",
                request.method, request.url.path, response.status_code, took_ms, request_id)
    return response


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


@app.get("/config")
def read_config() -> dict:
    """지금 이 서버가 무엇으로 도는가. **키는 내보내지 않는다.**"""
    return {
        "mode": config.mode(),
        "model": config.pick_model(),
        "gateway": config.gateway() or None,      # 주소만. 키는 아니다
        "dataReady": db.ready(),
        "rawSql": os.environ.get("ALLOW_RAW_SQL") == "1",
    }


@app.get("/report/{thread_id}")
def read_report(thread_id: str) -> dict:
    """저장된 문서를 꺼낸다. 화면이 처음 뜰 때 부른다.

    새로고침해도 같은 문서가 나오는 이유가 이 엔드포인트다. 공유 상태는
    브라우저가 아니라 DB에 산다 (교안 5장 5절).
    """
    return store.load(thread_id)


@app.post("/report")
def build_report(body: ReportRequest) -> dict:
    """v0 · 폼형. AI가 화면 **뒤에** 있다.

    3주차 식단 플래너와 같은 모양이다. 조건을 폼으로 받아 결과를 돌려주고
    끝난다. 서버는 요청 사이에 아무것도 기억하지 않는다.

    **이 구조는 정직하다.** 무상태 단발 함수에는 폼형이 맞는다. 다만 폼에
    없는 것을 사용자가 원하면 방법이 없다.
    """
    doc = schema.empty_report(body.date_from, body.date_to).dump()
    said = f"{body.date_from}부터 {body.date_to}까지 리포트 만들어줘"
    if body.group_by:
        said += f" {body.group_by}별로"

    final = None
    for event in run(doc, said, thread_id=f"form:{body.date_from}"):
        if event["event"] == "final":
            final = event
    return {"report": final["report"], "usage": final["usage"]}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    """v1 · 챗 위젯. AI가 화면 **옆에** 있다.

    **일부러 화면 상태를 받지 않는다.** 이 계약에는 `state`도 `selected`도
    없고, 그래서 사용자가 화면에서 섹션을 고른 채 "이거 빼줘"라고 해도
    무엇을 가리키는지 알 수 없다.

    세상의 AI 챗봇 위젯 대부분이 지금 이 모양이다. 고장이 아니라 구조의
    결과라는 것이 교안 3장 3절의 요점이다. 아래 `selected=None`이 그 구조다.
    """
    said = body.messages[-1].content if body.messages else ""
    doc = schema.empty_report().dump()

    reply = ""
    for event in run(doc, said, thread_id="chat", selected=None):
        if event["event"] == "text":
            reply = event["text"]
        elif event["event"] == "final" and not reply:
            reply = event["report"]["conclusion"]
    return ChatResponse(reply=reply or "무엇을 도와드릴까요?")
