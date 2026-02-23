import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import NightActionType, Role
from llm_werewolf.engine.game_logic import (
    execute_attack,
    execute_divine,
    execute_guard,
    find_night_actor,
    get_alive_speaking_order,
    get_attack_candidates,
    get_discussion_rounds,
    get_divine_candidates,
    get_guard_candidates,
    get_night_action_candidates,
    notify_divine_result,
    notify_medium_result,
    rotate_speaking_order,
    tally_votes,
)


def _make_game() -> GameState:
    return GameState(
        players=(
            Player(name="Alice", role=Role.SEER),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Dave", role=Role.KNIGHT),
            Player(name="Eve", role=Role.VILLAGER),
            Player(name="Frank", role=Role.MEDIUM),
            Player(name="Grace", role=Role.VILLAGER),
            Player(name="Heidi", role=Role.WEREWOLF),
            Player(name="Ivan", role=Role.MADMAN),
        )
    )


class TestGetAliveSpeakingOrder:
    def test_returns_in_speaking_order(self) -> None:
        game = _make_game()
        order = ("Charlie", "Alice", "Bob", "Eve", "Dave")
        result = get_alive_speaking_order(game, order)
        assert [p.name for p in result] == ["Charlie", "Alice", "Bob", "Eve", "Dave"]

    def test_excludes_dead_players(self) -> None:
        game = _make_game()
        bob = game.players[1]
        game = game.replace_player(bob, bob.killed())
        order = ("Charlie", "Alice", "Bob", "Eve", "Dave")
        result = get_alive_speaking_order(game, order)
        assert "Bob" not in [p.name for p in result]

    def test_empty_order_returns_alive_players(self) -> None:
        game = _make_game()
        result = get_alive_speaking_order(game, ())
        assert len(result) == 9


class TestNotifyDivineResult:
    def test_notifies_on_day2(self) -> None:
        game = _make_game()
        game = GameState(players=game.players, day=2, divined_history=(("Alice", "Charlie"),))
        result = notify_divine_result(game)
        divine_logs = [log for log in result.log if "[占い結果]" in log]
        assert len(divine_logs) == 1
        assert "人狼ではない" in divine_logs[0]

    def test_no_notification_on_day1(self) -> None:
        game = _make_game()
        result = notify_divine_result(game)
        assert not any("[占い結果]" in log for log in result.log)

    def test_no_notification_when_seer_dead(self) -> None:
        game = _make_game()
        alice = game.players[0]
        game = game.replace_player(alice, alice.killed())
        game = GameState(players=game.players, day=2, divined_history=(("Alice", "Charlie"),))
        result = notify_divine_result(game)
        assert not any("[占い結果]" in log for log in result.log)

    def test_no_notification_when_no_history(self) -> None:
        game = _make_game()
        game = GameState(players=game.players, day=2)
        result = notify_divine_result(game)
        assert not any("[占い結果]" in log for log in result.log)


class TestGetDivineCandidates:
    def test_excludes_self_and_divined(self) -> None:
        game = _make_game()
        game = GameState(players=game.players, divined_history=(("Alice", "Charlie"),))
        seer = game.players[0]
        candidates = get_divine_candidates(game, seer)
        names = [p.name for p in candidates]
        assert "Alice" not in names
        assert "Charlie" not in names
        assert "Bob" in names

    def test_empty_when_all_divined(self) -> None:
        game = _make_game()
        game = GameState(
            players=game.players,
            divined_history=(
                ("Alice", "Bob"),
                ("Alice", "Charlie"),
                ("Alice", "Dave"),
                ("Alice", "Eve"),
                ("Alice", "Frank"),
                ("Alice", "Grace"),
                ("Alice", "Heidi"),
                ("Alice", "Ivan"),
            ),
        )
        seer = game.players[0]
        candidates = get_divine_candidates(game, seer)
        assert len(candidates) == 0


class TestExecuteDivine:
    def test_successful_divine(self) -> None:
        game = _make_game()
        seer = game.players[0]
        new_game, result = execute_divine(game, seer, "Bob")
        assert result is not None
        assert result[0] == "Alice"
        assert result[1] == "Bob"
        assert result[2] is True  # Bob is werewolf

    def test_divine_non_werewolf(self) -> None:
        game = _make_game()
        seer = game.players[0]
        _, result = execute_divine(game, seer, "Charlie")
        assert result is not None
        assert result[2] is False

    def test_divine_invalid_target(self) -> None:
        game = _make_game()
        seer = game.players[0]
        _, result = execute_divine(game, seer, "Unknown")
        assert result is None

    def test_divine_self_returns_none(self) -> None:
        game = _make_game()
        seer = game.players[0]
        _, result = execute_divine(game, seer, "Alice")
        assert result is None

    def test_divine_dead_target_returns_none(self) -> None:
        game = _make_game()
        charlie = game.players[2]
        game = game.replace_player(charlie, charlie.killed())
        seer = game.players[0]
        _, result = execute_divine(game, seer, "Charlie")
        assert result is None


