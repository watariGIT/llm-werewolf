"""LLMActionProvider のテスト。

ChatOpenAI.invoke をモックして実 API を呼ばずにテストする。
"""

import random
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.llm_config import LLMConfig
from llm_werewolf.engine.llm_provider import LLMActionProvider


def _create_config() -> LLMConfig:
    return LLMConfig(model_name="gpt-4o-mini", temperature=0.7, api_key="test-key")


def _create_game() -> GameState:
    players = (
        Player(name="Alice", role=Role.SEER),
        Player(name="Bob", role=Role.VILLAGER),
        Player(name="Charlie", role=Role.WEREWOLF),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.VILLAGER),
    )
    game = GameState(players=players, phase=Phase.DAY, day=1)
    game = game.add_log("[配役] Alice は占い師です")
    game = game.add_log("[配役] Bob は村人です")
    game = game.add_log("[配役] Charlie は人狼です")
    game = game.add_log("[配役] Dave は村人です")
    game = game.add_log("[配役] Eve は村人です")
    return game


def _create_mock_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.content = content
    return mock


class TestLLMActionProviderInit:
    """コンストラクタのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_creates_chat_openai_with_config(self, mock_chat_openai: MagicMock) -> None:
        config = _create_config()
        LLMActionProvider(config)
        mock_chat_openai.assert_called_once_with(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=SecretStr("test-key"),
        )

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_uses_provided_rng(self, mock_chat_openai: MagicMock) -> None:
        config = _create_config()
        rng = random.Random(42)
        provider = LLMActionProvider(config, rng=rng)
        assert provider._rng is rng


class TestDiscuss:
    """discuss メソッドのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_returns_llm_response(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("怪しい人がいますね。")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        result = provider.discuss(game, game.players[1])  # Bob

        assert result == "怪しい人がいますね。"
        mock_instance.invoke.assert_called_once()

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_empty_response_returns_default(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        result = provider.discuss(game, game.players[1])

        assert result == "..."


class TestVote:
    """vote メソッドのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_exact_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Charlie")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[2], game.players[3])  # Charlie, Dave
        result = provider.vote(game, game.players[0], candidates)  # Alice votes

        assert result == "Charlie"

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_partial_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Charlieさんに投票します。")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[2], game.players[3])
        result = provider.vote(game, game.players[0], candidates)

        assert result == "Charlie"

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_fallback_to_random(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("わかりません")

        rng = random.Random(42)
        provider = LLMActionProvider(_create_config(), rng=rng)
        game = _create_game()
        candidates = (game.players[2], game.players[3])
        result = provider.vote(game, game.players[0], candidates)

        assert result in ("Charlie", "Dave")


class TestDivine:
    """divine メソッドのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_exact_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Bob")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[1], game.players[2])  # Bob, Charlie
        result = provider.divine(game, game.players[0], candidates)  # Alice (seer)

        assert result == "Bob"


class TestAttack:
    """attack メソッドのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_exact_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Alice")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[0], game.players[1])  # Alice, Bob
        result = provider.attack(game, game.players[2], candidates)  # Charlie (werewolf)

        assert result == "Alice"

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_night_phase(self, mock_chat_openai: MagicMock) -> None:
        from dataclasses import replace

        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Bob")

        provider = LLMActionProvider(_create_config())
        game = replace(_create_game(), phase=Phase.NIGHT)
        candidates = (game.players[0], game.players[1])
        result = provider.attack(game, game.players[2], candidates)

        assert result == "Bob"
