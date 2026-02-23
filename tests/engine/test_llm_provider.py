"""LLMActionProvider のテスト。

ChatOpenAI.invoke をモックして実 API を呼ばずにテストする。
リトライ・フォールバック動作・ロギングのテストを含む。
"""

import logging
import random
from unittest.mock import MagicMock, patch

import openai
import pytest
from pydantic import SecretStr

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.llm_config import LLMConfig
from llm_werewolf.engine.llm_provider import FALLBACK_DISCUSS_MESSAGE, MAX_RETRIES, LLMActionProvider


def _create_config() -> LLMConfig:
    return LLMConfig(model_name="gpt-4o-mini", temperature=0.7, api_key="test-key")


def _create_game() -> GameState:
    players = (
        Player(name="Alice", role=Role.SEER),
        Player(name="Bob", role=Role.VILLAGER),
        Player(name="Charlie", role=Role.WEREWOLF),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.KNIGHT),
        Player(name="Frank", role=Role.MEDIUM),
        Player(name="Grace", role=Role.MADMAN),
        Player(name="Heidi", role=Role.WEREWOLF),
        Player(name="Ivan", role=Role.VILLAGER),
    )
    game = GameState(players=players, phase=Phase.DAY, day=1)
    game = game.add_log("[配役] Alice は占い師です")
    game = game.add_log("[配役] Bob は村人です")
    game = game.add_log("[配役] Charlie は人狼です")
    game = game.add_log("[配役] Dave は村人です")
    game = game.add_log("[配役] Eve は狩人です")
    game = game.add_log("[配役] Frank は霊媒師です")
    game = game.add_log("[配役] Grace は狂人です")
    game = game.add_log("[配役] Heidi は人狼です")
    game = game.add_log("[配役] Ivan は村人です")
    return game


def _create_mock_response(content: str, usage_metadata: dict[str, int] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.content = content
    mock.usage_metadata = usage_metadata
    return mock


def _create_api_timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=MagicMock())


def _create_rate_limit_error() -> openai.RateLimitError:
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {}
    return openai.RateLimitError(message="Rate limit exceeded", response=mock_response, body=None)


def _create_server_error(status_code: int = 500) -> openai.APIStatusError:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    return openai.APIStatusError(message=f"Server error {status_code}", response=mock_response, body=None)


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


