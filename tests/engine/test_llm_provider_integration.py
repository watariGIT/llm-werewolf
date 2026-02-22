"""LLMActionProvider の結合テスト（実 API 呼び出し）。

OPENAI_API_KEY 未設定時は自動スキップされる。
実行: uv run pytest -m integration
"""

from __future__ import annotations

import os
import random

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.llm_config import load_llm_config
from llm_werewolf.engine.llm_provider import LLMActionProvider

pytestmark = [
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"),
    pytest.mark.integration,
]

# テスト用プレイヤー名
PLAYER_NAMES = ["アリス", "ボブ", "キャロル", "デイブ", "イブ"]


def _create_players() -> tuple[Player, ...]:
    """固定配役でプレイヤーを生成する。"""
    roles = [Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.SEER, Role.WEREWOLF]
    return tuple(Player(name=name, role=role) for name, role in zip(PLAYER_NAMES, roles))


@pytest.fixture(scope="module")
def provider() -> LLMActionProvider:
    config = load_llm_config()
    return LLMActionProvider(config, rng=random.Random(42))


@pytest.fixture()
def day_game() -> GameState:
    return GameState(players=_create_players(), phase=Phase.DAY, day=1)


@pytest.fixture()
def night_game() -> GameState:
    return GameState(players=_create_players(), phase=Phase.NIGHT, day=1)


class TestDiscuss:
    def test_returns_non_empty_string(self, provider: LLMActionProvider, day_game: GameState) -> None:
        villager = day_game.players[0]  # アリス (村人)
        result = provider.discuss(day_game, villager)

        assert isinstance(result, str)
        assert len(result) > 0


class TestVote:
    def test_returns_candidate_name(self, provider: LLMActionProvider, day_game: GameState) -> None:
        voter = day_game.players[0]  # アリス (村人)
        candidates = tuple(p for p in day_game.alive_players if p.name != voter.name)
        candidate_names = [c.name for c in candidates]

        result = provider.vote(day_game, voter, candidates)

        assert result in candidate_names


class TestDivine:
    def test_returns_candidate_name(self, provider: LLMActionProvider, night_game: GameState) -> None:
        seer = night_game.players[3]  # デイブ (占い師)
        candidates = tuple(p for p in night_game.alive_players if p.name != seer.name)
        candidate_names = [c.name for c in candidates]

        result = provider.divine(night_game, seer, candidates)

        assert result in candidate_names


class TestAttack:
    def test_returns_candidate_name(self, provider: LLMActionProvider, night_game: GameState) -> None:
        werewolf = night_game.players[4]  # イブ (人狼)
        candidates = tuple(p for p in night_game.alive_players if p.name != werewolf.name and p.role != Role.WEREWOLF)
        candidate_names = [c.name for c in candidates]

        result = provider.attack(night_game, werewolf, candidates)

        assert result in candidate_names
