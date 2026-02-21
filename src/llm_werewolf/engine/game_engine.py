import random
from collections import Counter
from dataclasses import replace

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import can_attack, can_divine, check_victory
from llm_werewolf.domain.value_objects import Phase, Role, Team
from llm_werewolf.engine.action_provider import ActionProvider


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
        game = self._notify_divine_result(game)

        # 議論
        game = self._discussion_phase(game)

        # 投票・処刑
        game = self._vote_and_execution_phase(game)

        return game

    def _night_phase(self) -> GameState:
        game = self._game
        game = game.add_log(f"--- Night {game.day} （夜フェーズ） ---")
        game = replace(game, phase=Phase.NIGHT)

        # 占い・襲撃を実行
        game, divine_result = self._resolve_divine(game)
        game, attack_target_name = self._resolve_attack(game)

        # 襲撃処理
        if attack_target_name is not None:
            target = self._find_alive_player(game, attack_target_name)
            if target is not None:
                dead_player = target.killed()
                game = game.replace_player(target, dead_player)
                game = game.add_log(f"[襲撃] {target.name} が人狼に襲撃された")

                # 占い師が襲撃された場合、占い結果は無効
                if divine_result is not None:
                    seer_name, _, _ = divine_result
                    if target.name == seer_name:
                        divine_result = None

        # 占い結果を記録（占い師が生存している場合のみ）
        if divine_result is not None:
            seer_name, target_name, _ = divine_result
            game = game.add_divine_history(seer_name, target_name)

        # 次の日へ
        game = replace(game, phase=Phase.DAY, day=game.day + 1)
        return game

    def _notify_divine_result(self, game: GameState) -> GameState:
        if game.day < 2:
            return game

        # 前夜の占い結果を通知
        seer_players = [p for p in game.alive_players if p.role == Role.SEER]
        if not seer_players:
            return game

        seer = seer_players[0]
        history = game.get_divined_history(seer.name)
        if not history:
            return game

        # 最新の占い対象を通知
        last_target_name = history[-1]
        last_target = self._find_player_by_name(game, last_target_name)
        if last_target is not None:
            is_werewolf = last_target.role == Role.WEREWOLF
            result_text = "人狼" if is_werewolf else "人狼ではない"
            game = game.add_log(f"[占い結果] {seer.name} の占い: {last_target_name} は {result_text}")

        return game

    def _discussion_phase(self, game: GameState) -> GameState:
        rounds = 1 if game.day == 1 else 2
        for round_num in range(1, rounds + 1):
            game = game.add_log(f"[議論] ラウンド {round_num}")
            for player in game.alive_players:
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
        vote_counts = Counter(votes.values())
        max_votes = max(vote_counts.values())
        top_candidates = [name for name, count in vote_counts.items() if count == max_votes]

        # 同票時はランダム
        executed_name = self._rng.choice(top_candidates) if len(top_candidates) > 1 else top_candidates[0]

        # 処刑
        target = self._find_alive_player(game, executed_name)
        if target is not None:
            dead_player = target.killed()
            game = game.replace_player(target, dead_player)
            game = game.add_log(f"[処刑] {target.name} が処刑された（得票数: {vote_counts[executed_name]}）")

        return game

    def _resolve_divine(self, game: GameState) -> tuple[GameState, tuple[str, str, bool] | None]:
        """占いを実行し、更新された game と結果を返す。結果は (seer_name, target_name, is_werewolf) または None。"""
        seer_players = [p for p in game.alive_players if p.role == Role.SEER]
        if not seer_players:
            return game, None

        seer = seer_players[0]
        # 占い可能な対象を取得
        already_divined = set(game.get_divined_history(seer.name))
        candidates = tuple(p for p in game.alive_players if p.name != seer.name and p.name not in already_divined)
        if not candidates:
            return game, None

        provider = self._providers[seer.name]
        target_name = provider.divine(game, seer, candidates)
        target = self._find_alive_player(game, target_name)
        if target is None:
            return game, None

        try:
            can_divine(game, seer, target)
        except ValueError:
            return game, None
        is_werewolf = target.role == Role.WEREWOLF
        game = game.add_log(f"[占い] {seer.name} が {target.name} を占った")
        return game, (seer.name, target_name, is_werewolf)

    def _resolve_attack(self, game: GameState) -> tuple[GameState, str | None]:
        """襲撃を実行し、更新された game と対象の名前を返す。"""
        werewolves = [p for p in game.alive_players if p.role == Role.WEREWOLF]
        if not werewolves:
            return game, None

        werewolf = werewolves[0]
        candidates = tuple(p for p in game.alive_players if p.role != Role.WEREWOLF)
        if not candidates:
            return game, None

        provider = self._providers[werewolf.name]
        target_name = provider.attack(game, werewolf, candidates)
        target = self._find_alive_player(game, target_name)
        if target is None:
            return game, None

        try:
            can_attack(game, werewolf, target)
        except ValueError:
            return game, None
        return game, target_name

    def _find_alive_player(self, game: GameState, name: str) -> Player | None:
        for p in game.alive_players:
            if p.name == name:
                return p
        return None

    def _find_player_by_name(self, game: GameState, name: str) -> Player | None:
        for p in game.players:
            if p.name == name:
                return p
        return None
