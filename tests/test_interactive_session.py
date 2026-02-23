import random

import pytest

from llm_werewolf.domain.value_objects import NightActionType, Role, Team
from llm_werewolf.session import (
    AI_NAMES,
    GameStep,
    InteractiveSession,
    InteractiveSessionStore,
    SessionLimitExceeded,
    advance_from_execution_result,
    advance_to_discussion,
    get_night_action_candidates,
    get_night_action_type,
    handle_auto_vote,
    handle_night_action,
    handle_user_discuss,
    handle_user_vote,
    skip_to_vote,
    start_night_phase,
)


def _create_session(seed: int = 42, human_name: str = "テスト太郎", role: Role | None = None) -> InteractiveSession:
    """テスト用にseed固定でセッションを生成する。"""
    store = InteractiveSessionStore()
    return store.create(human_name, rng=random.Random(seed), role=role)


class TestInteractiveSessionStore:
    def test_create_returns_session_with_role_reveal_step(self) -> None:
        session = _create_session()
        assert session.step == GameStep.ROLE_REVEAL
        assert session.game_id

    def test_create_assigns_nine_players(self) -> None:
        session = _create_session()
        assert len(session.game.players) == 9

    def test_create_includes_human_player(self) -> None:
        session = _create_session(human_name="Alice")
        names = [p.name for p in session.game.players]
        assert "Alice" in names

    def test_create_includes_ai_players(self) -> None:
        session = _create_session()
        names = [p.name for p in session.game.players]
        for ai_name in AI_NAMES:
            assert ai_name in names

    def test_create_has_game_start_log(self) -> None:
        session = _create_session()
        assert "=== ゲーム開始 ===" in session.game.log

    def test_get_returns_none_for_unknown_id(self) -> None:
        store = InteractiveSessionStore()
        assert store.get("unknown") is None

    def test_save_and_get_roundtrip(self) -> None:
        store = InteractiveSessionStore()
        session = store.create("Player1", rng=random.Random(42))
        session.step = GameStep.DISCUSSION
        store.save(session)
        retrieved = store.get(session.game_id)
        assert retrieved is not None
        assert retrieved.step == GameStep.DISCUSSION

    def test_delete_removes_session(self) -> None:
        store = InteractiveSessionStore()
        session = store.create("Player1", rng=random.Random(42))
        store.delete(session.game_id)
        assert store.get(session.game_id) is None

    def test_create_raises_when_max_sessions_reached(self) -> None:
        store = InteractiveSessionStore(max_sessions=3)
        for i in range(3):
            store.create(f"Player{i}", rng=random.Random(i))
        with pytest.raises(SessionLimitExceeded):
            store.create("Overflow", rng=random.Random(999))

    def test_create_after_delete_allows_new_session(self) -> None:
        store = InteractiveSessionStore(max_sessions=2)
        s1 = store.create("Player0", rng=random.Random(0))
        store.create("Player1", rng=random.Random(1))
        store.delete(s1.game_id)
        session = store.create("Player2", rng=random.Random(2))
        assert session.game_id is not None


