"""모델 선택과 실행 모드.

**9주차에는 게이트웨이가 없다.** 8주차에 세운 판단 그대로다. 게이트웨이는
부르는 곳이 둘 이상이 되거나 키를 남에게 나눠줘야 할 때부터 값을 하고,
그 전에는 장애점을 하나 늘릴 뿐이다. 이 랩은 앱이 하나이므로 프로바이더를
직접 부른다. 10\~14주차 개인 프로젝트도 대개 이쪽이다.

모드는 둘이다.

  · offline  키가 없다. 각본 대역이 대신 답한다 (기본값)
  · live     키가 있다. 진짜 호출이 나간다

키는 서버 컨테이너에만 있다. **브라우저 번들에는 들어가지 않는다.** 화면은
우리 api만 부르고 모델은 서버가 부른다 (교안 11장 5절).
"""

import os

OFFLINE_MODEL = "offline/scripted-analyst"

# 키가 있는 프로바이더를 찾아 기본 모델을 고른다. 바꾸려면 `.env`의 LLM_MODEL.
#
# **한 요청에 모델을 여러 번 부른다.** 리포트 하나에 분류 1 + 계획 1 +
# 섹션마다 2 + 결론 1이고, 섹션이 넷이면 열 번이다. 그래서 기본은 각 계열의
# 가장 빠르고 싼 모델이다. 도구 호출만 되면 이 랩에는 충분하다.
PROVIDERS: list[tuple[str, str]] = [
    ("GEMINI_API_KEY", "gemini/gemini-3.5-flash-lite"),
    ("OPENAI_API_KEY", "openai/gpt-4o-mini"),
    ("ANTHROPIC_API_KEY", "anthropic/claude-haiku-4-5-20251001"),
]


def provider() -> tuple[str, str] | None:
    """채워진 키가 있으면 (환경변수 이름, 기본 모델)을 돌려준다."""
    for env_name, model in PROVIDERS:
        if os.environ.get(env_name, "").strip():
            return env_name, model
    return None


def mode() -> str:
    """이번 호출을 무엇으로 처리할지: "live" 또는 "offline"."""
    requested = (os.environ.get("LLM_MODE") or "auto").strip().lower()
    if requested in ("live", "offline"):
        return requested
    return "live" if provider() else "offline"


def pick_model() -> str:
    """사용할 모델 이름. 키가 없으면 각본 대역의 이름을 돌려준다.

    서버는 키가 없다고 죽지 않는다. 죽는 대신 각본 대역으로 답하거나
    502로 알린다.
    """
    if mode() == "offline":
        return OFFLINE_MODEL
    chosen = os.environ.get("LLM_MODEL", "").strip()
    if chosen:
        return chosen
    found = provider()
    return found[1] if found else OFFLINE_MODEL
