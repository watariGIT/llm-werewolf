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
from llm_werewolf.domain.services import can_attack, can_divine, check_victory, create_game, create_game_with_role
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
    current_discussion: list[str] = field(default_factory=list)
    current_votes: dict[str, str] = field(default_factory=dict)
    night_messages: list[str] = field(default_factory=list)
    discussion_round: int = 0
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

    def create(self, human_name: str, rng: random.Random | None = None, role: Role | None = None) -> InteractiveSession:
        """新規インタラクティブゲームを作成する。

        Args:
            human_name: ユーザーのプレイヤー名
            rng: テスト用の乱数生成器
            role: ユーザーの役職（None の場合はランダム）
        """
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


def _find_player(game: GameState, name: str, *, alive_only: bool = False) -> Player | None:
    """プレイヤーを検索する。alive_only=True の場合は生存者のみ。"""
    players = game.alive_players if alive_only else game.players
    for p in players:
        if p.name == name:
            return p
    return None


def _get_alive_speaking_order(session: InteractiveSession) -> list[Player]:
    """speaking_order に基づき生存プレイヤーを発言順で返す。"""
    if not session.speaking_order:
        return list(session.game.alive_players)
    alive_names = {p.name for p in session.game.alive_players}
    name_to_player = {p.name: p for p in session.game.alive_players}
    return [name_to_player[name] for name in session.speaking_order if name in alive_names]


def _run_ai_discussion(session: InteractiveSession, players: list[Player]) -> list[str]:
    """指定 AI プレイヤーの発言を実行し、発言メッセージリストを返す。"""
    game = session.game
    messages: list[str] = []
    for player in players:
        provider = session.providers[player.name]
        message = provider.discuss(game, player)
        game = game.add_log(f"[発言] {player.name}: {message}")
        messages.append(f"{player.name}: {message}")
    session.game = game
    return messages


def advance_to_discussion(session: InteractiveSession) -> None:
    """1ラウンド分の AI 議論（ユーザーの手番まで）を実行し、DISCUSSION ステップへ遷移する。"""
    game = session.game

    # 新しい日の最初のラウンドの場合のみ、日のヘッダーログと占い結果通知を行う
    if session.discussion_round == 0:
        game = game.add_log(f"--- Day {game.day} （昼フェーズ） ---")
        game = replace(game, phase=Phase.DAY)
        game = _notify_divine_result(game)
        session.game = game
        session.current_discussion = []

    session.discussion_round += 1
    round_num = session.discussion_round

    session.game = session.game.add_log(f"[議論] ラウンド {round_num}")

    # speaking_order に基づく発言順で、ユーザーの前の AI を発言させる
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    ordered = _get_alive_speaking_order(session)

    if human is None:
        # ユーザー死亡時: 全 AI が発言
        ai_players = [p for p in ordered if p.name in session.providers]
        msgs = _run_ai_discussion(session, ai_players)
        session.current_discussion.extend(msgs)
    else:
        human_idx = next(i for i, p in enumerate(ordered) if p.name == session.human_player_name)
        before = [p for p in ordered[:human_idx] if p.name in session.providers]
        msgs = _run_ai_discussion(session, before)
        session.current_discussion.extend(msgs)

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
    last_target = _find_player(game, last_target_name)
    if last_target is not None:
        is_werewolf = last_target.role == Role.WEREWOLF
        result_text = "人狼" if is_werewolf else "人狼ではない"
        game = game.add_log(f"[占い結果] {seer.name} の占い: {last_target_name} は {result_text}")

    return game


