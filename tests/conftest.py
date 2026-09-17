"""테스트 공통 준비.

전부 네트워크·API 키 없이 돈다. 각본 대역이 기본 경로이므로 "더미 키라도
채워야 도는" 함정을 만들지 않는다 (8주차와 같은 방침).

데이터베이스가 필요한 테스트만 `needs_db`를 붙인다. 적재 전에도 나머지는
전부 통과해야 한다.
"""

import pytest

from core import config, db, offline


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    """**개발자의 `.env`에 기대지 않는다.**

    키를 넣고 `LLM_MODEL`을 바꿔 둔 사람의 기계에서만 깨지는 테스트는
    테스트가 아니다. 실제로 그렇게 한 번 깨졌다. 주변 환경을 먼저 비우고
    각본 대역으로 고정한다.
    """
    monkeypatch.delenv("LLM_MODEL", raising=False)
    for name, _ in config.PROVIDERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODE", "offline")
    monkeypatch.setattr(offline, "LATENCY_MS", 0)   # 테스트에서는 지연을 끈다


@pytest.fixture
def needs_db():
    if not db.ready():
        pytest.skip("데이터가 아직 없다: python -m scripts.load_data")
