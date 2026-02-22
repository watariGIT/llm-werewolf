"""ゲームセッション管理（インフラ層）。

インメモリ辞書でゲーム状態を保持し、リクエスト間で GameState を引き継ぐ。
ビジネスロジックはエンジン層（InteractiveGameEngine）に委譲する。
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from enum import Enum

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import create_game, create_game_with_role
from llm_werewolf.domain.value_objects import Role, Team
from llm_werewolf.engine.action_provider import ActionProvider
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.interactive_engine import InteractiveGameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider

AI_NAMES: list[str] = ["AI-1", "AI-2", "AI-3", "AI-4"]

MAX_SESSIONS = 100


class SessionLimitExceeded(Exception):
    """セッション数が上限に達した場合の例外。"""


class GameStep(str, Enum):
    """インタラクティブゲームの進行ステップ。"""

    ROLE_REVEAL = "role_reveal"
    DISCUSSION = "discussion"
    VOTE = "vote"
    EXECUTION_RESULT = "execution_result"
    NIGHT_ACTION = "night_action"
    NIGHT_RESULT = "night_result"
    GAME_OVER = "game_over"


@dataclass
class InteractiveSession:
    """インタラクティブゲームセッション（可変オブジェクト）。

    ステップ進行関数がフィールドを直接変更する。
    ドメイン層の frozen dataclass とは異なり、インフラ層のセッション管理として可変設計。
    """

    game_id: str
    game: GameState
    human_player_name: str
    step: GameStep
    providers: dict[str, ActionProvider]
    rng: random.Random
    speaking_order: tuple[str, ...] = ()
    display_order: tuple[str, ...] = ()
    current_discussion: list[str] = field(default_factory=list)
    current_votes: dict[str, str] = field(default_factory=dict)
    night_messages: list[str] = field(default_factory=list)
    discussion_round: int = 0
    winner: Team | None = None


class GameSessionStore:
    """ゲームセッションのインメモリストア。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: dict[str, GameState] = {}
        self._max_sessions = max_sessions

    def create(self, player_names: list[str], rng: random.Random | None = None) -> tuple[str, GameState]:
        """新規ゲームを作成し、一括実行して結果を保存する。

        Args:
            player_names: プレイヤー名リスト（5人）
            rng: テスト用の乱数生成器

        Returns:
            (ゲームID, 最終GameState) のタプル

        Raises:
            SessionLimitExceeded: セッション数が上限に達した場合
        """
        if len(self._sessions) >= self._max_sessions:
            raise SessionLimitExceeded("セッション数が上限に達しました")
        game_id = self._generate_unique_id()
        initial_state = create_game(player_names, rng=rng)

        # 全プレイヤーに RandomActionProvider を割り当て
        providers: dict[str, ActionProvider] = {p.name: RandomActionProvider(rng=rng) for p in initial_state.players}
        engine = GameEngine(initial_state, providers, rng=rng)
        final_state = engine.run()

        self._sessions[game_id] = final_state
        return game_id, final_state

    def _generate_unique_id(self) -> str:
        """衝突しない一意なゲームIDを生成する。"""
        for _ in range(10):
            game_id = uuid.uuid4().hex[:8]
            if game_id not in self._sessions:
                return game_id
        raise RuntimeError("Failed to generate unique game_id")

    def get(self, game_id: str) -> GameState | None:
        """ゲーム状態を取得する。"""
        return self._sessions.get(game_id)

    def save(self, game_id: str, game: GameState) -> None:
        """ゲーム状態を保存（上書き）する。"""
        self._sessions[game_id] = game

    def delete(self, game_id: str) -> None:
        """セッションを削除する。"""
        self._sessions.pop(game_id, None)

    def list_sessions(self) -> dict[str, GameState]:
        """全セッションを返す。"""
        return dict(self._sessions)


