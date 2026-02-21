import random

import pytest

from llm_werewolf.domain.game_log import format_log_for_context
from llm_werewolf.domain.services import create_game
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider


def _run_game(seed: int = 42) -> tuple[list[str], ...]:
    """テスト用にゲームを実行し、(player_names, game) を返す。"""
    rng = random.Random(seed)
    player_names = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    game = create_game(player_names, rng=rng)
    providers = {p.name: RandomActionProvider(rng=rng) for p in game.players}
    engine = GameEngine(game, providers, rng=rng)
    final = engine.run()
    return player_names, final  # type: ignore[return-value]


class TestFormatLogForContext:
    def test_raises_for_unknown_player(self) -> None:
        _, game = _run_game()
        with pytest.raises(ValueError, match="Player 'Unknown' not found"):
            format_log_for_context(game, "Unknown")

    def test_villager_cannot_see_others_role_assignment(self) -> None:
        _, game = _run_game()
        # 村人を探す
        from llm_werewolf.domain.value_objects import Role

        villager = next(p for p in game.players if p.role == Role.VILLAGER)
        log_text = format_log_for_context(game, villager.name)

        # 自分の配役は見える
        assert f"[配役] {villager.name}" in log_text

        # 他のプレイヤーの配役は見えない
        for p in game.players:
            if p.name != villager.name:
                assert f"[配役] {p.name}" not in log_text

    def test_seer_can_see_divine_logs(self) -> None:
        _, game = _run_game()
        from llm_werewolf.domain.value_objects import Role

        seer = next(p for p in game.players if p.role == Role.SEER)
        log_text = format_log_for_context(game, seer.name)

        # 占い師は占いログが見える
        if "[占い]" in "\n".join(game.log):
            assert "[占い]" in log_text

    def test_non_seer_cannot_see_divine_logs(self) -> None:
        _, game = _run_game()
        from llm_werewolf.domain.value_objects import Role

        non_seer = next(p for p in game.players if p.role != Role.SEER)
        log_text = format_log_for_context(game, non_seer.name)

        # 占い師以外は占いログが見えない
        assert "[占い]" not in log_text
        assert "[占い結果]" not in log_text

    def test_all_players_can_see_discussion_and_vote(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "[発言]" in log_text
            assert "[投票]" in log_text

    def test_all_players_can_see_game_start_and_end(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "=== ゲーム開始 ===" in log_text
            assert "=== ゲーム終了" in log_text

    def test_all_players_can_see_execution(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "[処刑]" in log_text
