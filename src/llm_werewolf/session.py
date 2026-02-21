"""ゲームセッション管理（インフラ層）。

インメモリ辞書でゲーム状態を保持し、リクエスト間で GameState を引き継ぐ。
"""

from __future__ import annotations

import random
import uuid

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.services import create_game
from llm_werewolf.engine.action_provider import ActionProvider
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider


class GameSessionStore:
    """ゲームセッションのインメモリストア。"""

    def __init__(self) -> None:
        self._sessions: dict[str, GameState] = {}

    def create(self, player_names: list[str], rng: random.Random | None = None) -> tuple[str, GameState]:
        """新規ゲームを作成し、一括実行して結果を保存する。

        Args:
            player_names: プレイヤー名リスト（5人）
            rng: テスト用の乱数生成器

        Returns:
            (ゲームID, 最終GameState) のタプル
        """
        game_id = uuid.uuid4().hex[:8]
        initial_state = create_game(player_names, rng=rng)

        # 全プレイヤーに RandomActionProvider を割り当て
        providers: dict[str, ActionProvider] = {p.name: RandomActionProvider(rng=rng) for p in initial_state.players}
        engine = GameEngine(initial_state, providers, rng=rng)
        final_state = engine.run()

        self._sessions[game_id] = final_state
        return game_id, final_state

    def get(self, game_id: str) -> GameState | None:
        """ゲーム状態を取得する。"""
        return self._sessions.get(game_id)

    def save(self, game_id: str, game: GameState) -> None:
        """ゲーム状態を保存（上書き）する。"""
        self._sessions[game_id] = game

    def delete(self, game_id: str) -> None:
        """セッションを削除する。"""
        self._sessions.pop(game_id, None)

    def list_sessions(self) -> dict[str, GameState]:
        """全セッションを返す。"""
        return dict(self._sessions)