def handle_user_discuss(session: InteractiveSession, message: str) -> None:
    """ユーザー発言を記録し、後半 AI 発言を実行。ラウンドが残っていれば次ラウンドへ、なければ VOTE へ。"""
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    if human is not None:
        session.game = session.game.add_log(f"[発言] {human.name}: {message}")
        session.current_discussion.append(f"{human.name}: {message}")

        # speaking_order に基づきユーザーの後ろの AI が発言
        ordered = _get_alive_speaking_order(session)
        human_idx = next(i for i, p in enumerate(ordered) if p.name == session.human_player_name)
        after = [p for p in ordered[human_idx + 1 :] if p.name in session.providers]
        msgs = _run_ai_discussion(session, after)
        session.current_discussion.extend(msgs)

    max_rounds = 1 if session.game.day == 1 else 2
    if session.discussion_round < max_rounds:
        # 次のラウンドへ
        advance_to_discussion(session)
    else:
        session.discussion_round = 0
        session.step = GameStep.VOTE


def skip_to_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に VOTE ステップへスキップする。"""
    session.discussion_round = 0
    session.step = GameStep.VOTE


def _tally_and_execute(session: InteractiveSession, votes: dict[str, str]) -> None:
    """投票を集計し、処刑を実行し、勝利判定を行う。"""
    game = session.game

    if not votes:
        session.step = GameStep.EXECUTION_RESULT
        return

    vote_counts = Counter(votes.values())
    max_votes = max(vote_counts.values())
    top_candidates = [name for name, count in vote_counts.items() if count == max_votes]
    executed_name = session.rng.choice(top_candidates) if len(top_candidates) > 1 else top_candidates[0]

    target = _find_player(game, executed_name, alive_only=True)
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


def handle_user_vote(session: InteractiveSession, target_name: str) -> None:
    """ユーザー投票を処理し、AI投票→集計→処刑→勝利判定を行う。セッションを直接変更する。"""
    game = session.game
    votes: dict[str, str] = {}

    # ユーザーの投票
    human = _find_player(game, session.human_player_name, alive_only=True)
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

    session.game = game
    _tally_and_execute(session, votes)


def handle_auto_vote(session: InteractiveSession) -> None:
    """ユーザー死亡時に AI のみで投票を行う。セッションを直接変更する。"""
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

    session.game = game
    _tally_and_execute(session, votes)


def _human_has_night_action(session: InteractiveSession) -> bool:
    """ユーザーが夜行動を持つか判定する（占い師 or 人狼で生存中）。"""
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    if human is None:
        return False
    return human.role in (Role.SEER, Role.WEREWOLF)


def get_night_action_type(session: InteractiveSession) -> str | None:
    """ユーザーの夜行動タイプを返す。"divine" / "attack" / None。"""
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    if human is None:
        return None
    if human.role == Role.SEER:
        return "divine"
    if human.role == Role.WEREWOLF:
        return "attack"
    return None


def get_night_action_candidates(session: InteractiveSession) -> list[Player]:
    """ユーザーの夜行動の対象候補を返す。"""
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    if human is None:
        return []
    game = session.game
    if human.role == Role.SEER:
        already_divined = set(game.get_divined_history(human.name))
        return [p for p in game.alive_players if p.name != human.name and p.name not in already_divined]
    if human.role == Role.WEREWOLF:
        return [p for p in game.alive_players if p.role != Role.WEREWOLF]
    return []


def start_night_phase(session: InteractiveSession) -> None:
    """夜フェーズを開始する。ユーザーに夜行動があれば NIGHT_ACTION へ遷移、なければ即解決。"""
    game = session.game
    game = game.add_log(f"--- Night {game.day} （夜フェーズ） ---")
    game = replace(game, phase=Phase.NIGHT)
    session.game = game

    if _human_has_night_action(session) and get_night_action_candidates(session):
        session.step = GameStep.NIGHT_ACTION
    else:
        resolve_night_phase(session)


def handle_night_action(session: InteractiveSession, target_name: str) -> None:
    """ユーザーの夜行動（占い or 襲撃対象選択）を処理し、夜フェーズを解決する。"""
    human = _find_player(session.game, session.human_player_name, alive_only=True)
    if human is None:
        resolve_night_phase(session)
        return

    # ターゲットバリデーション
    candidates = get_night_action_candidates(session)
    candidate_names = {p.name for p in candidates}
    if target_name not in candidate_names:
        resolve_night_phase(session)
        return

    if human.role == Role.SEER:
        resolve_night_phase(session, human_divine_target=target_name)
    elif human.role == Role.WEREWOLF:
        resolve_night_phase(session, human_attack_target=target_name)
    else:
        resolve_night_phase(session)


def resolve_night_phase(
    session: InteractiveSession,
    human_divine_target: str | None = None,
    human_attack_target: str | None = None,
) -> None:
    """夜フェーズを解決する（占い + 襲撃 + 勝利判定）。"""
    game = session.game
    night_messages: list[str] = []

    # 占いを実行
    divine_result = _resolve_divine(session, game, human_divine_target)
    if divine_result is not None:
        game, seer_name, target_name, _is_werewolf = divine_result

    # 襲撃を実行
    game, attack_target_name = _resolve_attack(session, game, human_attack_target)
    if attack_target_name is not None:
        attack_target = _find_player(game, attack_target_name, alive_only=True)
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

    # 襲撃された人の次から発言順を回転
    if attack_target_name is not None:
        order = list(session.speaking_order)
        if attack_target_name in order:
            idx = order.index(attack_target_name)
            # 襲撃された人の次の位置から開始するよう回転
            rotated = order[idx + 1 :] + order[: idx + 1]
            session.speaking_order = tuple(rotated)

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


def _resolve_divine(
    session: InteractiveSession, game: GameState, human_target: str | None = None
) -> tuple[GameState, str, str, bool] | None:
    """占いを実行する。結果は (game, seer_name, target_name, is_werewolf) または None。"""
    seer_players = [p for p in game.alive_players if p.role == Role.SEER]
    if not seer_players:
        return None

    seer = seer_players[0]
    already_divined = set(game.get_divined_history(seer.name))
    candidates = tuple(p for p in game.alive_players if p.name != seer.name and p.name not in already_divined)
    if not candidates:
        return None

    if human_target is not None and seer.name == session.human_player_name:
        target_name = human_target
    elif seer.name in session.providers:
        provider = session.providers[seer.name]
        target_name = provider.divine(game, seer, candidates)
    else:
        provider = RandomActionProvider(rng=session.rng)
        target_name = provider.divine(game, seer, candidates)

    target = _find_player(game, target_name, alive_only=True)
    if target is None:
        return None

    try:
        can_divine(game, seer, target)
    except ValueError:
        return None
    is_werewolf = target.role == Role.WEREWOLF
    game = game.add_log(f"[占い] {seer.name} が {target.name} を占った")
    return game, seer.name, target_name, is_werewolf


def _resolve_attack(
    session: InteractiveSession, game: GameState, human_target: str | None = None
) -> tuple[GameState, str | None]:
    """襲撃を実行する。"""
    werewolves = [p for p in game.alive_players if p.role == Role.WEREWOLF]
    if not werewolves:
        return game, None

    werewolf = werewolves[0]
    candidates = tuple(p for p in game.alive_players if p.role != Role.WEREWOLF)
    if not candidates:
        return game, None

    if human_target is not None and werewolf.name == session.human_player_name:
        target_name = human_target
    elif werewolf.name in session.providers:
        provider = session.providers[werewolf.name]
        target_name = provider.attack(game, werewolf, candidates)
    else:
        provider = RandomActionProvider(rng=session.rng)
        target_name = provider.attack(game, werewolf, candidates)

    target = _find_player(game, target_name, alive_only=True)
    if target is None:
        return game, None

    try:
        can_attack(game, werewolf, target)
    except ValueError:
        return game, None
    return game, target_name


def _set_game_over(session: InteractiveSession, winner: Team) -> None:
    """ゲーム終了を設定する。"""
    label = "村人陣営" if winner == Team.VILLAGE else "人狼陣営"
    session.game = session.game.add_log(f"=== ゲーム終了: {label}の勝利 ===")
    session.winner = winner
    session.step = GameStep.GAME_OVER