class TestAdvanceToDiscussion:
    def test_transitions_to_discussion(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        assert session.step == GameStep.DISCUSSION

    def test_generates_ai_discussion_messages(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        # ユーザー発言後に後半 AI の発言も追加されるため、AI のメッセージが含まれる
        ai_msgs = [msg for msg in session.current_discussion if not msg.startswith(session.human_player_name)]
        assert len(ai_msgs) > 0

    def test_does_not_include_human_discussion(self) -> None:
        session = _create_session(human_name="Alice")
        advance_to_discussion(session)
        for msg in session.current_discussion:
            assert not msg.startswith("Alice:")

    def test_adds_day_log(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        day_logs = [line for line in session.game.log if "昼フェーズ" in line]
        assert len(day_logs) > 0


class TestHandleUserDiscuss:
    def test_transitions_to_vote(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "こんにちは")
        assert session.step == GameStep.VOTE

    def test_records_message_in_log(self) -> None:
        session = _create_session(human_name="Alice")
        advance_to_discussion(session)
        handle_user_discuss(session, "怪しいのは誰だ")
        assert any("[発言] Alice: 怪しいのは誰だ" in line for line in session.game.log)


def _advance_to_day2(session: InteractiveSession) -> None:
    """セッションを Day 2 の議論開始前まで進める。"""
    # Day 1: 議論 → 投票 → 処刑
    advance_to_discussion(session)
    handle_user_discuss(session, "テスト")
    candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
    handle_user_vote(session, candidates[0].name)
    # 処刑結果 → 夜フェーズ
    advance_from_execution_result(session)
    if session.step == GameStep.NIGHT_ACTION:
        night_candidates = get_night_action_candidates(session)
        handle_night_action(session, night_candidates[0].name)
    elif session.step == GameStep.NIGHT_RESULT:
        pass  # 自動解決済み
    assert session.game.day == 2 or session.step == GameStep.NIGHT_RESULT


class TestSkipToVote:
    def test_transitions_to_vote(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        skip_to_vote(session)
        assert session.step == GameStep.VOTE

    def test_day2_executes_two_rounds(self) -> None:
        """Day 2 でユーザー死亡時に skip_to_vote が2巡分の議論を実行する。"""
        session = _create_session(seed=42)
        _advance_to_day2(session)
        # NIGHT_RESULT から Day 2 議論開始（1巡目実行）
        if session.step == GameStep.NIGHT_RESULT:
            advance_to_discussion(session)
        assert session.discussion_round == 1
        # skip_to_vote で残りラウンドを消化
        skip_to_vote(session)
        assert session.step == GameStep.VOTE
        assert session.discussion_round == 2


class TestHandleUserVote:
    def test_always_transitions_to_execution_result(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        # 誰か生存者に投票
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)
        assert session.step == GameStep.EXECUTION_RESULT

    def test_records_votes_in_log(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)
        vote_logs = [line for line in session.game.log if "[投票]" in line]
        assert len(vote_logs) > 0

    def test_stores_votes_dict(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)
        assert len(session.current_votes) > 0

    def test_game_over_when_werewolf_executed(self) -> None:
        """人狼が処刑されたら EXECUTION_RESULT を経由してゲーム終了になる。"""
        for seed in range(100):
            session = _create_session(seed=seed)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")

            # 人狼を見つける
            werewolf = next((p for p in session.game.alive_players if p.role == Role.WEREWOLF), None)
            if werewolf is None:
                continue

            handle_user_vote(session, werewolf.name)
            if session.winner == Team.VILLAGE:
                # 勝者が確定していても EXECUTION_RESULT を経由する
                assert session.step == GameStep.EXECUTION_RESULT
                assert len(session.current_votes) > 0
                # advance_from_execution_result で GAME_OVER に遷移
                advance_from_execution_result(session)
                assert session.step == GameStep.GAME_OVER
                return

        pytest.skip("No seed found that results in werewolf execution")


class TestHandleAutoVote:
    def test_always_transitions_to_execution_result(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        skip_to_vote(session)
        handle_auto_vote(session)
        assert session.step == GameStep.EXECUTION_RESULT


class TestExecuteNightPhase:
    def test_transitions_to_night_result_or_game_over(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)

        assert session.step == GameStep.EXECUTION_RESULT
        advance_from_execution_result(session)
        if session.step == GameStep.NIGHT_ACTION:
            candidates = get_night_action_candidates(session)
            if candidates:
                handle_night_action(session, candidates[0].name)
        assert session.step in (GameStep.NIGHT_RESULT, GameStep.GAME_OVER)

    def test_increments_day_after_night(self) -> None:
        session = _create_session()
        initial_day = session.game.day
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)

        assert session.step == GameStep.EXECUTION_RESULT
        if session.winner is None:
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                candidates = get_night_action_candidates(session)
                if candidates:
                    handle_night_action(session, candidates[0].name)
            assert session.game.day == initial_day + 1

    def test_night_attack_reduces_alive_count(self) -> None:
        """夜フェーズで襲撃が行われ、生存者が減る。"""
        for seed in range(50):
            session = _create_session(seed=seed)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")

            # 村人を投票対象にする
            villager = next(
                (
                    p
                    for p in session.game.alive_players
                    if p.role == Role.VILLAGER and p.name != session.human_player_name
                ),
                None,
            )
            if villager is None:
                continue

            handle_user_vote(session, villager.name)
            assert session.step == GameStep.EXECUTION_RESULT
            if session.winner is not None:
                continue

            alive_before = len(session.game.alive_players)
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                candidates = get_night_action_candidates(session)
                if candidates:
                    handle_night_action(session, candidates[0].name)
            alive_after = len(session.game.alive_players)

            # 夜の襲撃で1人減るはず（ゲーム終了でなければ）
            if session.step == GameStep.NIGHT_RESULT:
                assert alive_after < alive_before
                return

        pytest.skip("No seed found for night attack test")


class TestFullGameFlow:
    def test_complete_game_reaches_game_over(self) -> None:
        """ゲーム全体を通してプレイし、GAME_OVER に到達する。"""
        session = _create_session(seed=10)
        max_turns = 20

        for _ in range(max_turns):
            if session.step == GameStep.GAME_OVER:
                break

            if session.step == GameStep.ROLE_REVEAL:
                advance_to_discussion(session)
            elif session.step == GameStep.DISCUSSION:
                human = next((p for p in session.game.alive_players if p.name == session.human_player_name), None)
                if human is not None:
                    handle_user_discuss(session, "テスト発言")
                else:
                    skip_to_vote(session)
            elif session.step == GameStep.VOTE:
                human = next((p for p in session.game.alive_players if p.name == session.human_player_name), None)
                if human is not None:
                    candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
                    if candidates:
                        handle_user_vote(session, candidates[0].name)
                    else:
                        handle_auto_vote(session)
                else:
                    handle_auto_vote(session)
            elif session.step == GameStep.EXECUTION_RESULT:
                advance_from_execution_result(session)
                if session.step == GameStep.NIGHT_ACTION:
                    candidates = get_night_action_candidates(session)
                    if candidates:
                        handle_night_action(session, candidates[0].name)
            elif session.step == GameStep.NIGHT_RESULT:
                advance_to_discussion(session)

        assert session.step == GameStep.GAME_OVER
        assert session.winner is not None
        assert session.winner in (Team.VILLAGE, Team.WEREWOLF)


class TestCreateWithRole:
    def test_create_with_seer_role(self) -> None:
        session = _create_session(human_name="Alice", role=Role.SEER)
        human = next(p for p in session.game.players if p.name == "Alice")
        assert human.role == Role.SEER

    def test_create_with_werewolf_role(self) -> None:
        session = _create_session(human_name="Alice", role=Role.WEREWOLF)
        human = next(p for p in session.game.players if p.name == "Alice")
        assert human.role == Role.WEREWOLF

    def test_create_with_villager_role(self) -> None:
        session = _create_session(human_name="Alice", role=Role.VILLAGER)
        human = next(p for p in session.game.players if p.name == "Alice")
        assert human.role == Role.VILLAGER

    def test_create_with_random_role(self) -> None:
        session = _create_session(human_name="Alice", role=None)
        assert len(session.game.players) == 9

    def test_all_roles_assigned_with_fixed_role(self) -> None:
        session = _create_session(human_name="Alice", role=Role.SEER)
        roles = [p.role for p in session.game.players]
        assert roles.count(Role.SEER) == 1
        assert roles.count(Role.WEREWOLF) == 2
        assert roles.count(Role.VILLAGER) == 3
        assert roles.count(Role.KNIGHT) == 1
        assert roles.count(Role.MEDIUM) == 1
        assert roles.count(Role.MADMAN) == 1


class TestNightAction:
    def test_seer_gets_night_action(self) -> None:
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice", role=Role.SEER)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")
            candidates = [p for p in session.game.alive_players if p.name != "Alice"]
            handle_user_vote(session, candidates[0].name)
            if session.winner is not None:
                continue
            # Alice が生存しているか確認
            human = next((p for p in session.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            start_night_phase(session)
            assert session.step == GameStep.NIGHT_ACTION
            assert get_night_action_type(session) == NightActionType.DIVINE
            return
        pytest.skip("No seed found for seer night action test")

    def test_werewolf_gets_night_action(self) -> None:
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice", role=Role.WEREWOLF)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")
            candidates = [p for p in session.game.alive_players if p.name != "Alice"]
            handle_user_vote(session, candidates[0].name)
            if session.winner is not None:
                continue
            human = next((p for p in session.game.alive_players if p.name == "Alice"), None)
            if human is None:
                continue
            start_night_phase(session)
            assert session.step == GameStep.NIGHT_ACTION
            assert get_night_action_type(session) == NightActionType.ATTACK
            return
        pytest.skip("No seed found for werewolf night action test")

    def test_villager_skips_night_action(self) -> None:
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice", role=Role.VILLAGER)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")
            candidates = [p for p in session.game.alive_players if p.name != "Alice"]
            handle_user_vote(session, candidates[0].name)
            if session.winner is not None:
                continue
            start_night_phase(session)
            assert session.step != GameStep.NIGHT_ACTION
            return
        pytest.skip("No seed found for villager skip test")

    def test_seer_divine_candidates_exclude_self_and_divined(self) -> None:
        session = _create_session(human_name="Alice", role=Role.SEER)
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != "Alice"]
        handle_user_vote(session, candidates[0].name)
        if session.winner is None:
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_candidates = get_night_action_candidates(session)
                candidate_names = [p.name for p in night_candidates]
                assert "Alice" not in candidate_names

    def test_werewolf_attack_candidates_exclude_werewolves(self) -> None:
        session = _create_session(human_name="Alice", role=Role.WEREWOLF)
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != "Alice"]
        handle_user_vote(session, candidates[0].name)
        if session.winner is None:
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_candidates = get_night_action_candidates(session)
                for p in night_candidates:
                    assert p.role != Role.WEREWOLF

    def test_handle_night_action_resolves_night(self) -> None:
        session = _create_session(human_name="Alice", role=Role.SEER)
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != "Alice"]
        handle_user_vote(session, candidates[0].name)
        if session.winner is None:
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_candidates = get_night_action_candidates(session)
                handle_night_action(session, night_candidates[0].name)
                assert session.step in (GameStep.NIGHT_RESULT, GameStep.GAME_OVER)


