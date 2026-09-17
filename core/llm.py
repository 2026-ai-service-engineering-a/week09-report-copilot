"""LLM 호출의 단일 통로. 8주차 `core/llm.py`와 같은 자리다.

이 저장소에서 모델로 나가는 길은 **여기 하나뿐이고, 그 끝은 언제나
게이트웨이다.** 앱에는 프로바이더 키가 없다.

하는 일 셋.

  ① 각본 대역으로의 분기 — 키가 없어도 수업이 돌아가게 (core/offline.py)
  ② 게이트웨이 주소·가상키 주입 — 호출 코드는 그대로 두고 주소만 바꾼다
  ③ 실패의 번역 — litellm 예외를 core/errors.py의 종류로 바꾼다.
     이 자리가 없으면 그래프가 litellm 예외를 직접 알아야 하고, 그러면
     "코어는 위를 모른다"가 깨진다.
"""

from core import config, offline
from core.errors import UpstreamError, UpstreamTimeout


def completion(*, simulate: str | None = None, **kwargs):
    """모델 호출 한 번. 어느 경로로 가든 응답의 모양은 같다.

    simulate는 **랩 전용 스위치**다. 실패를 5초 만에 재현하려고 둔 것이고
    실제 서비스에는 이런 인자를 두지 않는다.
    """
    if simulate == "upstream":
        raise UpstreamError("모의 상류 장애: 모델 제공자가 500을 돌려줬다")
    if simulate == "timeout":
        raise UpstreamTimeout("모의 시간 초과: 모델이 제한 시간 안에 답하지 않았다")

    if config.mode() == "offline":
        return offline.completion(simulate=simulate, **kwargs)

    if not config.gateway():
        raise UpstreamError(
            "LLM_MODE=live인데 GATEWAY_URL이 없다. 이 랩의 앱은 프로바이더를 "
            "직접 부르지 않는다. .env에 게이트웨이 주소와 가상키를 넣는다"
        )
    if not config.gateway_key():
        # 비워 두면 litellm이 환경의 다른 키를 대신 보내고, 게이트웨이는 모르는
        # 키라며 거절한다. 원인을 짚기 어려우므로 여기서 먼저 막는다
        raise UpstreamError(
            "GATEWAY_URL은 있는데 GATEWAY_KEY가 비어 있다. "
            "관리자 화면(:4000/ui/)에서 가상키를 발급해 .env에 넣고 "
            "docker compose up -d --force-recreate api 로 다시 만든다"
        )

    from litellm import completion as litellm_completion

    kwargs["api_base"] = config.gateway()
    kwargs["api_key"] = config.gateway_key()
    try:
        return litellm_completion(**kwargs)
    except Exception as e:
        name = type(e).__name__
        if "Timeout" in name:
            raise UpstreamTimeout(str(e)) from e
        raise UpstreamError(f"{name}: {e}") from e
