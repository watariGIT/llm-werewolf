"""プロンプトテンプレートのテスト。"""

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.prompts import (
    build_attack_prompt,
    build_discuss_prompt,
    build_divine_prompt,
    build_system_prompt,
    build_vote_prompt,
)


def _create_game() -> GameState:
    """テスト用のゲーム状態を作成する。"""
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


class TestBuildSystemPrompt:
    """build_system_prompt のテスト。"""

    def test_villager_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.VILLAGER)
        assert "村人" in result
        assert "特殊能力はありません" in result

    def test_seer_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.SEER)
        assert "占い師" in result
        assert "占い結果を活用" in result

    def test_werewolf_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.WEREWOLF)
        assert "人狼" in result
        assert "村人のふりをして" in result

    def test_all_roles_contain_base_rules(self) -> None:
        for role in Role:
            result = build_system_prompt(role)
            assert "人狼ゲーム" in result
            assert "日本語" in result
            assert "投票は公開" in result

    def test_all_roles_contain_glossary_terms(self) -> None:
        for role in Role:
            result = build_system_prompt(role)
            assert "黒" in result
            assert "白" in result
            assert "処刑" in result
            assert "襲撃" in result
            assert "占い" in result


class TestBuildDiscussPrompt:
    """build_discuss_prompt のテスト。"""

    def test_contains_player_name(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "Bob" in result

    def test_contains_game_context(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "1日目" in result
        assert "昼" in result
        assert "生存者" in result

    def test_contains_discussion_instruction(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "発言内容を返してください" in result

    def test_contains_game_log(self) -> None:
        game = _create_game()
        game = game.add_log("[議論] Bob: おはようございます")
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "おはようございます" in result

    def test_seer_sees_own_role_log(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice (seer)
        result = build_discuss_prompt(game, player)
        assert "Alice は占い師です" in result

    def test_villager_does_not_see_other_role_log(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob (villager)
        result = build_discuss_prompt(game, player)
        assert "Alice は占い師です" not in result
        assert "Bob は村人です" in result


class TestBuildVotePrompt:
    """build_vote_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice
        candidates = (game.players[1], game.players[2], game.players[3], game.players[4])
        result = build_vote_prompt(game, player, candidates)
        assert "- Bob" in result
        assert "- Charlie" in result
        assert "- Dave" in result
        assert "- Eve" in result

    def test_contains_vote_instruction(self) -> None:
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "投票先の名前のみを返してください" in result

    def test_contains_player_name(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "Alice" in result


class TestBuildDivinePrompt:
    """build_divine_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        seer = game.players[0]  # Alice (seer)
        candidates = (game.players[1], game.players[2])
        result = build_divine_prompt(game, seer, candidates)
        assert "- Bob" in result
        assert "- Charlie" in result

    def test_contains_divine_instruction(self) -> None:
        game = _create_game()
        seer = game.players[0]
        candidates = (game.players[1],)
        result = build_divine_prompt(game, seer, candidates)
        assert "占い対象の名前のみを返してください" in result

    def test_contains_seer_role_label(self) -> None:
        game = _create_game()
        seer = game.players[0]
        candidates = (game.players[1],)
        result = build_divine_prompt(game, seer, candidates)
        assert "占い師" in result


class TestBuildAttackPrompt:
    """build_attack_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        werewolf = game.players[2]  # Charlie (werewolf)
        candidates = (game.players[0], game.players[1])
        result = build_attack_prompt(game, werewolf, candidates)
        assert "- Alice" in result
        assert "- Bob" in result

    def test_contains_attack_instruction(self) -> None:
        game = _create_game()
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "襲撃対象の名前のみを返してください" in result

    def test_contains_werewolf_role_label(self) -> None:
        game = _create_game()
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "人狼" in result

    def test_night_phase_context(self) -> None:
        game = _create_game()
        from dataclasses import replace

        game = replace(game, phase=Phase.NIGHT)
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "夜" in result
