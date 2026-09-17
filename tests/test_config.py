"""모델 선택 — **게이트웨이 없이** 프로바이더를 직접 부른다.

8주차를 뒤집는 것이 아니라 8주차 8장의 판단 그대로다. 앱이 하나면 직접
호출이 맞고, 게이트웨이는 부르는 곳이 둘 이상이 되거나 키를 남에게 나눠줘야
할 때부터 값을 한다. 10\~14주차 개인 프로젝트도 대개 이쪽이다.
"""

import pytest

from core import config
from core.errors import UpstreamError
from core.llm import completion


def test_no_key_means_the_scripted_stand_in(monkeypatch):
    for name, _ in config.PROVIDERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODE", "auto")
    assert config.mode() == "offline"
    assert config.pick_model() == config.OFFLINE_MODEL


def test_the_first_filled_key_picks_the_model(monkeypatch):
    for name, _ in config.PROVIDERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert config.mode() == "live"
    assert config.pick_model() == "openai/gpt-4o-mini"


def test_llm_model_overrides(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-2.5-pro")
    assert config.pick_model() == "gemini/gemini-2.5-pro"


def test_live_without_a_key_fails_with_a_useful_message(monkeypatch):
    """서버는 키가 없다고 죽지 않는다. **무엇을 해야 하는지 말하고** 502가 된다."""
    for name, _ in config.PROVIDERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODE", "live")
    with pytest.raises(UpstreamError) as caught:
        completion(model="gemini/gemini-2.5-flash", messages=[])
    assert "GEMINI_API_KEY" in str(caught.value)


def test_errors_carry_the_model_but_never_the_key(monkeypatch):
    """원인을 짚으려면 모델 이름이 필요하다. 키는 절대 싣지 않는다."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-secret-value")
    with pytest.raises(UpstreamError) as caught:
        completion(model="gemini/does-not-exist", messages=[{"role": "user", "content": "x"}])
    message = str(caught.value)
    assert "model=gemini/does-not-exist" in message
    assert "sk-secret-value" not in message