class TestDiscussionRounds:
    def test_day1_one_round(self) -> None:
        """Day 1 ではユーザー発言後に即 VOTE へ遷移する。"""
        session = _create_session()
        advance_to_discussion(session)
        assert session.discussion_round == 1
        handle_user_discuss(session, "こんにちは")
        assert session.step == GameStep.VOTE
        assert session.discussion_round == 0

    def test_day2_two_rounds(self) -> None:
        """Day 2 ではユーザーが2回発言できる。"""
        for seed in range(50):
            session = _create_session(seed=seed)
            advance_to_discussion(session)
            handle_user_discuss(session, "Day1 発言")
            candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
            handle_user_vote(session, candidates[0].name)
            if session.winner is not None:
                continue
            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_cands = get_night_action_candidates(session)
                if night_cands:
                    handle_night_action(session, night_cands[0].name)
            if session.step != GameStep.NIGHT_RESULT:
                continue

            # Day 2 の議論開始
            advance_to_discussion(session)
            assert session.step == GameStep.DISCUSSION
            assert session.discussion_round == 1

            # ラウンド1のユーザー発言 → まだ DISCUSSION（ラウンド2）
            handle_user_discuss(session, "Day2 ラウンド1")
            assert session.step == GameStep.DISCUSSION
            assert session.discussion_round == 2

            # ラウンド2のユーザー発言 → VOTE
            handle_user_discuss(session, "Day2 ラウンド2")
            assert session.step == GameStep.VOTE
            assert session.discussion_round == 0
            return
        pytest.skip("No seed found for day2 two rounds test")

    def test_speaking_order_includes_human(self) -> None:
        """ユーザーの発言が speaking_order の順序通りに挿入される。"""
        session = _create_session(human_name="Alice")
        advance_to_discussion(session)
        handle_user_discuss(session, "私の発言です")

        # ユーザーの発言が current_discussion に含まれる
        human_msgs = [msg for msg in session.current_discussion if msg.startswith("Alice:")]
        assert len(human_msgs) == 1

        # 発言順が speaking_order に従うか確認
        speaking_order = list(session.speaking_order)
        human_name = "Alice"
        human_idx = speaking_order.index(human_name)

        # ユーザーの前の AI の発言がユーザーの前にある
        discussion_speakers = [msg.split(": ", 1)[0] for msg in session.current_discussion]
        human_msg_idx = discussion_speakers.index(human_name)
        for speaker in discussion_speakers[:human_msg_idx]:
            assert speaker in speaking_order[:human_idx]