class TestGetGuardCandidates:
    def test_excludes_self(self) -> None:
        game = _make_game()
        knight = game.players[3]  # Dave
        candidates = get_guard_candidates(game, knight)
        names = [p.name for p in candidates]
        assert "Dave" not in names
        assert len(names) == 8  # 9 - 1 (self)

    def test_includes_last_guard_target(self) -> None:
        """連続護衛が許可されているため、前回護衛対象も候補に含まれる"""
        game = _make_game()
        game = game.add_guard_history("Dave", "Alice")
        knight = game.players[3]  # Dave
        candidates = get_guard_candidates(game, knight)
        names = [p.name for p in candidates]
        assert "Dave" not in names
        assert "Alice" in names
        assert len(names) == 8  # 9 - 1 (self)


class TestExecuteGuard:
    def test_successful_guard(self) -> None:
        game = _make_game()
        knight = game.players[3]  # Dave
        new_game, target_name = execute_guard(game, knight, "Alice")
        assert target_name == "Alice"
        assert any("[護衛]" in log for log in new_game.log)
        assert new_game.get_last_guard_target("Dave") == "Alice"

    def test_guard_invalid_target(self) -> None:
        game = _make_game()
        knight = game.players[3]
        _, target_name = execute_guard(game, knight, "Unknown")
        assert target_name is None

    def test_guard_self_returns_none(self) -> None:
        game = _make_game()
        knight = game.players[3]
        _, target_name = execute_guard(game, knight, "Dave")
        assert target_name is None

    def test_guard_dead_target_returns_none(self) -> None:
        game = _make_game()
        alice = game.players[0]
        game = game.replace_player(alice, alice.killed())
        knight = game.players[3]
        _, target_name = execute_guard(game, knight, "Alice")
        assert target_name is None

    def test_consecutive_guard_succeeds(self) -> None:
        """連続護衛が許可されているため、前回と同じ対象を護衛できる"""
        game = _make_game()
        game = game.add_guard_history("Dave", "Alice")
        knight = game.players[3]
        new_game, target_name = execute_guard(game, knight, "Alice")
        assert target_name == "Alice"
        assert new_game.get_last_guard_target("Dave") == "Alice"


class TestGetAttackCandidates:
    def test_excludes_werewolves(self) -> None:
        game = _make_game()
        candidates = get_attack_candidates(game)
        for p in candidates:
            assert p.role != Role.WEREWOLF


class TestExecuteAttack:
    def test_successful_attack(self) -> None:
        game = _make_game()
        werewolf = game.players[1]
        _, target_name = execute_attack(game, werewolf, "Charlie")
        assert target_name == "Charlie"

    def test_attack_invalid_target(self) -> None:
        game = _make_game()
        werewolf = game.players[1]
        _, target_name = execute_attack(game, werewolf, "Unknown")
        assert target_name is None

    def test_attack_werewolf_returns_none(self) -> None:
        game = _make_game()
        werewolf = game.players[1]
        _, target_name = execute_attack(game, werewolf, "Bob")
        assert target_name is None

    def test_attack_dead_target_returns_none(self) -> None:
        game = _make_game()
        charlie = game.players[2]
        game = game.replace_player(charlie, charlie.killed())
        werewolf = game.players[1]
        _, target_name = execute_attack(game, werewolf, "Charlie")
        assert target_name is None


class TestNotifyMediumResult:
    def test_notifies_on_day2(self) -> None:
        game = _make_game()
        game = GameState(
            players=game.players,
            day=2,
            medium_results=((1, "Charlie", False),),
        )
        result = notify_medium_result(game)
        medium_logs = [log for log in result.log if "[霊媒結果]" in log]
        assert len(medium_logs) == 1
        assert "人狼ではない" in medium_logs[0]
        assert "Frank" in medium_logs[0]

    def test_notifies_werewolf_result(self) -> None:
        game = _make_game()
        game = GameState(
            players=game.players,
            day=2,
            medium_results=((1, "Bob", True),),
        )
        result = notify_medium_result(game)
        medium_logs = [log for log in result.log if "[霊媒結果]" in log]
        assert len(medium_logs) == 1
        assert "人狼" in medium_logs[0]
        assert "人狼ではない" not in medium_logs[0]

    def test_no_notification_on_day1(self) -> None:
        game = _make_game()
        result = notify_medium_result(game)
        assert not any("[霊媒結果]" in log for log in result.log)

    def test_no_notification_when_medium_dead(self) -> None:
        game = _make_game()
        frank = game.players[5]
        game = game.replace_player(frank, frank.killed())
        game = GameState(
            players=game.players,
            day=2,
            medium_results=((1, "Charlie", False),),
        )
        result = notify_medium_result(game)
        assert not any("[霊媒結果]" in log for log in result.log)

    def test_no_notification_when_no_results(self) -> None:
        game = _make_game()
        game = GameState(players=game.players, day=2)
        result = notify_medium_result(game)
        assert not any("[霊媒結果]" in log for log in result.log)


