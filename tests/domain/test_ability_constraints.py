import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import can_attack, can_divine
from llm_werewolf.domain.value_objects import Role


@pytest.fixture
def game() -> GameState:
    """役職が確定したゲーム状態"""
    players = [
        Player(name="Alice", role=Role.SEER),
        Player(name="Bob", role=Role.VILLAGER),
        Player(name="Charlie", role=Role.VILLAGER),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.WEREWOLF),
    ]
    return GameState(players=players)


class TestCanDivine:
    def test_valid_divine(self, game: GameState) -> None:
        """正常系: 占い師が有効な対象を占える"""
        can_divine(game, game.players[0], game.players[1])

    def test_cannot_divine_themselves(self, game: GameState) -> None:
        """占い師は自分自身を占えない"""
        seer = game.players[0]
        with pytest.raises(ValueError, match="cannot divine themselves"):
            can_divine(game, seer, seer)

    def test_cannot_divine_same_target_twice(self, game: GameState) -> None:
        """同じ対象を複数回占えない"""
        seer = game.players[0]
        target = game.players[1]
        can_divine(game, seer, target)
        game.add_divine_history(seer.name, target.name)

        with pytest.raises(ValueError, match="has already divined"):
            can_divine(game, seer, target)

    def test_can_divine_different_targets(self, game: GameState) -> None:
        """異なる対象を順次占える"""
        seer = game.players[0]
        can_divine(game, seer, game.players[1])
        game.add_divine_history(seer.name, game.players[1].name)

        can_divine(game, seer, game.players[2])

    def test_dead_seer_cannot_divine(self, game: GameState) -> None:
        """死亡した占い師は占えない"""
        seer = game.players[0]
        seer.kill()

        with pytest.raises(ValueError, match="is dead and cannot divine"):
            can_divine(game, seer, game.players[1])

    def test_cannot_divine_dead_target(self, game: GameState) -> None:
        """死亡した対象は占えない"""
        target = game.players[1]
        target.kill()

        with pytest.raises(ValueError, match="is dead and cannot be divined"):
            can_divine(game, game.players[0], target)

    def test_non_seer_cannot_divine(self, game: GameState) -> None:
        """占い師以外は占えない"""
        with pytest.raises(ValueError, match="is not a seer"):
            can_divine(game, game.players[1], game.players[2])

    def test_target_not_in_game(self, game: GameState) -> None:
        """ゲーム外のプレイヤーは占えない"""
        outsider = Player(name="Frank", role=Role.VILLAGER)
        with pytest.raises(ValueError, match="is not in the game"):
            can_divine(game, game.players[0], outsider)


class TestCanAttack:
    def test_valid_attack(self, game: GameState) -> None:
        """正常系: 人狼が村人を襲撃できる"""
        can_attack(game, game.players[4], game.players[1])

    def test_cannot_attack_themselves(self, game: GameState) -> None:
        """人狼は自分自身を襲撃できない"""
        werewolf = game.players[4]
        with pytest.raises(ValueError, match="cannot attack themselves"):
            can_attack(game, werewolf, werewolf)

    def test_cannot_attack_another_werewolf(self) -> None:
        """人狼は他の人狼を襲撃できない"""
        players = [
            Player(name="Alice", role=Role.SEER),
            Player(name="Bob", role=Role.VILLAGER),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.WEREWOLF),
            Player(name="Eve", role=Role.WEREWOLF),
        ]
        game = GameState(players=players)

        with pytest.raises(ValueError, match="cannot attack another werewolf"):
            can_attack(game, game.players[3], game.players[4])

    def test_dead_werewolf_cannot_attack(self, game: GameState) -> None:
        """死亡した人狼は襲撃できない"""
        werewolf = game.players[4]
        werewolf.kill()

        with pytest.raises(ValueError, match="is dead and cannot attack"):
            can_attack(game, werewolf, game.players[1])

    def test_cannot_attack_dead_target(self, game: GameState) -> None:
        """死亡した対象は襲撃できない"""
        target = game.players[1]
        target.kill()

        with pytest.raises(ValueError, match="is dead and cannot be attacked"):
            can_attack(game, game.players[4], target)

    def test_non_werewolf_cannot_attack(self, game: GameState) -> None:
        """人狼以外は襲撃できない"""
        with pytest.raises(ValueError, match="is not a werewolf"):
            can_attack(game, game.players[1], game.players[2])

    def test_target_not_in_game(self, game: GameState) -> None:
        """ゲーム外のプレイヤーは襲撃できない"""
        outsider = Player(name="Frank", role=Role.VILLAGER)
        with pytest.raises(ValueError, match="is not in the game"):
            can_attack(game, game.players[4], outsider)

    def test_can_attack_seer(self, game: GameState) -> None:
        """人狼は占い師を襲撃できる"""
        can_attack(game, game.players[4], game.players[0])


class TestDivineHistory:
    def test_initial_history_is_empty(self, game: GameState) -> None:
        """初期状態では占い履歴が空"""
        assert game.get_divined_history("Alice") == []

    def test_add_and_get_history(self, game: GameState) -> None:
        """占い履歴の追加と取得"""
        game.add_divine_history("Alice", "Bob")
        game.add_divine_history("Alice", "Charlie")
        assert game.get_divined_history("Alice") == ["Bob", "Charlie"]

    def test_default_divined_history(self, game: GameState) -> None:
        """divined_history のデフォルト値は空の dict"""
        assert game.divined_history == {}
