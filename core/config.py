"""모델 선택과 실행 모드. 8주차 `core/config.py` 그대로다.

이 랩의 앱도 프로바이더를 직접 부르지 않는다. 모델로 나가는 길은 게이트웨이
하나뿐이고, 앱이 쥐는 것은 주소와 가상키 두 개다.

  · offline  게이트웨이가 없다. 각본 대역이 대신 답한다 (기본값)
  · live     게이트웨이가 있다. 진짜 호출이 그쪽으로 나간다
"""

import os

OFFLINE_MODEL = "offline/scripted-analyst"

# 게이트웨이 뒤의 기본 별명. gateway/config.yaml의 model_name 중 하나다
DEFAULT_GATEWAY_MODEL = "report"


def gateway() -> str:
    """게이트웨이 주소. 비어 있으면 각본 대역으로 돈다."""
    return os.environ.get("GATEWAY_URL", "").strip()


def gateway_key() -> str:
    """앱이 쥔 가상키. 진짜 프로바이더 키가 아니다."""
    return os.environ.get("GATEWAY_KEY", "").strip()


def mode() -> str:
    """이번 호출을 무엇으로 처리할지: "live" 또는 "offline"."""
    requested = (os.environ.get("LLM_MODE") or "auto").strip().lower()
    if requested in ("live", "offline"):
        return requested
    return "live" if gateway() else "offline"


def pick_model() -> str:
    """사용할 모델 이름. 게이트웨이가 없으면 각본 대역의 이름을 돌려준다."""
    if mode() == "offline" or not gateway():
        return OFFLINE_MODEL
    return "openai/" + os.environ.get("GATEWAY_MODEL", DEFAULT_GATEWAY_MODEL)
