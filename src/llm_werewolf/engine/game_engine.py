import random
from collections import Counter
from dataclasses import replace

from llm_werewolf.domain.game import GameState
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


class GameEngine:
    """ゲーム進行エンジン。

    昼議論→投票→処刑→夜行動→勝利判定のゲームループを管理する。
    """

    def __init__(
        self,
        game: GameState,
        providers: dict[str, ActionProvider],
        rng: random.Random | None = None,
    ) -> None:
        self._game = game
        self._providers = providers
        self._rng = rng if rng is not None else random.Random()
        # 発言順をランダムに決定
        names = [p.name for p in game.players]
        self._speaking_order: tuple[str, ...] = tuple(self._rng.sample(names, len(names)))

    @property
    def game(self) -> GameState:
        return self._game

    def run(self) -> GameState:
        """ゲーム終了までループを実行し、最終状態を返す。"""
        self._game = self._game.add_log("=== ゲーム開始 ===")
        self._game = self._log_role_assignment()

        while True:
            # 昼フェーズ
            self._game = self._day_phase()
            winner = check_victory(self._game)
            if winner is not None:
                self._game = self._log_winner(winner)
                return self._game

            # 夜フェーズ
            self._game = self._night_phase()
            winner = check_victory(self._game)
            if winner is not None:
                self._game = self._log_winner(winner)
                return self._game

    def _log_role_assignment(self) -> GameState:
        game = self._game
        for player in game.players:
            game = game.add_log(f"[配役] {player.name}: {player.role.value}")
        return game

    def _log_winner(self, winner: Team) -> GameState:
        label = "村人陣営" if winner == Team.VILLAGE else "人狼陣営"
        return self._game.add_log(f"=== ゲーム終了: {label}の勝利 ===")

    def _day_phase(self) -> GameState:
        game = self._game
        game = game.add_log(f"--- Day {game.day} （昼フェーズ） ---")

        # 占い結果通知 (Day 2以降)
        game = notify_divine_result(game)

        # 霊媒結果通知 (Day 2以降)
        game = notify_medium_result(game)

        # 議論
        game = self._discussion_phase(game)

        # 投票・処刑
        game = self._vote_and_execution_phase(game)

        return game

    def _night_phase(self) -> GameState:
        game = self._game
        game = game.add_log(f"--- Night {game.day} （夜フェーズ） ---")
        game = replace(game, phase=Phase.NIGHT)

        # 占い → 護衛 → 襲撃 の順に解決
        game, divine_result = self._resolve_divine(game)
        game, guard_target_name = self._resolve_guard(game)
        game, attack_target_name = self._resolve_attack(game)

        # 襲撃処理（護衛判定を含む）
        attacked_name: str | None = None
        if attack_target_name is not None:
            if guard_target_name is not None and guard_target_name == attack_target_name:
                # 護衛成功（GJ）
                game = game.add_log(f"[護衛成功] {attack_target_name} への襲撃は護衛により阻止された")
                game = game.add_log("[襲撃] 今夜は誰も襲撃されなかった")
            else:
                target = game.find_player(attack_target_name, alive_only=True)
                if target is not None:
                    dead_player = target.killed()
                    game = game.replace_player(target, dead_player)
                    game = game.add_log(f"[襲撃] {target.name} が人狼に襲撃された")
                    attacked_name = target.name

                    # 占い師が襲撃された場合、占い結果は無効
                    if divine_result is not None:
                        seer_name, _, _ = divine_result
                        if target.name == seer_name:
                            divine_result = None

        # 占い結果を記録（占い師が生存している場合のみ）
        if divine_result is not None:
            seer_name, target_name, _ = divine_result
            game = game.add_divine_history(seer_name, target_name)

        # 襲撃された人の次から発言順を回転
        if attacked_name is not None:
            self._speaking_order = rotate_speaking_order(self._speaking_order, attacked_name)

        # 次の日へ
        game = replace(game, phase=Phase.DAY, day=game.day + 1)
        return game

    def _discussion_phase(self, game: GameState) -> GameState:
        rounds = get_discussion_rounds(game.day)
        ordered = get_alive_speaking_order(game, self._speaking_order)
        for round_num in range(1, rounds + 1):
            game = game.add_log(f"[議論] ラウンド {round_num}")
            for player in ordered:
                provider = self._providers[player.name]
                message = provider.discuss(game, player)
                game = game.add_log(f"[発言] {player.name}: {message}")
        return game

    def _vote_and_execution_phase(self, game: GameState) -> GameState:
        votes: dict[str, str] = {}
        for player in game.alive_players:
            candidates = tuple(p for p in game.alive_players if p.name != player.name)
            provider = self._providers[player.name]
            target_name = provider.vote(game, player, candidates)
            votes[player.name] = target_name
            game = game.add_log(f"[投票] {player.name} → {target_name}")

        # 集計
        executed_name = tally_votes(votes, self._rng)

        # 処刑
        if executed_name is not None:
            target = game.find_player(executed_name, alive_only=True)
            if target is not None:
                vote_counts = Counter(votes.values())
                is_werewolf = target.role == Role.WEREWOLF
                dead_player = target.killed()
                game = game.replace_player(target, dead_player)
                game = game.add_log(f"[処刑] {target.name} が処刑された（得票数: {vote_counts[executed_name]}）")
                # 霊媒結果を記録
                game = game.add_medium_result(game.day, target.name, is_werewolf)

        return game

    def _resolve_divine(self, game: GameState) -> tuple[GameState, tuple[str, str, bool] | None]:
        """占いを実行し、更新された game と結果を返す。結果は (seer_name, target_name, is_werewolf) または None。"""
        seer = find_night_actor(game, NightActionType.DIVINE)
        if seer is None:
            return game, None

        candidates = get_night_action_candidates(game, seer)
        if not candidates:
            return game, None

        provider = self._providers[seer.name]
        target_name = provider.divine(game, seer, candidates)
        return execute_divine(game, seer, target_name)

    def _resolve_guard(self, game: GameState) -> tuple[GameState, str | None]:
        """護衛を実行し、更新された game と護衛対象の名前を返す。"""
        knight = find_night_actor(game, NightActionType.GUARD)
        if knight is None:
            return game, None

        candidates = get_night_action_candidates(game, knight)
        if not candidates:
            return game, None

        provider = self._providers[knight.name]
        target_name = provider.guard(game, knight, candidates)
        return execute_guard(game, knight, target_name)

    def _resolve_attack(self, game: GameState) -> tuple[GameState, str | None]:
        """襲撃を実行し、更新された game と対象の名前を返す。"""
        werewolf = find_night_actor(game, NightActionType.ATTACK)
        if werewolf is None:
            return game, None

        candidates = get_night_action_candidates(game, werewolf)
        if not candidates:
            return game, None

        provider = self._providers[werewolf.name]
        target_name = provider.attack(game, werewolf, candidates)
        return execute_attack(game, werewolf, target_name)