class TestSpeakingOrder:
    def test_speaking_order_is_randomized(self) -> None:
        """speaking_order はランダムで決定され、必ずしもプレイヤーが先頭ではない。"""
        orders: set[tuple[str, ...]] = set()
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice")
            orders.add(session.speaking_order)
        # 複数の異なる発言順が生成されるはず
        assert len(orders) > 1

    def test_speaking_order_contains_all_players(self) -> None:
        """speaking_order は全プレイヤーを含む。"""
        session = _create_session(human_name="Alice")
        player_names = {p.name for p in session.game.players}
        assert set(session.speaking_order) == player_names

    def test_display_order_set_on_creation(self) -> None:
        """display_order がゲーム開始時に speaking_order と同じ値で設定される。"""
        session = _create_session(human_name="Alice")
        assert session.display_order == session.speaking_order
        assert len(session.display_order) == 9

    def test_display_order_unchanged_after_night_attack(self) -> None:
        """夜襲撃後も display_order は変更されない（speaking_order は変わる）。"""
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice", role=Role.VILLAGER)
            original_display_order = session.display_order
            advance_to_discussion(session)
            handle_user_discuss(session, "test")

            villager = next(
                (p for p in session.game.alive_players if p.role == Role.VILLAGER and p.name != "Alice"),
                None,
            )
            if villager is None:
                continue

            handle_user_vote(session, villager.name)
            if session.winner is not None:
                continue

            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_cands = get_night_action_candidates(session)
                if night_cands:
                    handle_night_action(session, night_cands[0].name)
            if session.step not in (GameStep.NIGHT_RESULT, GameStep.GAME_OVER):
                continue

            if session.night_messages:
                # speaking_order は変わるが display_order は変わらない
                assert session.speaking_order != original_display_order
                assert session.display_order == original_display_order
                return

        pytest.skip("No seed found for display order test")

    def test_human_not_always_first_in_speaking_order(self) -> None:
        """ユーザーが常に最初ではない。"""
        first_count = 0
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice")
            if session.speaking_order[0] == "Alice":
                first_count += 1
        # 50回中すべてが先頭ではないはず（確率的にほぼありえない）
        assert first_count < 50

    def test_discussion_follows_speaking_order(self) -> None:
        """議論の発言順が speaking_order に従う。"""
        session = _create_session(seed=10, human_name="Alice")
        advance_to_discussion(session)
        handle_user_discuss(session, "テスト発言")

        # 全発言者の順序を取得
        discussion_speakers = [msg.split(": ", 1)[0] for msg in session.current_discussion]

        # speaking_order から生存者のみ抽出
        alive_names = {p.name for p in session.game.alive_players}
        expected_order = [name for name in session.speaking_order if name in alive_names]

        # discussion_speakers は expected_order のサブシーケンスであるべき
        expected_idx = 0
        for speaker in discussion_speakers:
            while expected_idx < len(expected_order) and expected_order[expected_idx] != speaker:
                expected_idx += 1
            assert expected_idx < len(expected_order), f"{speaker} not in expected order position"
            expected_idx += 1

    def test_speaking_order_rotates_after_night_attack(self) -> None:
        """夜襲撃後、speaking_order が襲撃された人の次から開始するよう回転する。"""
        for seed in range(50):
            session = _create_session(seed=seed, human_name="Alice", role=Role.VILLAGER)
            original_order = session.speaking_order
            advance_to_discussion(session)
            handle_user_discuss(session, "test")

            # 村人を投票対象にする（人狼以外）
            villager = next(
                (p for p in session.game.alive_players if p.role == Role.VILLAGER and p.name != "Alice"),
                None,
            )
            if villager is None:
                continue

            handle_user_vote(session, villager.name)
            if session.winner is not None:
                continue

            start_night_phase(session)
            if session.step == GameStep.NIGHT_ACTION:
                night_cands = get_night_action_candidates(session)
                if night_cands:
                    handle_night_action(session, night_cands[0].name)
            if session.step not in (GameStep.NIGHT_RESULT, GameStep.GAME_OVER):
                continue

            # 夜の襲撃があった場合、speaking_order が変わっているはず
            if session.night_messages:
                assert session.speaking_order != original_order
                return

        pytest.skip("No seed found for speaking order rotation test")


class TestDeterminism:
    def test_same_seed_produces_same_result(self) -> None:
        """同じ seed で同じ結果が得られる。"""
        results = []
        for _ in range(2):
            session = _create_session(seed=99)
            advance_to_discussion(session)

            roles1 = [(p.name, p.role) for p in session.game.players]
            msgs1 = list(session.current_discussion)
            results.append((roles1, msgs1))

        assert results[0] == results[1]
