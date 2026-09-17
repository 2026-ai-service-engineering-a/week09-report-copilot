"""실패를 상태 코드로 옮기는 자리. 8주차 `api/errors.py`와 같다.

코어는 "무엇이 실패했는가"만 말한다(`core/errors.py`). 그것이 HTTP에서 몇
번인지는 문이 정한다.

  · 상류(모델)가 실패했다      → 502 Bad Gateway
  · 상류가 제때 답하지 않았다   → 504 Gateway Timeout
  · 하네스가 질의를 막았다      → 400 Bad Request
  · 지표 사전에 없는 용어다     → 400 Bad Request
  · 요청이 계약을 어겼다        → 422 (FastAPI가 자동으로)

**500이 아니라는 점이 중요하다.** 500은 "우리 코드가 깨졌다"는 뜻이고,
모델 제공자의 장애나 막힌 질의를 500으로 돌려주면 원인을 잘못 짚는다.

스트리밍 문(`/agent`)은 이 표를 쓰지 않는다. 헤더가 이미 나간 뒤라 상태
코드를 고칠 수 없고, 그래서 실패도 이벤트로 보낸다 (`RUN_ERROR`).
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from core.errors import BlockedQuery, UnknownMetric, UpstreamError, UpstreamTimeout

STATUS = {
    UpstreamTimeout: 504,
    UpstreamError: 502,
    BlockedQuery: 400,
    UnknownMetric: 400,
}


async def handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS.get(type(exc), 502),
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def install(app) -> None:
    for kind in STATUS:
        app.add_exception_handler(kind, handler)
