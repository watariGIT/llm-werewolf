import random

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import format_log_for_context
from llm_werewolf.domain.services import create_game
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider


def _run_game(seed: int = 42) -> tuple[list[str], GameState]:
    """テスト用にゲームを実行し、(player_names, game) を返す。"""
    rng = random.Random(seed)
    player_names = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    game = create_game(player_names, rng=rng)
    providers = {p.name: RandomActionProvider(rng=rng) for p in game.players}
    engine = GameEngine(game, providers, rng=rng)
    final = engine.run()
    return player_names, final


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


class TestGuardLogVisibility:
    """護衛ログの可視性テスト"""

    def test_knight_can_see_own_guard_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.KNIGHT),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[護衛] Aliceが Charlieを護衛した",))
        log_text = format_log_for_context(game, "Alice")
        assert "[護衛]" in log_text

    def test_non_knight_cannot_see_guard_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.KNIGHT),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[護衛] Aliceが Charlieを護衛した",))
        for name in ("Bob", "Charlie"):
            log_text = format_log_for_context(game, name)
            assert "[護衛]" not in log_text


class TestMediumResultLogVisibility:
    """霊媒結果ログの可視性テスト"""

    def test_medium_can_see_own_medium_result_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.MEDIUM),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[霊媒結果] Aliceの霊媒: Bobは人狼だった",))
        log_text = format_log_for_context(game, "Alice")
        assert "[霊媒結果]" in log_text

    def test_non_medium_cannot_see_medium_result_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.MEDIUM),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[霊媒結果] Aliceの霊媒: Bobは人狼だった",))
        for name in ("Bob", "Charlie"):
            log_text = format_log_for_context(game, name)
            assert "[霊媒結果]" not in log_text


class TestWerewolfAllyLogVisibility:
    """人狼仲間ログの可視性テスト"""

    def test_werewolf_can_see_ally_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.WEREWOLF),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[人狼仲間] 人狼はAlice, Bobです",))
        for name in ("Alice", "Bob"):
            log_text = format_log_for_context(game, name)
            assert "[人狼仲間]" in log_text

    def test_non_werewolf_cannot_see_ally_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.WEREWOLF),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Diana", role=Role.SEER),
            Player(name="Eve", role=Role.MADMAN),
        )
        game = GameState(players=players, log=("[人狼仲間] 人狼はAlice, Bobです",))
        for name in ("Charlie", "Diana", "Eve"):
            log_text = format_log_for_context(game, name)
            assert "[人狼仲間]" not in log_text