class TestGuard:
    """guard メソッドのテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_exact_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Alice")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[0], game.players[1])  # Alice, Bob
        result = provider.guard(game, game.players[4], candidates)  # Eve (knight)

        assert result == "Alice"

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_partial_match(self, mock_chat_openai: MagicMock) -> None:
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Aliceさんを護衛します。")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[0], game.players[1])
        result = provider.guard(game, game.players[4], candidates)

        assert result == "Alice"


class TestRetry:
    """リトライ機構のテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_retry_on_timeout_then_success(self, mock_chat_openai: MagicMock) -> None:
        """タイムアウト後にリトライで成功する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [
            _create_api_timeout_error(),
            _create_mock_response("リトライ後の発言です。"),
        ]

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        result = provider.discuss(game, game.players[1])

        assert result == "リトライ後の発言です。"
        assert mock_instance.invoke.call_count == 2
        provider._sleep.assert_called_once_with(1)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_retry_on_rate_limit_then_success(self, mock_chat_openai: MagicMock) -> None:
        """レート制限後にリトライで成功する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [
            _create_rate_limit_error(),
            _create_mock_response("Charlie"),
        ]

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[2], game.players[3])
        result = provider.vote(game, game.players[0], candidates)

        assert result == "Charlie"
        assert mock_instance.invoke.call_count == 2

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_retry_on_server_error_then_success(self, mock_chat_openai: MagicMock) -> None:
        """サーバーエラー (5xx) 後にリトライで成功する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [
            _create_server_error(500),
            _create_mock_response("Bob"),
        ]

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[1], game.players[2])
        result = provider.divine(game, game.players[0], candidates)

        assert result == "Bob"
        assert mock_instance.invoke.call_count == 2

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_exponential_backoff(self, mock_chat_openai: MagicMock) -> None:
        """指数バックオフで待機時間が増加する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [
            _create_api_timeout_error(),
            _create_api_timeout_error(),
            _create_mock_response("成功"),
        ]

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        result = provider.discuss(game, game.players[1])

        assert result == "成功"
        assert provider._sleep.call_count == 2
        provider._sleep.assert_any_call(1)  # 2^0
        provider._sleep.assert_any_call(2)  # 2^1

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_no_retry_on_client_error(self, mock_chat_openai: MagicMock) -> None:
        """クライアントエラー (4xx、429以外) はリトライしない。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = _create_server_error(400)

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        result = provider.discuss(game, game.players[1])

        assert result == FALLBACK_DISCUSS_MESSAGE
        assert mock_instance.invoke.call_count == 1
        provider._sleep.assert_not_called()


class TestFallback:
    """フォールバック動作のテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_discuss_fallback(self, mock_chat_openai: MagicMock) -> None:
        """discuss のフォールバックは定型文を返す。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_api_timeout_error()] * MAX_RETRIES

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        result = provider.discuss(game, game.players[1])

        assert result == FALLBACK_DISCUSS_MESSAGE
        assert mock_instance.invoke.call_count == MAX_RETRIES

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_vote_fallback(self, mock_chat_openai: MagicMock) -> None:
        """vote のフォールバックはランダム選択する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_rate_limit_error()] * MAX_RETRIES

        rng = random.Random(42)
        provider = LLMActionProvider(_create_config(), rng=rng)
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[2], game.players[3])
        result = provider.vote(game, game.players[0], candidates)

        assert result in ("Charlie", "Dave")
        assert mock_instance.invoke.call_count == MAX_RETRIES

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_divine_fallback(self, mock_chat_openai: MagicMock) -> None:
        """divine のフォールバックはランダム選択する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_server_error(503)] * MAX_RETRIES

        rng = random.Random(42)
        provider = LLMActionProvider(_create_config(), rng=rng)
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[1], game.players[2])
        result = provider.divine(game, game.players[0], candidates)

        assert result in ("Bob", "Charlie")
        assert mock_instance.invoke.call_count == MAX_RETRIES

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_attack_fallback(self, mock_chat_openai: MagicMock) -> None:
        """attack のフォールバックはランダム選択する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_api_timeout_error()] * MAX_RETRIES

        rng = random.Random(42)
        provider = LLMActionProvider(_create_config(), rng=rng)
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[0], game.players[1])
        result = provider.attack(game, game.players[2], candidates)

        assert result in ("Alice", "Bob")
        assert mock_instance.invoke.call_count == MAX_RETRIES

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_guard_fallback(self, mock_chat_openai: MagicMock) -> None:
        """guard のフォールバックはランダム選択する。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_api_timeout_error()] * MAX_RETRIES

        rng = random.Random(42)
        provider = LLMActionProvider(_create_config(), rng=rng)
        provider._sleep = MagicMock()
        game = _create_game()
        candidates = (game.players[0], game.players[1])
        result = provider.guard(game, game.players[4], candidates)

        assert result in ("Alice", "Bob")
        assert mock_instance.invoke.call_count == MAX_RETRIES


class TestLogging:
    """ロギング出力のテスト。"""

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_info_log_on_discuss_success(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """discuss 成功時に INFO ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("発言です。")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        with caplog.at_level(logging.INFO, logger="llm_werewolf.engine.llm_provider"):
            provider.discuss(game, game.players[1])  # Bob

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("player=Bob" in m and "action=discuss" in m and "elapsed=" in m for m in info_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_info_log_on_vote_success(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """vote 成功時に INFO ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Charlie")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[2], game.players[3])
        with caplog.at_level(logging.INFO, logger="llm_werewolf.engine.llm_provider"):
            provider.vote(game, game.players[0], candidates)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("player=Alice" in m and "action=vote" in m for m in info_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_info_log_on_divine_success(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """divine 成功時に INFO ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Bob")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[1], game.players[2])
        with caplog.at_level(logging.INFO, logger="llm_werewolf.engine.llm_provider"):
            provider.divine(game, game.players[0], candidates)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("player=Alice" in m and "action=divine" in m for m in info_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_info_log_on_attack_success(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """attack 成功時に INFO ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Alice")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[0], game.players[1])
        with caplog.at_level(logging.INFO, logger="llm_werewolf.engine.llm_provider"):
            provider.attack(game, game.players[2], candidates)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("player=Charlie" in m and "action=attack" in m for m in info_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_info_log_on_guard_success(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """guard 成功時に INFO ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("Alice")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        candidates = (game.players[0], game.players[1])
        with caplog.at_level(logging.INFO, logger="llm_werewolf.engine.llm_provider"):
            provider.guard(game, game.players[4], candidates)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("player=Eve" in m and "action=guard" in m for m in info_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_debug_log_contains_prompt_and_response(
        self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DEBUG ログにプロンプトとレスポンスが含まれる。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("テスト発言")

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        with caplog.at_level(logging.DEBUG, logger="llm_werewolf.engine.llm_provider"):
            provider.discuss(game, game.players[1])

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("LLM プロンプト:" in m for m in debug_messages)
        assert any("LLM レスポンス:" in m and "テスト発言" in m for m in debug_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_debug_log_contains_token_usage(
        self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DEBUG ログにトークン使用量が含まれる。"""
        mock_instance = mock_chat_openai.return_value
        usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        mock_instance.invoke.return_value = _create_mock_response("発言", usage_metadata=usage)

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        with caplog.at_level(logging.DEBUG, logger="llm_werewolf.engine.llm_provider"):
            provider.discuss(game, game.players[1])

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("input=100" in m and "output=50" in m and "total=150" in m for m in debug_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_no_token_log_when_usage_metadata_is_none(
        self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """usage_metadata が None の場合、トークンログは出力されない。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.return_value = _create_mock_response("発言", usage_metadata=None)

        provider = LLMActionProvider(_create_config())
        game = _create_game()
        with caplog.at_level(logging.DEBUG, logger="llm_werewolf.engine.llm_provider"):
            provider.discuss(game, game.players[1])

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert not any("トークン使用量" in m for m in debug_messages)

    @patch("llm_werewolf.engine.llm_provider.ChatOpenAI")
    def test_warning_log_on_fallback(self, mock_chat_openai: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        """フォールバック時に WARNING ログが出力される。"""
        mock_instance = mock_chat_openai.return_value
        mock_instance.invoke.side_effect = [_create_api_timeout_error()] * MAX_RETRIES

        provider = LLMActionProvider(_create_config())
        provider._sleep = MagicMock()
        game = _create_game()
        with caplog.at_level(logging.WARNING, logger="llm_werewolf.engine.llm_provider"):
            provider.discuss(game, game.players[1])

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("フォールバック" in m for m in warning_messages)
