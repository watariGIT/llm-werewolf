import pytest

from llm_werewolf.engine.llm_config import DEFAULT_MODEL_NAME, DEFAULT_TEMPERATURE, load_llm_config


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

    def test_config_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
        monkeypatch.delenv("OPENAI_TEMPERATURE", raising=False)

        config = load_llm_config()

        with pytest.raises(AttributeError):
            config.api_key = "new-key"  # type: ignore[misc]
