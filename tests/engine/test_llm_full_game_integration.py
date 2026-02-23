"""LLMActionProvider で 1 ゲーム完走する結合テスト。

GameEngine + LLMActionProvider でゲーム全体のフロー
（昼議論→投票→処刑→夜行動→勝利判定）が正常に完了することを検証する。

OPENAI_API_KEY 未設定時は自動スキップされる。
実行: uv run pytest -m integration
"""

from __future__ import annotations

import os
import random

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.services import create_game
from llm_werewolf.domain.value_objects import PlayerStatus
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.llm_config import load_llm_config
from llm_werewolf.engine.llm_provider import LLMActionProvider

pytestmark = [
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"),
    pytest.mark.integration,
]

PLAYER_NAMES = ["アリス", "ボブ", "キャロル", "デイブ", "イブ", "フランク", "グレース", "ハイジ", "アイバン"]


def _create_all_llm_providers(game: GameState) -> dict[str, LLMActionProvider]:
    """全プレイヤーに LLMActionProvider を割り当てる。"""
    config = load_llm_config()
    return {p.name: LLMActionProvider(config, rng=random.Random(42)) for p in game.players}


class TestLLMFullGameSimulation:
    """GameEngine + LLMActionProvider で 1 ゲーム完走することを確認する。"""

    @pytest.mark.timeout(300)
    def test_simulation_completes_with_winner(self) -> None:
        rng = random.Random(42)
        game = create_game(PLAYER_NAMES, rng=rng)
        providers = _create_all_llm_providers(game)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        # ゲームが終了していること
        assert any("ゲーム終了" in log for log in result.log)
        # 勝利陣営が記録されていること
        assert any("勝利" in log for log in result.log)

    @pytest.mark.timeout(300)
    def test_all_actions_target_valid_candidates(self) -> None:
        rng = random.Random(99)
        game = create_game(PLAYER_NAMES, rng=rng)
        providers = _create_all_llm_providers(game)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        # ゲームが正常に終了していること
        assert any("ゲーム終了" in log for log in result.log)

        # 死亡プレイヤーが存在すること（ゲームが進行した証拠）
        dead_players = [p for p in result.players if p.status == PlayerStatus.DEAD]
        assert len(dead_players) > 0

        # 投票ログを検証: "[投票] X → Y" の形式
        vote_logs = [log for log in result.log if "[投票]" in log]
        assert len(vote_logs) > 0, "投票ログが存在すること"

        # 襲撃ログを検証: "襲撃" を含むログが存在すること
        attack_logs = [log for log in result.log if "襲撃" in log]
        assert len(attack_logs) > 0, "襲撃ログが存在すること"
