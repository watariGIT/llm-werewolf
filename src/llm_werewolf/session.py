"""ゲームセッション管理（インフラ層）。

インメモリ辞書でゲーム状態を保持し、リクエスト間で GameState を引き継ぐ。
"""

from __future__ import annotations

import random
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import Enum

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import can_attack, can_divine, check_victory, create_game
from llm_werewolf.domain.value_objects import Phase, Role, Team
from llm_werewolf.engine.action_provider import ActionProvider
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider

AI_NAMES: list[str] = ["AI-1", "AI-2", "AI-3", "AI-4"]


class GameStep(str, Enum):
    """インタラクティブゲームの進行ステップ。"""

    ROLE_REVEAL = "role_reveal"
    DISCUSSION = "discussion"
    VOTE = "vote"
    EXECUTION_RESULT = "execution_result"
    NIGHT_RESULT = "night_result"
    GAME_OVER = "game_over"


@dataclass
class InteractiveSession:
    """インタラクティブゲームセッション。"""

    game_id: str
    game: GameState
    human_player_name: str
    step: GameStep
    providers: dict[str, ActionProvider]
    rng: random.Random
    current_discussion: list[str] = field(default_factory=list)
    current_votes: dict[str, str] = field(default_factory=dict)
    night_messages: list[str] = field(default_factory=list)
    winner: Team | None = None


