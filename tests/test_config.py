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


def test_the_default_is_a_cheap_model(monkeypatch):
    """**한 요청에 모델을 여러 번 부른다.** 리포트 하나에 열 번까지 간다."""
    for name, _ in config.PROVIDERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert config.pick_model() == "gemini/gemini-3.5-flash-lite"


def test_the_default_models_are_priced_so_the_budget_guard_works():
    """요금표에 없는 모델이면 `completion_cost`가 0을 돌려주고 **예산 게이트가
    조용히 꺼진다.** 루프는 돌지만 지갑을 지키는 층이 사라진다.

    기본 모델을 바꿀 때 여기서 걸리게 해 둔다. 7주차에 litellm 요금표
    드리프트로 겪은 것과 같은 종류의 문제다.

    `model_cost` 딕셔너리를 직접 보지 않는다. 키가 프로바이더 접두 없이
    들어 있는 계열이 있어서(`gpt-4o-mini`) 그대로 찾으면 없다고 나온다.
    `completion_cost`가 실제로 쓰는 `get_model_info`로 확인한다.
    """
    from litellm import get_model_info

    for _, model in config.PROVIDERS:
        info = get_model_info(model)
        assert info.get("input_cost_per_token"), f"요금이 없는 모델: {model}"


def test_llm_model_overrides(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.5-pro")
    assert config.pick_model() == "gemini/gemini-3.5-pro"


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
