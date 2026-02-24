"""GM-AI（GameMasterProvider）のテスト。"""

from __future__ import annotations

from unittest.mock import patch

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.game_master import (
    AdviceOption,
    GameAnalysis,
    GameMasterProvider,
    PlayerSummary,
    RoleAdvice,
    RoleClaim,
    extract_board_info,
)
from llm_werewolf.engine.llm_config import LLMConfig


def _create_game_with_log() -> GameState:
    """投票・処刑・襲撃を含むゲーム状態を作成する。"""
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
    game = GameState(players=players, phase=Phase.DAY, day=2)

    # Day 1 ログ
    game = game.add_log("--- Day 1 （昼フェーズ） ---")
    game = game.add_log("[議論] ラウンド 1")
    game = game.add_log("[発言] Alice: 私は占い師です。")
    game = game.add_log("[発言] Bob: 怪しいのは Charlie だと思う。")
    game = game.add_log("[投票] Alice → Charlie")
    game = game.add_log("[投票] Bob → Charlie")
    game = game.add_log("[投票] Charlie → Alice")
    game = game.add_log("[投票] Dave → Charlie")
    game = game.add_log("[投票] Eve → Charlie")
    game = game.add_log("[投票] Frank → Alice")
    game = game.add_log("[投票] Grace → Alice")
    game = game.add_log("[投票] Heidi → Alice")
    game = game.add_log("[投票] Ivan → Charlie")
    game = game.add_log("[処刑] Charlie が処刑された（得票数: 5）")

    # Night 1 ログ
    game = game.add_log("--- Night 1 （夜フェーズ） ---")
    game = game.add_log("[襲撃] Bob が人狼に襲撃された")

    # Charlie と Bob を死亡に
    charlie = game.find_player("Charlie")
    if charlie:
        game = game.replace_player(charlie, charlie.killed())
    bob = game.find_player("Bob")
    if bob:
        game = game.replace_player(bob, bob.killed())

    return game


class TestExtractBoardInfo:
    """extract_board_info のテスト。"""

    def test_extracts_alive_players(self) -> None:
        game = _create_game_with_log()
        alive, dead, vote_history = extract_board_info(game)

        assert "Alice" in alive
        assert "Dave" in alive
        assert "Charlie" not in alive
        assert "Bob" not in alive

    def test_extracts_dead_players(self) -> None:
        game = _create_game_with_log()
        alive, dead, vote_history = extract_board_info(game)

        dead_names = {d.name for d in dead}
        assert "Charlie" in dead_names
        assert "Bob" in dead_names

        charlie_info = next(d for d in dead if d.name == "Charlie")
        assert charlie_info.cause == "execution"
        assert charlie_info.day == 1

        bob_info = next(d for d in dead if d.name == "Bob")
        assert bob_info.cause == "attack"
        assert bob_info.day == 1

    def test_extracts_vote_history(self) -> None:
        game = _create_game_with_log()
        alive, dead, vote_history = extract_board_info(game)

        assert len(vote_history) == 1
        day1_votes = vote_history[0]
        assert day1_votes.day == 1
        assert day1_votes.executed == "Charlie"
        assert day1_votes.votes["Alice"] == "Charlie"
        assert day1_votes.votes["Charlie"] == "Alice"

    def test_empty_log(self) -> None:
        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        alive, dead, vote_history = extract_board_info(game)

        assert alive == ["Alice", "Bob"]
        assert dead == []
        assert vote_history == []

    def test_no_match_for_guard_success(self) -> None:
        """護衛成功のログは死亡者に含まれない。"""
        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        game = game.add_log("--- Day 1 （昼フェーズ） ---")
        game = game.add_log("[襲撃] 今夜は誰も襲撃されなかった")
        alive, dead, vote_history = extract_board_info(game)

        assert dead == []


class TestGameMasterProviderSummarize:
    """GameMasterProvider.summarize のテスト（LLM をモック）。"""

    def test_summarize_returns_json_string(self) -> None:
        game = _create_game_with_log()
        config = LLMConfig(model_name="test-model", temperature=0.3, api_key="sk-test")

        mock_analysis = GameAnalysis(
            claims=[RoleClaim(player="Alice", claimed_role="占い師", day=1)],
            contradictions=["Grace が占い師COしたが、Alice もCOしている"],
            player_summaries=[PlayerSummary(name="Alice", summary="占い師COした")],
        )

        provider = GameMasterProvider(config)

        with patch.object(provider, "_call_llm_analysis", return_value=mock_analysis):
            result = provider.summarize(game)

        import json

        data = json.loads(result)
        assert "alive" in data
        assert "dead" in data
        assert "vote_history" in data
        assert "claims" in data
        assert len(data["claims"]) == 1
        assert data["claims"][0]["player"] == "Alice"

    def test_summarize_includes_role_advice(self) -> None:
        """role_advice が JSON に含まれることを確認する。"""
        game = _create_game_with_log()
        config = LLMConfig(model_name="test-model", temperature=0.3, api_key="sk-test")

        mock_analysis = GameAnalysis(
            role_advice=[
                RoleAdvice(
                    role="占い師",
                    options=[
                        AdviceOption(
                            action="Dave を占う",
                            merit="情報が少ないプレイヤーの白黒が判明する",
                            demerit="Grace を放置するリスクがある",
                        ),
                        AdviceOption(
                            action="Grace を占う",
                            merit="怪しいプレイヤーを確認できる",
                            demerit="他の候補を見逃す可能性がある",
                        ),
                    ],
                ),
            ],
        )

        provider = GameMasterProvider(config)

        with patch.object(provider, "_call_llm_analysis", return_value=mock_analysis):
            result = provider.summarize(game)

        import json

        data = json.loads(result)
        assert "role_advice" in data
        assert len(data["role_advice"]) == 1
        assert data["role_advice"][0]["role"] == "占い師"
        assert len(data["role_advice"][0]["options"]) == 2
        assert data["role_advice"][0]["options"][0]["action"] == "Dave を占う"

    def test_summarize_works_when_llm_fails(self) -> None:
        """LLM が失敗しても確定情報だけで JSON を返す。"""
        game = _create_game_with_log()
        config = LLMConfig(model_name="test-model", temperature=0.3, api_key="sk-test")

        provider = GameMasterProvider(config)

        with patch.object(provider, "_call_llm_analysis", return_value=None):
            result = provider.summarize(game)

        import json

        data = json.loads(result)
        assert "alive" in data
        assert "dead" in data
        assert data["claims"] == []
        assert data["contradictions"] == []
        assert data["player_summaries"] == []
        assert data["role_advice"] == []

    def test_token_usage_tracked(self) -> None:
        game = _create_game_with_log()
        config = LLMConfig(model_name="test-model", temperature=0.3, api_key="sk-test")

        mock_analysis = GameAnalysis()
        provider = GameMasterProvider(config)

        def fake_call_llm_analysis(g: GameState) -> GameAnalysis:
            provider.last_input_tokens = 200
            provider.last_output_tokens = 100
            provider.last_cache_read_input_tokens = 50
            return mock_analysis

        with patch.object(provider, "_call_llm_analysis", side_effect=fake_call_llm_analysis):
            provider.summarize(game)

        assert provider.last_input_tokens == 200
        assert provider.last_output_tokens == 100
        assert provider.last_cache_read_input_tokens == 50
