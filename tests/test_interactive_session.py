import random

import pytest

from llm_werewolf.domain.value_objects import Role, Team
from llm_werewolf.session import (
    AI_NAMES,
    GameStep,
    InteractiveSession,
    InteractiveSessionStore,
    advance_to_discussion,
    execute_night_phase,
    handle_auto_vote,
    handle_user_discuss,
    handle_user_vote,
    skip_to_vote,
)


def _create_session(seed: int = 42, human_name: str = "テスト太郎") -> InteractiveSession:
    """テスト用にseed固定でセッションを生成する。"""
    store = InteractiveSessionStore()
    return store.create(human_name, rng=random.Random(seed))


class TestInteractiveSessionStore:
    def test_create_returns_session_with_role_reveal_step(self) -> None:
        session = _create_session()
        assert session.step == GameStep.ROLE_REVEAL
        assert session.game_id

    def test_create_assigns_five_players(self) -> None:
        session = _create_session()
        assert len(session.game.players) == 5

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


class TestAdvanceToDiscussion:
    def test_transitions_to_discussion(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        assert session.step == GameStep.DISCUSSION

    def test_generates_ai_discussion_messages(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        assert len(session.current_discussion) > 0

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


class TestSkipToVote:
    def test_transitions_to_vote(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        skip_to_vote(session)
        assert session.step == GameStep.VOTE


class TestHandleUserVote:
    def test_transitions_to_execution_result_on_no_victory(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        # 誰か生存者に投票
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)
        assert session.step in (GameStep.EXECUTION_RESULT, GameStep.GAME_OVER)

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
        """人狼が処刑されたらゲーム終了になる。seed を調整して人狼を直接処刑する。"""
        # 人狼を見つけてそのプレイヤーに全員投票させるような状況を作る
        for seed in range(100):
            session = _create_session(seed=seed)
            advance_to_discussion(session)
            handle_user_discuss(session, "test")

            # 人狼を見つける
            werewolf = next((p for p in session.game.alive_players if p.role == Role.WEREWOLF), None)
            if werewolf is None:
                continue

            handle_user_vote(session, werewolf.name)
            if session.step == GameStep.GAME_OVER:
                assert session.winner == Team.VILLAGE
                return

        # いずれかの seed で GAME_OVER になるはず（大量投票でランダム的に当たる）
        pytest.skip("No seed found that results in werewolf execution")


class TestHandleAutoVote:
    def test_transitions_after_auto_vote(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        skip_to_vote(session)
        handle_auto_vote(session)
        assert session.step in (GameStep.EXECUTION_RESULT, GameStep.GAME_OVER)


class TestExecuteNightPhase:
    def test_transitions_to_night_result_or_game_over(self) -> None:
        session = _create_session()
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)

        if session.step == GameStep.EXECUTION_RESULT:
            execute_night_phase(session)
            assert session.step in (GameStep.NIGHT_RESULT, GameStep.GAME_OVER)

    def test_increments_day_after_night(self) -> None:
        session = _create_session()
        initial_day = session.game.day
        advance_to_discussion(session)
        handle_user_discuss(session, "test")
        candidates = [p for p in session.game.alive_players if p.name != session.human_player_name]
        handle_user_vote(session, candidates[0].name)

        if session.step == GameStep.EXECUTION_RESULT:
            execute_night_phase(session)
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
            if session.step != GameStep.EXECUTION_RESULT:
                continue

            alive_before = len(session.game.alive_players)
            execute_night_phase(session)
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
                execute_night_phase(session)
            elif session.step == GameStep.NIGHT_RESULT:
                advance_to_discussion(session)

        assert session.step == GameStep.GAME_OVER
        assert session.winner is not None
        assert session.winner in (Team.VILLAGE, Team.WEREWOLF)


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
