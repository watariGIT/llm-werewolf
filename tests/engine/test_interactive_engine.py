import random

import pytest

from llm_werewolf.domain.services import create_game, create_game_with_role
from llm_werewolf.domain.value_objects import NightActionType, Phase, Role, Team
from llm_werewolf.engine.interactive_engine import InteractiveGameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider

AI_NAMES = ["AI-1", "AI-2", "AI-3", "AI-4", "AI-5", "AI-6", "AI-7", "AI-8"]


def _create_engine(
    seed: int = 42,
    human_name: str = "Alice",
    role: Role | None = None,
) -> InteractiveGameEngine:
    """テスト用にseed固定でエンジンを生成する。"""
    rng = random.Random(seed)
    all_names = [human_name] + AI_NAMES
    if role is not None:
        game = create_game_with_role(all_names, human_name, role, rng=rng)
    else:
        game = create_game(all_names, rng=rng)

    game = game.add_log("=== ゲーム開始 ===")
    for p in game.players:
        game = game.add_log(f"[配役] {p.name}: {p.role.value}")

    providers = {name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES}
    speaking_order = tuple(rng.sample(all_names, len(all_names)))

    return InteractiveGameEngine(
        game=game,
        providers=providers,
        human_player_name=human_name,
        rng=rng,
        speaking_order=speaking_order,
    )


def _create_engine_with_dead_human(
    seed: int = 42,
    human_name: str = "Alice",
    role: Role = Role.VILLAGER,
) -> InteractiveGameEngine:
    """ユーザーが死亡済みのエンジンを生成する。"""
    engine = _create_engine(seed=seed, human_name=human_name, role=role)
    game = engine.game
    human = next(p for p in game.players if p.name == human_name)
    game = game.replace_player(human, human.killed())
    return InteractiveGameEngine(
        game=game,
        providers={name: RandomActionProvider(rng=random.Random(seed)) for name in AI_NAMES},
        human_player_name=human_name,
        rng=random.Random(seed),
        speaking_order=engine.speaking_order,
    )