class GameSessionStore:
    """ゲームセッションのインメモリストア。"""

    def __init__(self) -> None:
        self._sessions: dict[str, GameState] = {}

    def create(self, player_names: list[str], rng: random.Random | None = None) -> tuple[str, GameState]:
        """新規ゲームを作成し、一括実行して結果を保存する。

        Args:
            player_names: プレイヤー名リスト（5人）
            rng: テスト用の乱数生成器

        Returns:
            (ゲームID, 最終GameState) のタプル
        """
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

    def __init__(self) -> None:
        self._sessions: dict[str, InteractiveSession] = {}

    def create(self, human_name: str, rng: random.Random | None = None) -> InteractiveSession:
        """新規インタラクティブゲームを作成する。"""
        rng = rng if rng is not None else random.Random()
        all_names = [human_name] + AI_NAMES
        game = create_game(all_names, rng=rng)

        # 配役ログ
        game = game.add_log("=== ゲーム開始 ===")
        for p in game.players:
            game = game.add_log(f"[配役] {p.name}: {p.role.value}")

        providers: dict[str, ActionProvider] = {
            name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES
        }

        game_id = self._generate_unique_id()
        session = InteractiveSession(
            game_id=game_id,
            game=game,
            human_player_name=human_name,
            step=GameStep.ROLE_REVEAL,
            providers=providers,
            rng=rng,
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


def _find_alive_player(game: GameState, name: str) -> Player | None:
    for p in game.alive_players:
        if p.name == name:
            return p
    return None


def _find_player_by_name(game: GameState, name: str) -> Player | None:
    for p in game.players:
        if p.name == name:
            return p
    return None


def advance_to_discussion(session: InteractiveSession) -> None:
    """AI 議論を実行し、DISCUSSION ステップへ遷移する。"""
    game = session.game
    game = game.add_log(f"--- Day {game.day} （昼フェーズ） ---")
    game = replace(game, phase=Phase.DAY)

    # 占い結果通知 (Day 2+)
    game = _notify_divine_result(game)

    rounds = 1 if game.day == 1 else 2
    discussion_messages: list[str] = []

    for round_num in range(1, rounds + 1):
        game = game.add_log(f"[議論] ラウンド {round_num}")
        for player in game.alive_players:
            if player.name == session.human_player_name:
                continue
            provider = session.providers[player.name]
            message = provider.discuss(game, player)
            game = game.add_log(f"[発言] {player.name}: {message}")
            discussion_messages.append(f"{player.name}: {message}")

    session.game = game
    session.current_discussion = discussion_messages
    session.step = GameStep.DISCUSSION


def _notify_divine_result(game: GameState) -> GameState:
    """占い結果を通知する（Day 2+）。"""
    if game.day < 2:
        return game

    seer_players = [p for p in game.alive_players if p.role == Role.SEER]
    if not seer_players:
        return game

    seer = seer_players[0]
    history = game.get_divined_history(seer.name)
    if not history:
        return game

    last_target_name = history[-1]
    last_target = _find_player_by_name(game, last_target_name)
    if last_target is not None:
        is_werewolf = last_target.role == Role.WEREWOLF
        result_text = "人狼" if is_werewolf else "人狼ではない"
        game = game.add_log(f"[占い結果] {seer.name} の占い: {last_target_name} は {result_text}")

    return game


def handle_user_discuss(session: InteractiveSession, message: str) -> None:
    """ユーザー発言を記録し、VOTE ステップへ遷移する。"""
    human = _find_alive_player(session.game, session.human_player_name)
    if human is not None:
        session.game = session.game.add_log(f"[発言] {human.name}: {message}")
    session.step = GameStep.VOTE


def skip_to_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に VOTE ステップへスキップする。"""
    session.step = GameStep.VOTE


def handle_user_vote(session: InteractiveSession, target_name: str) -> None:
    """ユーザー投票を処理し、AI投票→集計→処刑→勝利判定を行う。"""
    game = session.game
    votes: dict[str, str] = {}

    # ユーザーの投票
    human = _find_alive_player(game, session.human_player_name)
    if human is not None:
        votes[human.name] = target_name
        game = game.add_log(f"[投票] {human.name} → {target_name}")

    # AI の投票
    for player in game.alive_players:
        if player.name == session.human_player_name:
            continue
        candidates = tuple(p for p in game.alive_players if p.name != player.name)
        provider = session.providers[player.name]
        ai_target = provider.vote(game, player, candidates)
        votes[player.name] = ai_target
        game = game.add_log(f"[投票] {player.name} → {ai_target}")

    # 集計・処刑
    vote_counts = Counter(votes.values())
    max_votes = max(vote_counts.values())
    top_candidates = [name for name, count in vote_counts.items() if count == max_votes]
    executed_name = session.rng.choice(top_candidates) if len(top_candidates) > 1 else top_candidates[0]

    target = _find_alive_player(game, executed_name)
    if target is not None:
        dead_player = target.killed()
        game = game.replace_player(target, dead_player)
        game = game.add_log(f"[処刑] {target.name} が処刑された（得票数: {vote_counts[executed_name]}）")

    session.game = game
    session.current_votes = votes

    # 勝利判定
    winner = check_victory(game)
    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.EXECUTION_RESULT


def handle_auto_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に AI のみで投票を行う。"""
    game = session.game
    votes: dict[str, str] = {}

    for player in game.alive_players:
        if player.name not in session.providers:
            continue
        candidates = tuple(p for p in game.alive_players if p.name != player.name)
        provider = session.providers[player.name]
        ai_target = provider.vote(game, player, candidates)
        votes[player.name] = ai_target
        game = game.add_log(f"[投票] {player.name} → {ai_target}")

    vote_counts = Counter(votes.values())
    max_votes = max(vote_counts.values())
    top_candidates = [name for name, count in vote_counts.items() if count == max_votes]
    executed_name = session.rng.choice(top_candidates) if len(top_candidates) > 1 else top_candidates[0]

    target = _find_alive_player(game, executed_name)
    if target is not None:
        dead_player = target.killed()
        game = game.replace_player(target, dead_player)
        game = game.add_log(f"[処刑] {target.name} が処刑された（得票数: {vote_counts[executed_name]}）")

    session.game = game
    session.current_votes = votes

    winner = check_victory(game)
    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.EXECUTION_RESULT


def execute_night_phase(session: InteractiveSession) -> None:
    """夜フェーズを実行する（占い + 襲撃 + 勝利判定）。"""
    game = session.game
    game = game.add_log(f"--- Night {game.day} （夜フェーズ） ---")
    game = replace(game, phase=Phase.NIGHT)

    night_messages: list[str] = []

    # 占いを実行
    divine_result = _resolve_divine(session, game)
    if divine_result is not None:
        game, seer_name, target_name, _is_werewolf = divine_result

    # 襲撃を実行
    game, attack_target_name = _resolve_attack(session, game)
    if attack_target_name is not None:
        attack_target = _find_alive_player(game, attack_target_name)
        if attack_target is not None:
            dead_player = attack_target.killed()
            game = game.replace_player(attack_target, dead_player)
            game = game.add_log(f"[襲撃] {attack_target.name} が人狼に襲撃された")
            night_messages.append(f"{attack_target.name} が人狼に襲撃された")

            # 占い師が襲撃された場合、占い結果は無効
            if divine_result is not None:
                seer_name_check = divine_result[1]
                if attack_target.name == seer_name_check:
                    divine_result = None

    # 占い結果を記録
    if divine_result is not None:
        _, seer_name_rec, target_name_rec, _ = divine_result
        game = game.add_divine_history(seer_name_rec, target_name_rec)

    # 次の日へ
    game = replace(game, phase=Phase.DAY, day=game.day + 1)

    session.game = game
    session.night_messages = night_messages

    # 勝利判定
    winner = check_victory(game)
    if winner is not None:
        _set_game_over(session, winner)
    else:
        session.step = GameStep.NIGHT_RESULT


def _resolve_divine(session: InteractiveSession, game: GameState) -> tuple[GameState, str, str, bool] | None:
    """占いを実行する。結果は (game, seer_name, target_name, is_werewolf) または None。"""
    seer_players = [p for p in game.alive_players if p.role == Role.SEER]
    if not seer_players:
        return None

    seer = seer_players[0]
    already_divined = set(game.get_divined_history(seer.name))
    candidates = tuple(p for p in game.alive_players if p.name != seer.name and p.name not in already_divined)
    if not candidates:
        return None

    # Mock版: 占い師がユーザーでも AI でもランダム実行
    if seer.name in session.providers:
        provider = session.providers[seer.name]
    else:
        provider = RandomActionProvider(rng=session.rng)
    target_name = provider.divine(game, seer, candidates)

    target = _find_alive_player(game, target_name)
    if target is None:
        return None

    can_divine(game, seer, target)
    is_werewolf = target.role == Role.WEREWOLF
    game = game.add_log(f"[占い] {seer.name} が {target.name} を占った")
    return game, seer.name, target_name, is_werewolf


def _resolve_attack(session: InteractiveSession, game: GameState) -> tuple[GameState, str | None]:
    """襲撃を実行する。"""
    werewolves = [p for p in game.alive_players if p.role == Role.WEREWOLF]
    if not werewolves:
        return game, None

    werewolf = werewolves[0]
    candidates = tuple(p for p in game.alive_players if p.role != Role.WEREWOLF)
    if not candidates:
        return game, None

    if werewolf.name in session.providers:
        provider = session.providers[werewolf.name]
    else:
        provider = RandomActionProvider(rng=session.rng)
    target_name = provider.attack(game, werewolf, candidates)

    target = _find_alive_player(game, target_name)
    if target is None:
        return game, None

    can_attack(game, werewolf, target)
    return game, target_name


def _set_game_over(session: InteractiveSession, winner: Team) -> None:
    """ゲーム終了を設定する。"""
    label = "村人陣営" if winner == Team.VILLAGE else "人狼陣営"
    session.game = session.game.add_log(f"=== ゲーム終了: {label}の勝利 ===")
    session.winner = winner
    session.step = GameStep.GAME_OVER
