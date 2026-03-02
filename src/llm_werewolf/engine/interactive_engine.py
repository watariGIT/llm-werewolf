"""インタラクティブゲーム用のステップ実行エンジン。

ユーザーと AI が対戦するインタラクティブモードのゲーム進行ロジックを管理する。
session.py はこのエンジンを呼び出す薄いラッパーとして機能する。
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import check_victory
from llm_werewolf.domain.value_objects import NightActionType, Phase, Role, Team
from llm_werewolf.engine.action_provider import ActionProvider
from llm_werewolf.engine.game_logic import (
    execute_attack,
    execute_divine,
    execute_guard,
    find_night_actor,
    get_alive_speaking_order,
    get_discussion_rounds,
    get_night_action_candidates,
    notify_divine_result,
    notify_medium_result,
    rotate_speaking_order,
    tally_votes,
)

if TYPE_CHECKING:
    from llm_werewolf.engine.game_master import GameMasterProvider

# 進捗コールバック: (player_name, action_type) を受け取る
ProgressCallback = Callable[[str, str], None]
# 発言完了コールバック: (player_name, message_text) を受け取る
MessageCallback = Callable[[str, str], None]


class InteractiveGameEngine:
    """インタラクティブゲーム用のステップ実行エンジン。

    1ステップずつゲームを進行し、ユーザー入力を受け付ける。
    ビジネスロジック（投票集計、占い、襲撃、発言順管理等）をカプセル化し、
    インフラ層（session.py）から分離する。
    """

    def __init__(
        self,
        game: GameState,
        providers: dict[str, ActionProvider],
        human_player_name: str,
        rng: random.Random,
        speaking_order: tuple[str, ...],
        discussion_round: int = 0,
        gm_provider: GameMasterProvider | None = None,
        on_progress: ProgressCallback | None = None,
        on_message: MessageCallback | None = None,
    ) -> None:
        self._game = game
        self._providers = providers
        self._human_player_name = human_player_name
        self._rng = rng
        self._speaking_order = speaking_order
        self._discussion_round = discussion_round
        self._gm_provider = gm_provider
        self._on_progress = on_progress
        self._on_message = on_message

    @property
    def game(self) -> GameState:
        return self._game

    @property
    def speaking_order(self) -> tuple[str, ...]:
        return self._speaking_order

    @property
    def discussion_round(self) -> int:
        return self._discussion_round

    def advance_discussion(self) -> list[str]:
        """1ラウンド分の AI 議論（ユーザーの手番まで）を実行する。

        最初のラウンド（discussion_round == 0）では日のヘッダーログと占い結果通知も行う。

        Returns:
            AI プレイヤーの発言メッセージリスト
        """
        messages: list[str] = []

        if self._discussion_round == 0:
            self._game = self._game.add_log(f"--- Day {self._game.day} （昼フェーズ） ---")
            self._game = replace(self._game, phase=Phase.DAY)
            self._game = notify_divine_result(self._game)
            self._game = notify_medium_result(self._game)

            # GM-AI 要約 (Day 2以降)
            if self._game.day >= 2 and self._gm_provider is not None:
                self._notify_progress("GM", "summarize")
                summary_json = self._gm_provider.summarize(self._game)
                self._game = replace(self._game, gm_summary=summary_json, gm_summary_log_offset=len(self._game.log))

        self._discussion_round += 1
        self._game = self._game.add_log(f"[議論] ラウンド {self._discussion_round}")

        human = self._game.find_player(self._human_player_name, alive_only=True)
        ordered = get_alive_speaking_order(self._game, self._speaking_order)

        if human is None:
            ai_players = [p for p in ordered if p.name in self._providers]
            messages = self._run_ai_discussion(ai_players)
        else:
            human_idx = next(i for i, p in enumerate(ordered) if p.name == self._human_player_name)
            before = [p for p in ordered[:human_idx] if p.name in self._providers]
            messages = self._run_ai_discussion(before)

        return messages

    def handle_user_discuss(self, message: str) -> tuple[list[str], bool]:
        """ユーザー発言を記録し、後半 AI 発言を実行する。

        Args:
            message: ユーザーの発言内容

        Returns:
            (発言メッセージリスト, vote_ready) のタプル。
            vote_ready が True なら全ラウンド完了で投票フェーズへ遷移すべき。
        """
        messages: list[str] = []
        human = self._game.find_player(self._human_player_name, alive_only=True)

        if human is not None:
            self._game = self._game.add_log(f"[発言] {human.name}: {message}")
            messages.append(f"{human.name}: {message}")

            ordered = get_alive_speaking_order(self._game, self._speaking_order)
            human_idx = next(i for i, p in enumerate(ordered) if p.name == self._human_player_name)
            after = [p for p in ordered[human_idx + 1 :] if p.name in self._providers]
            after_msgs = self._run_ai_discussion(after)
            messages.extend(after_msgs)

        max_rounds = get_discussion_rounds(self._game.day)
        if self._discussion_round < max_rounds:
            # 次ラウンドの AI 発言を実行
            next_msgs = self.advance_discussion()
            messages.extend(next_msgs)
            return messages, False
        else:
            self._discussion_round = 0
            return messages, True

    def handle_user_vote(self, target_name: str) -> tuple[dict[str, str], Team | None]:
        """ユーザー投票を処理し、AI投票→集計→処刑→勝利判定を行う。

        Returns:
            (投票結果dict, 勝利陣営またはNone) のタプル
        """
        votes: dict[str, str] = {}

        human = self._game.find_player(self._human_player_name, alive_only=True)
        if human is not None:
            votes[human.name] = target_name

        self._collect_ai_votes(votes)
        self._log_votes(votes)
        winner = self._execute_votes(votes)
        return votes, winner

    def handle_auto_vote(self) -> tuple[dict[str, str], Team | None]:
        """ユーザー死亡時に AI のみで投票を行う。

        Returns:
            (投票結果dict, 勝利陣営またはNone) のタプル
        """
        votes: dict[str, str] = {}
        self._collect_ai_votes(votes)
        self._log_votes(votes)
        winner = self._execute_votes(votes)
        return votes, winner

    def start_night(self) -> bool:
        """夜フェーズを開始する。

        Returns:
            True ならユーザーに夜行動がある（NIGHT_ACTION ステップへ遷移すべき）。
            False なら即座に resolve_night を呼ぶべき。
        """
        self._game = self._game.add_log(f"--- Night {self._game.day} （夜フェーズ） ---")
        self._game = replace(self._game, phase=Phase.NIGHT)

        if self._human_has_night_action() and self.get_night_action_candidates():
            return True
        return False

    def get_night_action_type(self) -> NightActionType | None:
        """ユーザーの夜行動タイプを返す。"""
        human = self._game.find_player(self._human_player_name, alive_only=True)
        if human is None:
            return None
        return human.role.night_action_type

    def get_night_action_candidates(self) -> list[Player]:
        """ユーザーの夜行動の対象候補を返す。"""
        human = self._game.find_player(self._human_player_name, alive_only=True)
        if human is None:
            return []
        return list(get_night_action_candidates(self._game, human))

    def resolve_night(
        self,
        human_divine_target: str | None = None,
        human_attack_target: str | None = None,
        human_guard_target: str | None = None,
    ) -> tuple[list[str], Team | None]:
        """夜フェーズを解決する（占い + 護衛 + 襲撃 + 勝利判定）。

        Returns:
            (夜メッセージリスト, 勝利陣営またはNone) のタプル
        """
        night_messages: list[str] = []

        # 占い → 護衛 → 襲撃 の順に解決
        divine_result = self._resolve_divine(human_divine_target)
        guard_target_name = self._resolve_guard(human_guard_target)
        attack_target_name = self._resolve_attack(human_attack_target)

        # 襲撃処理（護衛判定を含む）
        attacked_name: str | None = None
        if attack_target_name is not None:
            if guard_target_name is not None and guard_target_name == attack_target_name:
                # 護衛成功（GJ）
                self._game = self._game.add_log(f"[護衛成功] {attack_target_name} への襲撃は護衛により阻止された")
                self._game = self._game.add_log("[襲撃] 今夜は誰も襲撃されなかった")
                night_messages.append("今夜は誰も襲撃されなかった")
            else:
                attack_target = self._game.find_player(attack_target_name, alive_only=True)
                if attack_target is not None:
                    dead_player = attack_target.killed()
                    self._game = self._game.replace_player(attack_target, dead_player)
                    self._game = self._game.add_log(f"[襲撃] {attack_target.name} が人狼に襲撃された")
                    night_messages.append(f"{attack_target.name} が人狼に襲撃された")
                    attacked_name = attack_target.name

                    # 占い師が襲撃された場合、占い結果は無効
                    if divine_result is not None and attack_target.name == divine_result[0]:
                        divine_result = None

        # 占い結果を記録
        if divine_result is not None:
            seer_name, target_name_rec, _ = divine_result
            self._game = self._game.add_divine_history(seer_name, target_name_rec)

        # 発言順を回転
        if attacked_name is not None:
            self._speaking_order = rotate_speaking_order(self._speaking_order, attacked_name)

        # 次の日へ
        self._game = replace(self._game, phase=Phase.DAY, day=self._game.day + 1)

        winner = check_victory(self._game)
        return night_messages, winner

    # --- private methods ---

    def _notify_progress(self, player_name: str, action_type: str) -> None:
        """進捗コールバックを呼び出す。"""
        if self._on_progress is not None:
            self._on_progress(player_name, action_type)

    def _notify_message(self, player_name: str, text: str) -> None:
        """発言完了コールバックを呼び出す。"""
        if self._on_message is not None:
            self._on_message(player_name, text)

    def _run_ai_discussion(self, players: list[Player]) -> list[str]:
        """指定 AI プレイヤーの発言を実行し、発言メッセージリストを返す。"""
        messages: list[str] = []
        for player in players:
            self._notify_progress(player.name, "discuss")
            provider = self._providers[player.name]
            result = provider.discuss(self._game, player)
            if result.thinking:
                self._game = self._game.add_log(f"[思考] {player.name}: {result.thinking}")
            self._game = self._game.add_log(f"[発言] {player.name}: {result.message}")
            messages.append(f"{player.name}: {result.message}")
            self._notify_message(player.name, result.message)
        return messages

    def _collect_ai_votes(self, votes: dict[str, str]) -> None:
        """AI プレイヤーの投票を収集する（ログ記録は行わない）。"""
        for player in self._game.alive_players:
            if player.name == self._human_player_name:
                continue
            if player.name not in self._providers:
                continue
            self._notify_progress(player.name, "vote")
            candidates = tuple(p for p in self._game.alive_players if p.name != player.name)
            provider = self._providers[player.name]
            ai_target = provider.vote(self._game, player, candidates)
            thinking = getattr(provider, "last_thinking", "")
            if thinking:
                self._game = self._game.add_log(f"[思考] {player.name}: {thinking}")
            votes[player.name] = ai_target

    def _log_votes(self, votes: dict[str, str]) -> None:
        """全投票をまとめてログに記録する。"""
        for voter, target in votes.items():
            self._game = self._game.add_log(f"[投票] {voter} → {target}")

    def _execute_votes(self, votes: dict[str, str]) -> Team | None:
        """投票を集計・処刑し、勝利判定を行う。"""
        executed_name = tally_votes(votes, self._rng)
        if executed_name is None:
            return None

        vote_counts = Counter(votes.values())

        executed_player = self._game.find_player(executed_name, alive_only=True)
        if executed_player is not None:
            is_werewolf = executed_player.role == Role.WEREWOLF
            dead_player = executed_player.killed()
            self._game = self._game.replace_player(executed_player, dead_player)
            self._game = self._game.add_log(
                f"[処刑] {executed_player.name} が処刑された（得票数: {vote_counts[executed_name]}）"
            )
            # 霊媒結果を記録
            self._game = self._game.add_medium_result(self._game.day, executed_player.name, is_werewolf)

        return check_victory(self._game)

    def _human_has_night_action(self) -> bool:
        """ユーザーが夜行動を持つか判定する。"""
        human = self._game.find_player(self._human_player_name, alive_only=True)
        if human is None:
            return False
        return human.role.has_night_action

    def _resolve_divine(self, human_target: str | None = None) -> tuple[str, str, bool] | None:
        """占いを実行する。結果は (seer_name, target_name, is_werewolf) または None。"""
        seer = find_night_actor(self._game, NightActionType.DIVINE)
        if seer is None:
            return None

        candidates = get_night_action_candidates(self._game, seer)
        if not candidates:
            return None

        if seer.name == self._human_player_name:
            if human_target is None:
                return None
            target_name = human_target
        else:
            self._notify_progress(seer.name, "divine")
            provider = self._providers[seer.name]
            target_name = provider.divine(self._game, seer, candidates)
            thinking = getattr(provider, "last_thinking", "")
            if thinking:
                self._game = self._game.add_log(f"[思考] {seer.name}: {thinking}")

        self._game, result = execute_divine(self._game, seer, target_name)
        return result

    def _resolve_guard(self, human_target: str | None = None) -> str | None:
        """護衛を実行する。護衛対象名または None を返す。"""
        knight = find_night_actor(self._game, NightActionType.GUARD)
        if knight is None:
            return None

        candidates = get_night_action_candidates(self._game, knight)
        if not candidates:
            return None

        if knight.name == self._human_player_name:
            if human_target is None:
                return None
            target_name = human_target
        else:
            self._notify_progress(knight.name, "guard")
            provider = self._providers[knight.name]
            target_name = provider.guard(self._game, knight, candidates)
            thinking = getattr(provider, "last_thinking", "")
            if thinking:
                self._game = self._game.add_log(f"[思考] {knight.name}: {thinking}")

        self._game, guard_target = execute_guard(self._game, knight, target_name)
        return guard_target

    def _resolve_attack(self, human_target: str | None = None) -> str | None:
        """襲撃を実行する。襲撃対象名または None を返す。"""
        werewolf = find_night_actor(self._game, NightActionType.ATTACK)
        if werewolf is None:
            return None

        candidates = get_night_action_candidates(self._game, werewolf)
        if not candidates:
            return None

        if werewolf.name == self._human_player_name:
            if human_target is None:
                return None
            target_name = human_target
        else:
            self._notify_progress(werewolf.name, "attack")
            provider = self._providers[werewolf.name]
            target_name = provider.attack(self._game, werewolf, candidates)
            thinking = getattr(provider, "last_thinking", "")
            if thinking:
                self._game = self._game.add_log(f"[思考] {werewolf.name}: {thinking}")

        self._game, attack_target = execute_attack(self._game, werewolf, target_name)
        return attack_target