class TestAdvanceDiscussion:
    def test_returns_ai_messages(self) -> None:
        engine = _create_engine()
        msgs = engine.advance_discussion()
        assert isinstance(msgs, list)
        assert engine.discussion_round == 1

    def test_adds_day_log(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        assert any("昼フェーズ" in log for log in engine.game.log)

    def test_adds_round_log(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        assert any("ラウンド 1" in log for log in engine.game.log)

    def test_user_dead_all_ai_discuss(self) -> None:
        engine = _create_engine_with_dead_human()
        msgs = engine.advance_discussion()
        assert len(msgs) > 0
        assert all("Alice" not in msg for msg in msgs)


class TestHandleUserDiscuss:
    def test_day1_one_round_returns_vote_ready(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        msgs, vote_ready = engine.handle_user_discuss("テスト発言")
        assert vote_ready is True

    def test_records_user_message(self) -> None:
        engine = _create_engine(human_name="Alice")
        engine.advance_discussion()
        msgs, _ = engine.handle_user_discuss("怪しいのは誰だ")
        assert any("[発言] Alice: 怪しいのは誰だ" in log for log in engine.game.log)

    def test_day2_first_round_not_vote_ready(self) -> None:
        """Day 2 ではラウンド1の後に vote_ready=False が返る。"""
        for seed in range(50):
            engine = _create_engine(seed=seed)
            engine.advance_discussion()
            _, vote_ready = engine.handle_user_discuss("test")

            # 投票→処刑→夜→Day2 まで進める
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            votes, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue

            has_action = engine.start_night()
            if has_action:
                night_cands = engine.get_night_action_candidates()
                action_type = engine.get_night_action_type()
                if night_cands:
                    engine.resolve_night(
                        human_divine_target=night_cands[0].name if action_type == NightActionType.DIVINE else None,
                        human_attack_target=night_cands[0].name if action_type == NightActionType.ATTACK else None,
                        human_guard_target=night_cands[0].name if action_type == NightActionType.GUARD else None,
                    )
                else:
                    engine.resolve_night()
            else:
                engine.resolve_night()

            if engine.game.day < 2:
                continue

            # Day 2 の議論
            engine.advance_discussion()
            _, vote_ready = engine.handle_user_discuss("Day2 ラウンド1")
            assert vote_ready is False
            assert engine.discussion_round == 2
            return

        pytest.skip("No seed found for day2 test")

    def test_user_dead_skips_user_message(self) -> None:
        engine = _create_engine_with_dead_human()
        engine.advance_discussion()
        msgs, vote_ready = engine.handle_user_discuss("テスト発言")
        assert not any("[発言] Alice" in log for log in engine.game.log)


class TestHandleUserVote:
    def test_returns_votes_and_winner(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        votes, winner = engine.handle_user_vote(candidates[0].name)
        assert len(votes) > 0
        assert winner is None or isinstance(winner, Team)

    def test_records_vote_logs(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        engine.handle_user_vote(candidates[0].name)
        vote_logs = [log for log in engine.game.log if "[投票]" in log]
        assert len(vote_logs) > 0


class TestHandleAutoVote:
    def test_returns_votes(self) -> None:
        engine = _create_engine()
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        votes, _ = engine.handle_auto_vote()
        assert len(votes) > 0


class TestStartNight:
    def test_seer_gets_night_action(self) -> None:
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.SEER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            has_action = engine.start_night()
            assert has_action is True
            assert engine.get_night_action_type() == NightActionType.DIVINE
            return
        pytest.skip("No seed found for seer night action test")

    def test_villager_no_night_action(self) -> None:
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.VILLAGER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue
            has_action = engine.start_night()
            assert has_action is False
            return
        pytest.skip("No seed found for villager test")

    def test_werewolf_gets_night_action(self) -> None:
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.WEREWOLF)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            has_action = engine.start_night()
            assert has_action is True
            assert engine.get_night_action_type() == NightActionType.ATTACK
            return
        pytest.skip("No seed found for werewolf night action test")

    def test_dead_user_no_night_action(self) -> None:
        engine = _create_engine_with_dead_human(role=Role.SEER)
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        _, winner = engine.handle_auto_vote()
        if winner is None:
            has_action = engine.start_night()
            assert has_action is False


class TestResolveNight:
    def test_returns_night_messages(self) -> None:
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.VILLAGER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            villager = next((p for p in candidates if p.role == Role.VILLAGER), None)
            if villager is None:
                continue
            _, winner = engine.handle_user_vote(villager.name)
            if winner is not None:
                continue
            engine.start_night()
            night_msgs, winner = engine.resolve_night()
            if winner is None:
                assert len(night_msgs) > 0
                return
        pytest.skip("No seed found for night messages test")

    def test_increments_day(self) -> None:
        engine = _create_engine()
        initial_day = engine.game.day
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        _, winner = engine.handle_user_vote(candidates[0].name)
        if winner is None:
            engine.start_night()
            engine.resolve_night()
            assert engine.game.day == initial_day + 1

    def test_seer_attacked_divine_result_invalidated(self) -> None:
        """占い師が夜に襲撃された場合、占い結果は無効化される。"""
        # Alice=占い師, 人狼がAliceを襲撃するケースを探す
        for seed in range(100):
            engine = _create_engine(seed=seed, role=Role.SEER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            villager = next((p for p in candidates if p.role == Role.VILLAGER), None)
            if villager is None:
                continue
            _, winner = engine.handle_user_vote(villager.name)
            if winner is not None:
                continue
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue

            engine.start_night()
            divine_cands = engine.get_night_action_candidates()
            if not divine_cands:
                continue

            # 占い実行し、夜を解決（人狼がAliceを襲撃するかはAIのランダム依存）
            night_msgs, winner = engine.resolve_night(human_divine_target=divine_cands[0].name)

            # Aliceが襲撃された場合、占い結果が履歴に記録されないことを確認
            alice_alive = any(p.name == "Alice" and p.is_alive for p in engine.game.players)
            if not alice_alive:
                # 占い師が襲撃された → 占い結果は無効（divined_historyに追加されない）
                history = engine.game.get_divined_history("Alice")
                assert divine_cands[0].name not in history
                return

        pytest.skip("No seed found for seer attacked test")

    def test_speaking_order_rotated_after_attack(self) -> None:
        """襲撃後に発言順が回転する。"""
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.VILLAGER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            villager = next((p for p in candidates if p.role == Role.VILLAGER), None)
            if villager is None:
                continue
            _, winner = engine.handle_user_vote(villager.name)
            if winner is not None:
                continue

            order_before = engine.speaking_order
            engine.start_night()
            night_msgs, winner = engine.resolve_night()
            if winner is not None:
                continue

            if night_msgs:
                # 襲撃が発生した → 発言順が変わっているはず
                assert engine.speaking_order != order_before
                return

        pytest.skip("No seed found for speaking order rotation test")


class TestGetNightActionType:
    def test_dead_user_returns_none(self) -> None:
        engine = _create_engine_with_dead_human(role=Role.SEER)
        assert engine.get_night_action_type() is None

    def test_villager_returns_none(self) -> None:
        engine = _create_engine(role=Role.VILLAGER)
        assert engine.get_night_action_type() is None


class TestGetNightActionCandidates:
    def test_seer_excludes_self(self) -> None:
        engine = _create_engine(role=Role.SEER)
        candidates = engine.get_night_action_candidates()
        assert all(p.name != "Alice" for p in candidates)

    def test_werewolf_excludes_werewolves(self) -> None:
        engine = _create_engine(role=Role.WEREWOLF)
        candidates = engine.get_night_action_candidates()
        assert all(p.role != Role.WEREWOLF for p in candidates)

    def test_dead_user_returns_empty(self) -> None:
        engine = _create_engine_with_dead_human(role=Role.SEER)
        assert engine.get_night_action_candidates() == []

    def test_villager_returns_empty(self) -> None:
        engine = _create_engine(role=Role.VILLAGER)
        assert engine.get_night_action_candidates() == []


class TestFullGame:
    def test_complete_game_reaches_winner(self) -> None:
        """エンジンを通してゲーム全体をプレイし、勝者が決まる。"""
        engine = _create_engine(seed=10)
        max_turns = 20

        for _ in range(max_turns):
            # 議論
            engine.advance_discussion()
            msgs, vote_ready = engine.handle_user_discuss("テスト発言")
            while not vote_ready:
                msgs, vote_ready = engine.handle_user_discuss("テスト発言")

            # 投票
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is not None:
                candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
                if candidates:
                    votes, winner = engine.handle_user_vote(candidates[0].name)
                else:
                    votes, winner = engine.handle_auto_vote()
            else:
                votes, winner = engine.handle_auto_vote()

            if winner is not None:
                assert winner in (Team.VILLAGE, Team.WEREWOLF)
                return

            # 夜
            has_action = engine.start_night()
            if has_action:
                night_cands = engine.get_night_action_candidates()
                action_type = engine.get_night_action_type()
                if night_cands:
                    night_msgs, winner = engine.resolve_night(
                        human_divine_target=night_cands[0].name if action_type == NightActionType.DIVINE else None,
                        human_attack_target=night_cands[0].name if action_type == NightActionType.ATTACK else None,
                        human_guard_target=night_cands[0].name if action_type == NightActionType.GUARD else None,
                    )
                else:
                    night_msgs, winner = engine.resolve_night()
            else:
                night_msgs, winner = engine.resolve_night()

            if winner is not None:
                assert winner in (Team.VILLAGE, Team.WEREWOLF)
                return

        pytest.fail("Game did not reach a winner within max turns")


class TestResolveNightWithoutHumanTarget:
    """ユーザーが占い師/人狼で human_target=None の場合にスキップされる。"""

    def test_seer_human_without_target_skips_divine(self) -> None:
        """ユーザーが占い師で human_divine_target=None の場合、占いがスキップされる。"""
        engine = _create_engine(seed=42, role=Role.SEER)
        engine.advance_discussion()
        engine.handle_user_discuss("テスト")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        villager = next(p for p in candidates if p.role == Role.VILLAGER)
        _, winner = engine.handle_user_vote(villager.name)
        if winner is not None:
            pytest.skip("Game ended at vote")

        engine.start_night()
        # human_divine_target=None で呼び出し → KeyError にならずスキップされる
        night_msgs, _ = engine.resolve_night(human_divine_target=None)
        # 占い履歴が増えていないことを確認
        assert len(engine.game.divined_history) == 0

    def test_werewolf_human_without_target_skips_attack(self) -> None:
        """ユーザーが人狼で human_attack_target=None の場合、襲撃がスキップされる。"""
        engine = _create_engine(seed=42, role=Role.WEREWOLF)
        engine.advance_discussion()
        engine.handle_user_discuss("テスト")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        villager = next(p for p in candidates if p.role == Role.VILLAGER)
        _, winner = engine.handle_user_vote(villager.name)
        if winner is not None:
            pytest.skip("Game ended at vote")

        engine.start_night()
        # human_attack_target=None で呼び出し → KeyError にならずスキップされる
        night_msgs, _ = engine.resolve_night(human_attack_target=None)
        # 襲撃が発生していないことを確認
        assert len(night_msgs) == 0


class TestGuardNightPhase:
    """護衛の夜フェーズテスト（インタラクティブ）。"""

    def test_knight_user_gets_night_action(self) -> None:
        """ユーザーが狩人の場合、夜行動で護衛対象を選べる。"""
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.KNIGHT)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            has_action = engine.start_night()
            assert has_action is True
            assert engine.get_night_action_type() == NightActionType.GUARD
            # 護衛対象に自分が含まれない
            guard_cands = engine.get_night_action_candidates()
            assert all(p.name != "Alice" for p in guard_cands)
            return
        pytest.skip("No seed found for knight night action test")

    def test_knight_user_guard_target(self) -> None:
        """ユーザーが狩人で護衛対象を指定した場合、護衛が実行される。"""
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.KNIGHT)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue
            human = next((p for p in engine.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            has_action = engine.start_night()
            if not has_action:
                continue
            guard_cands = engine.get_night_action_candidates()
            if not guard_cands:
                continue
            night_msgs, _ = engine.resolve_night(human_guard_target=guard_cands[0].name)
            # 護衛ログが記録されている
            assert any("[護衛]" in log for log in engine.game.log)
            return
        pytest.skip("No seed found for knight guard test")

    def test_guard_success_prevents_attack(self) -> None:
        """護衛成功時に襲撃が無効化される。"""
        from llm_werewolf.domain.game import GameState
        from llm_werewolf.domain.player import Player
        from llm_werewolf.engine.random_provider import RandomActionProvider

        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.KNIGHT),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.SEER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
                Player(name="Frank", role=Role.WEREWOLF),
                Player(name="Grace", role=Role.MEDIUM),
                Player(name="Heidi", role=Role.MADMAN),
                Player(name="Ivan", role=Role.VILLAGER),
            ),
            phase=Phase.NIGHT,
        )
        game = game.add_log("--- Night 1 （夜フェーズ） ---")

        class FixedAttackProvider(RandomActionProvider):
            def attack(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
                return "Charlie"

        all_names = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"]
        ai_names = [n for n in all_names if n != "Alice"]
        providers = {
            name: FixedAttackProvider(rng=random.Random(rng.randint(0, 2**32)))
            if name == "Bob"
            else RandomActionProvider(rng=random.Random(rng.randint(0, 2**32)))
            for name in ai_names
        }
        speaking_order = tuple(rng.sample(all_names, len(all_names)))

        engine = InteractiveGameEngine(
            game=game,
            providers=providers,
            human_player_name="Alice",
            rng=rng,
            speaking_order=speaking_order,
        )

        # Alice（狩人）が Charlie を護衛、Bob（人狼）が Charlie を襲撃
        night_msgs, _ = engine.resolve_night(human_guard_target="Charlie")

        # 護衛成功ログ
        assert any("[護衛成功]" in log for log in engine.game.log)
        # 「今夜は誰も襲撃されなかった」メッセージ
        assert "今夜は誰も襲撃されなかった" in night_msgs
        # Charlie は生存
        charlie = engine.game.find_player("Charlie")
        assert charlie is not None and charlie.is_alive


class TestMediumResultInteractive:
    """霊媒結果テスト（インタラクティブ）。"""

    def test_medium_result_recorded_after_execution(self) -> None:
        """処刑後に霊媒結果が記録される。"""
        engine = _create_engine(seed=42)
        engine.advance_discussion()
        engine.handle_user_discuss("test")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        _, winner = engine.handle_user_vote(candidates[0].name)
        if winner is not None:
            pytest.skip("Game ended at vote")
        assert len(engine.game.medium_results) == 1

    def test_medium_result_notified_on_day2(self) -> None:
        """Day 2 の議論開始時に霊媒結果が通知される。"""
        for seed in range(50):
            engine = _create_engine(seed=seed, role=Role.VILLAGER)
            engine.advance_discussion()
            engine.handle_user_discuss("test")
            candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
            _, winner = engine.handle_user_vote(candidates[0].name)
            if winner is not None:
                continue

            engine.start_night()
            _, winner = engine.resolve_night()
            if winner is not None:
                continue

            # Day 2 の議論を開始
            engine.advance_discussion()

            # 霊媒師が生存していれば霊媒結果通知がある
            medium_alive = any(p.role == Role.MEDIUM and p.is_alive for p in engine.game.players)
            medium_logs = [log for log in engine.game.log if "[霊媒結果]" in log]
            if medium_alive:
                assert len(medium_logs) == 1
            return
        pytest.skip("No seed found for medium result notification test")


class TestResolveNightWithGuard:
    """護衛パラメータ付き resolve_night テスト。"""

    def test_knight_human_without_target_skips_guard(self) -> None:
        """ユーザーが狩人で human_guard_target=None の場合、護衛がスキップされる。"""
        engine = _create_engine(seed=42, role=Role.KNIGHT)
        engine.advance_discussion()
        engine.handle_user_discuss("テスト")
        candidates = [p for p in engine.game.alive_players if p.name != "Alice"]
        villager = next(p for p in candidates if p.role == Role.VILLAGER)
        _, winner = engine.handle_user_vote(villager.name)
        if winner is not None:
            pytest.skip("Game ended at vote")

        engine.start_night()
        # human_guard_target=None で呼び出し → 護衛がスキップされる
        night_msgs, _ = engine.resolve_night(human_guard_target=None)
        # 護衛ログがない（Aliceの護衛ログ）
        guard_logs = [log for log in engine.game.log if "[護衛] Alice" in log]
        assert len(guard_logs) == 0


class TestProgressCallback:
    """on_progress / on_message コールバックのテスト。"""

    def test_discussion_calls_progress_and_message(self) -> None:
        """議論中に on_progress と on_message が各 AI プレイヤーに対して呼ばれる。"""
        progress_calls: list[tuple[str, str]] = []
        message_calls: list[tuple[str, str]] = []

        rng = random.Random(42)
        all_names = ["Alice"] + AI_NAMES
        game = create_game_with_role(all_names, "Alice", Role.VILLAGER, rng=rng)
        game = game.add_log("=== ゲーム開始 ===")
        for p in game.players:
            game = game.add_log(f"[配役] {p.name}: {p.role.value}")

        providers = {name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES}
        speaking_order = tuple(rng.sample(all_names, len(all_names)))

        engine = InteractiveGameEngine(
            game=game,
            providers=providers,
            human_player_name="Alice",
            rng=rng,
            speaking_order=speaking_order,
            on_progress=lambda p, a: progress_calls.append((p, a)),
            on_message=lambda p, m: message_calls.append((p, m)),
        )

        msgs = engine.advance_discussion()
        # AI の発言数と progress/message コール数が一致
        ai_msg_count = len(msgs)
        assert len(progress_calls) >= ai_msg_count
        assert len(message_calls) == ai_msg_count
        # すべて "discuss" アクション
        for _, action in progress_calls:
            if action != "summarize":
                assert action == "discuss"

    def test_vote_calls_progress(self) -> None:
        """投票中に on_progress が各 AI プレイヤーに対して呼ばれる。"""
        progress_calls: list[tuple[str, str]] = []

        engine = _create_engine(seed=42, role=Role.VILLAGER)
        engine.advance_discussion()
        engine.handle_user_discuss("テスト")

        # on_progress を投票用エンジンに設定
        rng = engine._rng
        engine2 = InteractiveGameEngine(
            game=engine.game,
            providers=engine._providers,
            human_player_name="Alice",
            rng=rng,
            speaking_order=engine.speaking_order,
            discussion_round=engine.discussion_round,
            on_progress=lambda p, a: progress_calls.append((p, a)),
        )

        candidates = [p for p in engine2.game.alive_players if p.name != "Alice"]
        engine2.handle_user_vote(candidates[0].name)

        # AI プレイヤー分の投票コールバック
        assert len(progress_calls) > 0
        for _, action in progress_calls:
            assert action == "vote"

    def test_none_callbacks_no_error(self) -> None:
        """on_progress/on_message が None の場合にエラーなく動作する。"""
        engine = _create_engine(seed=42)
        # デフォルト（None）で問題なく動作することを確認
        msgs = engine.advance_discussion()
        assert len(msgs) >= 0