class InteractiveSessionStore:
    """インタラクティブゲームセッションのインメモリストア。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: dict[str, InteractiveSession] = {}
        self._max_sessions = max_sessions

    def create(self, human_name: str, rng: random.Random | None = None, role: Role | None = None) -> InteractiveSession:
        """新規インタラクティブゲームを作成する。

        Args:
            human_name: ユーザーのプレイヤー名
            rng: テスト用の乱数生成器
            role: ユーザーの役職（None の場合はランダム）

        Raises:
            SessionLimitExceeded: セッション数が上限に達した場合
        """
        if len(self._sessions) >= self._max_sessions:
            raise SessionLimitExceeded("セッション数が上限に達しました")
        rng = rng if rng is not None else random.Random()
        all_names = [human_name] + AI_NAMES
        if role is not None:
            game = create_game_with_role(all_names, human_name, role, rng=rng)
        else:
            game = create_game(all_names, rng=rng)

        # 配役ログ
        game = game.add_log("=== ゲーム開始 ===")
        for p in game.players:
            game = game.add_log(f"[配役] {p.name}: {p.role.value}")

        providers: dict[str, ActionProvider] = {
            name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES
        }

        # 発言順をランダムで決定
        speaking_order = tuple(rng.sample(all_names, len(all_names)))

        game_id = self._generate_unique_id()
        session = InteractiveSession(
            game_id=game_id,
            game=game,
            human_player_name=human_name,
            step=GameStep.ROLE_REVEAL,
            providers=providers,
            rng=rng,
            speaking_order=speaking_order,
            display_order=speaking_order,
        )
        self._sessions[game_id] = session
        return session

    def _generate_unique_id(self) -> str:
        for _ in range(10):
            game_id = uuid.uuid4().hex[:8]
            if game_id not in self._sessions:
                return game_id
        raise RuntimeError("Failed to generate unique game_id")

    def get(self, game_id: str) -> InteractiveSession | None:
        return self._sessions.get(game_id)

    def save(self, session: InteractiveSession) -> None:
        self._sessions[session.game_id] = session

    def delete(self, game_id: str) -> None:
        self._sessions.pop(game_id, None)


# --- ステップ進行関数群 ---
# エンジン層の InteractiveGameEngine に委譲する薄いラッパー。


def _create_engine(session: InteractiveSession) -> InteractiveGameEngine:
    """セッションから InteractiveGameEngine を生成する。"""
    return InteractiveGameEngine(
        game=session.game,
        providers=session.providers,
        human_player_name=session.human_player_name,
        rng=session.rng,
        speaking_order=session.speaking_order,
        discussion_round=session.discussion_round,
    )


def _sync_engine_to_session(session: InteractiveSession, engine: InteractiveGameEngine) -> None:
    """エンジンの状態をセッションに反映する。"""
    session.game = engine.game
    session.speaking_order = engine.speaking_order
    session.discussion_round = engine.discussion_round


def advance_to_discussion(session: InteractiveSession) -> None:
    """1ラウンド分の AI 議論（ユーザーの手番まで）を実行し、DISCUSSION ステップへ遷移する。"""
    if session.discussion_round == 0:
        session.current_discussion = []

    engine = _create_engine(session)
    msgs = engine.advance_discussion()
    _sync_engine_to_session(session, engine)
    session.current_discussion.extend(msgs)
    session.step = GameStep.DISCUSSION


def handle_user_discuss(session: InteractiveSession, message: str) -> None:
    """ユーザー発言を記録し、後半 AI 発言を実行。ラウンドが残っていれば次ラウンドへ、なければ VOTE へ。"""
    engine = _create_engine(session)
    msgs, vote_ready = engine.handle_user_discuss(message)
    _sync_engine_to_session(session, engine)
    session.current_discussion.extend(msgs)

    if vote_ready:
        session.step = GameStep.VOTE
    else:
        session.step = GameStep.DISCUSSION


def skip_to_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に VOTE ステップへスキップする。"""
    session.discussion_round = 0
    session.step = GameStep.VOTE


def handle_user_vote(session: InteractiveSession, target_name: str) -> None:
    """ユーザー投票を処理し、AI投票→集計→処刑→勝利判定を行う。セッションを直接変更する。"""
    engine = _create_engine(session)
    votes, winner = engine.handle_user_vote(target_name)
    _sync_engine_to_session(session, engine)
    session.current_votes = votes

    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.EXECUTION_RESULT


def handle_auto_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に AI のみで投票を行う。セッションを直接変更する。"""
    engine = _create_engine(session)
    votes, winner = engine.handle_auto_vote()
    _sync_engine_to_session(session, engine)
    session.current_votes = votes

    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.EXECUTION_RESULT


def get_night_action_type(session: InteractiveSession) -> str | None:
    """ユーザーの夜行動タイプを返す。"divine" / "attack" / None。"""
    engine = _create_engine(session)
    return engine.get_night_action_type()


def get_night_action_candidates(session: InteractiveSession) -> list[Player]:
    """ユーザーの夜行動の対象候補を返す。"""
    engine = _create_engine(session)
    return engine.get_night_action_candidates()


def start_night_phase(session: InteractiveSession) -> None:
    """夜フェーズを開始する。ユーザーに夜行動があれば NIGHT_ACTION へ遷移、なければ即解決。"""
    engine = _create_engine(session)
    has_action = engine.start_night()
    _sync_engine_to_session(session, engine)

    if has_action:
        session.step = GameStep.NIGHT_ACTION
    else:
        resolve_night_phase(session)


def handle_night_action(session: InteractiveSession, target_name: str) -> None:
    """ユーザーの夜行動（占い or 襲撃対象選択）を処理し、夜フェーズを解決する。"""
    engine = _create_engine(session)
    human = engine.get_night_action_type()

    if human is None:
        resolve_night_phase(session)
        return

    candidates = engine.get_night_action_candidates()
    candidate_names = {p.name for p in candidates}
    if target_name not in candidate_names:
        resolve_night_phase(session)
        return

    if human == "divine":
        resolve_night_phase(session, human_divine_target=target_name)
    elif human == "attack":
        resolve_night_phase(session, human_attack_target=target_name)
    else:
        resolve_night_phase(session)


def resolve_night_phase(
    session: InteractiveSession,
    human_divine_target: str | None = None,
    human_attack_target: str | None = None,
) -> None:
    """夜フェーズを解決する（占い + 襲撃 + 勝利判定）。"""
    engine = _create_engine(session)
    night_messages, winner = engine.resolve_night(human_divine_target, human_attack_target)
    _sync_engine_to_session(session, engine)
    session.night_messages = night_messages

    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.NIGHT_RESULT


def _set_game_over(session: InteractiveSession, winner: Team) -> None:
    """ゲーム終了を設定する。"""
    label = "村人陣営" if winner == Team.VILLAGE else "人狼陣営"
    session.game = session.game.add_log(f"=== ゲーム終了: {label}の勝利 ===")
    session.winner = winner
    session.step = GameStep.GAME_OVER