class TestTallyVotes:
    def test_majority_wins(self) -> None:
        rng = random.Random(42)
        votes = {"Alice": "Bob", "Charlie": "Bob", "Dave": "Alice"}
        result = tally_votes(votes, rng)
        assert result == "Bob"

    def test_empty_votes(self) -> None:
        rng = random.Random(42)
        assert tally_votes({}, rng) is None

    def test_tie_resolved(self) -> None:
        rng = random.Random(42)
        votes = {"Alice": "Bob", "Charlie": "Dave"}
        result = tally_votes(votes, rng)
        assert result in ("Bob", "Dave")

    def test_three_way_tie(self) -> None:
        rng = random.Random(42)
        votes = {"Alice": "Bob", "Charlie": "Dave", "Eve": "Alice"}
        result = tally_votes(votes, rng)
        assert result in ("Bob", "Dave", "Alice")


class TestRotateSpeakingOrder:
    def test_rotates_after_removal(self) -> None:
        order = ("Alice", "Bob", "Charlie", "Dave", "Eve")
        result = rotate_speaking_order(order, "Charlie")
        assert result == ("Dave", "Eve", "Alice", "Bob")
        assert "Charlie" not in result

    def test_no_rotation_if_not_found(self) -> None:
        order = ("Alice", "Bob", "Charlie")
        result = rotate_speaking_order(order, "Unknown")
        assert result == order

    def test_remove_first_player(self) -> None:
        order = ("Alice", "Bob", "Charlie", "Dave")
        result = rotate_speaking_order(order, "Alice")
        assert result == ("Bob", "Charlie", "Dave")

    def test_remove_last_player(self) -> None:
        order = ("Alice", "Bob", "Charlie", "Dave")
        result = rotate_speaking_order(order, "Dave")
        assert result == ("Alice", "Bob", "Charlie")

    def test_empty_order(self) -> None:
        result = rotate_speaking_order((), "Alice")
        assert result == ()


class TestFindNightActor:
    def test_find_seer(self) -> None:
        game = _make_game()
        actor = find_night_actor(game, NightActionType.DIVINE)
        assert actor is not None
        assert actor.name == "Alice"
        assert actor.role == Role.SEER

    def test_find_werewolf(self) -> None:
        game = _make_game()
        actor = find_night_actor(game, NightActionType.ATTACK)
        assert actor is not None
        assert actor.name == "Bob"
        assert actor.role == Role.WEREWOLF

    def test_find_knight(self) -> None:
        game = _make_game()
        actor = find_night_actor(game, NightActionType.GUARD)
        assert actor is not None
        assert actor.name == "Dave"
        assert actor.role == Role.KNIGHT

    def test_returns_none_when_dead(self) -> None:
        game = _make_game()
        alice = game.players[0]
        game = game.replace_player(alice, alice.killed())
        actor = find_night_actor(game, NightActionType.DIVINE)
        assert actor is None


class TestGetNightActionCandidates:
    def test_divine_candidates(self) -> None:
        game = _make_game()
        seer = game.players[0]
        candidates = get_night_action_candidates(game, seer)
        names = [p.name for p in candidates]
        assert "Alice" not in names
        assert "Bob" in names

    def test_attack_candidates(self) -> None:
        game = _make_game()
        werewolf = game.players[1]
        candidates = get_night_action_candidates(game, werewolf)
        for p in candidates:
            assert p.role != Role.WEREWOLF

    def test_guard_candidates(self) -> None:
        game = _make_game()
        knight = game.players[3]  # Dave
        candidates = get_night_action_candidates(game, knight)
        names = [p.name for p in candidates]
        assert "Dave" not in names
        assert "Alice" in names

    def test_villager_returns_empty(self) -> None:
        game = _make_game()
        villager = game.players[2]
        candidates = get_night_action_candidates(game, villager)
        assert len(candidates) == 0


class TestGetDiscussionRounds:
    def test_day1_one_round(self) -> None:
        assert get_discussion_rounds(1) == 1

    def test_day2_two_rounds(self) -> None:
        assert get_discussion_rounds(2) == 2

    def test_day3_two_rounds(self) -> None:
        assert get_discussion_rounds(3) == 2
