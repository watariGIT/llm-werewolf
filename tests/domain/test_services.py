import random
from collections import Counter

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import (
    assign_roles,
    can_guard,
    check_victory,
    create_game,
    create_game_with_role,
)
from llm_werewolf.domain.value_objects import PlayerStatus, Role, Team

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"]


class TestAssignRoles:
    def test_returns_nine_players(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        assert len(players) == 9

    def test_role_composition(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        role_counts = Counter(p.role for p in players)
        assert role_counts[Role.VILLAGER] == 3
        assert role_counts[Role.SEER] == 1
        assert role_counts[Role.WEREWOLF] == 2
        assert role_counts[Role.KNIGHT] == 1
        assert role_counts[Role.MEDIUM] == 1
        assert role_counts[Role.MADMAN] == 1

    def test_names_preserved(self) -> None:
        players = assign_roles(PLAYER_NAMES)
        assert [p.name for p in players] == PLAYER_NAMES

    def test_deterministic_with_seed(self) -> None:
        players1 = assign_roles(PLAYER_NAMES, rng=random.Random(42))
        players2 = assign_roles(PLAYER_NAMES, rng=random.Random(42))
        assert [p.role for p in players1] == [p.role for p in players2]

    def test_invalid_player_count(self) -> None:
        with pytest.raises(ValueError, match="Player count must be 9"):
            assign_roles(["Alice", "Bob"])

    def test_duplicate_names_rejected(self) -> None:
        with pytest.raises(ValueError, match="player_names must be unique"):
            assign_roles(["Alice"] * 9)


class TestCreateGame:
    def test_returns_game_state(self) -> None:
        game = create_game(PLAYER_NAMES)
        assert isinstance(game, GameState)
        assert len(game.players) == 9


class TestCreateGameWithRole:
    def test_fixed_role_knight(self) -> None:
        game = create_game_with_role(PLAYER_NAMES, "Alice", Role.KNIGHT)
        alice = game.find_player("Alice")
        assert alice is not None
        assert alice.role == Role.KNIGHT

    def test_fixed_role_medium(self) -> None:
        game = create_game_with_role(PLAYER_NAMES, "Bob", Role.MEDIUM)
        bob = game.find_player("Bob")
        assert bob is not None
        assert bob.role == Role.MEDIUM

    def test_fixed_role_madman(self) -> None:
        game = create_game_with_role(PLAYER_NAMES, "Charlie", Role.MADMAN)
        charlie = game.find_player("Charlie")
        assert charlie is not None
        assert charlie.role == Role.MADMAN

    def test_remaining_roles_correct(self) -> None:
        game = create_game_with_role(PLAYER_NAMES, "Alice", Role.KNIGHT)
        role_counts = Counter(p.role for p in game.players)
        assert role_counts[Role.KNIGHT] == 1
        assert role_counts[Role.WEREWOLF] == 2
        assert sum(role_counts.values()) == 9


class TestCheckVictory:
    def test_village_wins_when_all_werewolves_dead(self) -> None:
        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.KNIGHT),
            Player(name="Eve", role=Role.MEDIUM),
            Player(name="Frank", role=Role.MADMAN),
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF, status=PlayerStatus.DEAD),
            Player(name="Ivan", role=Role.WEREWOLF, status=PlayerStatus.DEAD),
        )
        game = GameState(players=players)
        assert check_victory(game) == Team.VILLAGE

    def test_werewolf_wins_when_villagers_lte_werewolves(self) -> None:
        players = (
            Player(name="Alice", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Bob", role=Role.SEER, status=PlayerStatus.DEAD),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.KNIGHT, status=PlayerStatus.DEAD),
            Player(name="Eve", role=Role.MEDIUM, status=PlayerStatus.DEAD),
            Player(name="Frank", role=Role.MADMAN, status=PlayerStatus.DEAD),
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        assert check_victory(game) == Team.WEREWOLF

    def test_madman_counted_as_non_werewolf_in_victory_check(self) -> None:
        """狂人は人狼ではないため、勝利判定では人狼以外の生存者としてカウントされる。"""
        players = (
            Player(name="Alice", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Bob", role=Role.SEER, status=PlayerStatus.DEAD),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.KNIGHT, status=PlayerStatus.DEAD),
            Player(name="Eve", role=Role.MEDIUM, status=PlayerStatus.DEAD),
            Player(name="Frank", role=Role.MADMAN),  # 狂人は人狼ではない
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.WEREWOLF, status=PlayerStatus.DEAD),
        )
        game = GameState(players=players)
        # 人狼以外の生存者: Frank + Grace = 2人, 人狼生存: Heidi = 1人 → ゲーム続行
        assert check_victory(game) is None

    def test_madman_with_two_werewolves_ongoing(self) -> None:
        """狂人1 + 人狼2 + 村人2 = 人狼以外3人 > 人狼2人 → ゲーム続行。"""
        players = (
            Player(name="Alice", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Bob", role=Role.SEER, status=PlayerStatus.DEAD),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.KNIGHT, status=PlayerStatus.DEAD),
            Player(name="Eve", role=Role.MEDIUM),
            Player(name="Frank", role=Role.MADMAN),
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        # 人狼以外の生存者: Eve + Frank + Grace = 3人, 人狼: Heidi + Ivan = 2人 → ゲーム続行
        assert check_victory(game) is None

    def test_werewolf_wins_with_madman_alive(self) -> None:
        """狂人1 + 人狼2 + 村人1 = 人狼以外2人 ≦ 人狼2人 → 人狼勝利。"""
        players = (
            Player(name="Alice", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Bob", role=Role.SEER, status=PlayerStatus.DEAD),
            Player(name="Charlie", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Dave", role=Role.KNIGHT, status=PlayerStatus.DEAD),
            Player(name="Eve", role=Role.MEDIUM, status=PlayerStatus.DEAD),
            Player(name="Frank", role=Role.MADMAN),
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        # 人狼以外の生存者: Frank + Grace = 2人, 人狼: Heidi + Ivan = 2人 → 人狼勝利
        assert check_victory(game) == Team.WEREWOLF

    def test_ongoing_game(self) -> None:
        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.SEER),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.KNIGHT),
            Player(name="Eve", role=Role.MEDIUM),
            Player(name="Frank", role=Role.MADMAN),
            Player(name="Grace", role=Role.VILLAGER, status=PlayerStatus.DEAD),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.WEREWOLF),
        )
        game = GameState(players=players)
        assert check_victory(game) is None

    def test_initial_state(self) -> None:
        game = create_game(PLAYER_NAMES)
        assert check_victory(game) is None


class TestCanGuard:
    def _make_game(self) -> GameState:
        return GameState(
            players=(
                Player(name="Alice", role=Role.KNIGHT),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.SEER),
                Player(name="Eve", role=Role.VILLAGER),
                Player(name="Frank", role=Role.MEDIUM),
                Player(name="Grace", role=Role.VILLAGER),
                Player(name="Heidi", role=Role.WEREWOLF),
                Player(name="Ivan", role=Role.MADMAN),
            )
        )

    def test_valid_guard(self) -> None:
        game = self._make_game()
        knight = game.players[0]
        target = game.players[2]
        can_guard(game, knight, target)  # no exception

    def test_not_knight_raises(self) -> None:
        game = self._make_game()
        villager = game.players[2]
        target = game.players[3]
        with pytest.raises(ValueError, match="is not a knight"):
            can_guard(game, villager, target)

    def test_dead_knight_raises(self) -> None:
        game = self._make_game()
        knight = game.players[0]
        dead_knight = knight.killed()
        game = game.replace_player(knight, dead_knight)
        target = game.players[2]
        with pytest.raises(ValueError, match="is dead and cannot guard"):
            can_guard(game, dead_knight, target)

    def test_dead_target_raises(self) -> None:
        game = self._make_game()
        knight = game.players[0]
        charlie = game.players[2]
        dead_charlie = charlie.killed()
        game = game.replace_player(charlie, dead_charlie)
        with pytest.raises(ValueError, match="is dead and cannot be guarded"):
            can_guard(game, knight, dead_charlie)

    def test_self_guard_raises(self) -> None:
        game = self._make_game()
        knight = game.players[0]
        with pytest.raises(ValueError, match="cannot guard themselves"):
            can_guard(game, knight, knight)

    def test_consecutive_guard_allowed(self) -> None:
        """連続で同じ対象を護衛できる"""
        game = self._make_game()
        game = game.add_guard_history("Alice", "Charlie")
        knight = game.players[0]
        target = game.players[2]  # Charlie
        can_guard(game, knight, target)  # no exception
