"""LLM 호출의 단일 통로.

5주차에서 배운 대로 생성 호출은 전부 litellm을 지나간다. 이 랩에서 모델로
나가는 길은 **여기 하나뿐이다.**

하는 일 셋.

  ① 각본 대역으로의 분기 — 키가 없어도 수업이 돌아가게 (core/offline.py)
  ② 프로바이더 직접 호출 — 8주차와 달리 게이트웨이를 거치지 않는다
  ③ 실패의 번역 — litellm 예외를 core/errors.py의 종류로 바꾼다.
     이 자리가 없으면 그래프가 litellm 예외를 직접 알아야 하고, 그러면
     "코어는 위를 모른다"가 깨진다.

**게이트웨이를 걷어낸 것이 8주차를 뒤집는 것이 아니다.** 8주차 8장의 판단
그대로다. 앱이 하나면 직접 호출이 맞고, 게이트웨이는 부르는 곳이 둘 이상이
되거나 키를 남에게 나눠줘야 할 때부터 값을 한다.
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

    if not config.provider() and not kwargs.get("api_key"):
        raise UpstreamError(
            "LLM_MODE=live인데 프로바이더 키가 없다. .env에 "
            f"{' 또는 '.join(name for name, _ in config.PROVIDERS)} 중 하나를 넣고 "
            "docker compose up -d --force-recreate api 로 다시 만든다"
        )

    from litellm import completion as litellm_completion

    try:
        return litellm_completion(**kwargs)
    except Exception as e:
        name = type(e).__name__
        if "Timeout" in name:
            raise UpstreamTimeout(str(e)) from e
        # 원인을 짚기 쉽게 모델 이름을 함께 싣는다. 키는 절대 싣지 않는다
        raise UpstreamError(f"{name}: {e} (model={kwargs.get('model')})") from e
