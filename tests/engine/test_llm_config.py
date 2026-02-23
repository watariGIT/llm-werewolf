import pytest

from llm_werewolf.engine.llm_config import (
    DEFAULT_MODEL_NAME,
    DEFAULT_TEMPERATURE,
    GM_DEFAULT_MODEL,
    GM_DEFAULT_TEMPERATURE,
    load_gm_config,
    load_llm_config,
)


class TestLLMConfig:
    def test_load_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
        monkeypatch.delenv("OPENAI_TEMPERATURE", raising=False)

        config = load_llm_config()

        assert config.api_key == "sk-test-key"
        assert config.model_name == DEFAULT_MODEL_NAME
        assert config.temperature == DEFAULT_TEMPERATURE

    def test_load_without_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            load_llm_config()

    def test_load_with_empty_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "   ")

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            load_llm_config()

    def test_load_with_custom_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_MODEL_NAME", "gpt-4o")
        monkeypatch.delenv("OPENAI_TEMPERATURE", raising=False)

        config = load_llm_config()

        assert config.model_name == "gpt-4o"

    def test_load_with_custom_temperature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
        monkeypatch.setenv("OPENAI_TEMPERATURE", "0.5")

        config = load_llm_config()

        assert config.temperature == 0.5

    def test_load_with_invalid_temperature_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_TEMPERATURE", "abc")

        with pytest.raises(ValueError, match="OPENAI_TEMPERATURE の値が不正です"):
            load_llm_config()

    def test_load_with_out_of_range_temperature_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_TEMPERATURE", "3.0")

        with pytest.raises(ValueError, match="0.0〜2.0"):
            load_llm_config()

    def test_config_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
        monkeypatch.delenv("OPENAI_TEMPERATURE", raising=False)

        config = load_llm_config()

        with pytest.raises(AttributeError):
            config.api_key = "new-key"  # type: ignore[misc]


class TestGMConfig:
    """load_gm_config のテスト。"""

    def test_load_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("GM_MODEL_NAME", raising=False)
        monkeypatch.delenv("GM_TEMPERATURE", raising=False)

        config = load_gm_config()

        assert config.api_key == "sk-test-key"
        assert config.model_name == GM_DEFAULT_MODEL
        assert config.temperature == GM_DEFAULT_TEMPERATURE

    def test_load_with_custom_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GM_MODEL_NAME", "gpt-4o")
        monkeypatch.delenv("GM_TEMPERATURE", raising=False)

        config = load_gm_config()

        assert config.model_name == "gpt-4o"

    def test_load_with_custom_temperature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("GM_MODEL_NAME", raising=False)
        monkeypatch.setenv("GM_TEMPERATURE", "0.5")

        config = load_gm_config()

        assert config.temperature == 0.5

    def test_load_without_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            load_gm_config()

    def test_load_with_invalid_temperature_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GM_TEMPERATURE", "abc")

        with pytest.raises(ValueError, match="GM_TEMPERATURE の値が不正です"):
            load_gm_config()

    def test_load_with_out_of_range_temperature_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GM_TEMPERATURE", "3.0")

        with pytest.raises(ValueError, match="0.0〜2.0"):
            load_gm_config()

    def test_gm_config_independent_from_player_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GM 設定がプレイヤー AI 設定と独立していること。"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_MODEL_NAME", "gpt-4o")
        monkeypatch.setenv("OPENAI_TEMPERATURE", "0.8")
        monkeypatch.setenv("GM_MODEL_NAME", "gpt-3.5-turbo")
        monkeypatch.setenv("GM_TEMPERATURE", "0.2")

        player_config = load_llm_config()
        gm_config = load_gm_config()

        assert player_config.model_name == "gpt-4o"
        assert player_config.temperature == 0.8
        assert gm_config.model_name == "gpt-3.5-turbo"
        assert gm_config.temperature == 0.2
        # API キーは共有
        assert player_config.api_key == gm_config.api_key
