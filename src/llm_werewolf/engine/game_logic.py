"""両エンジン共通のゲームロジック関数。

GameEngine（一括実行）と InteractiveGameEngine（ステップ実行）が
共有するビジネスロジックを提供する。
"""

from __future__ import annotations

import random
from collections import Counter

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import can_attack, can_divine
from llm_werewolf.domain.value_objects import Role


def find_player(game: GameState, name: str, *, alive_only: bool = False) -> Player | None:
    """プレイヤーを検索する。alive_only=True の場合は生存者のみ。"""
    players = game.alive_players if alive_only else game.players
    for p in players:
        if p.name == name:
            return p
    return None


def get_alive_speaking_order(game: GameState, speaking_order: tuple[str, ...]) -> list[Player]:
    """speaking_order に基づき生存プレイヤーを発言順で返す。"""
    if not speaking_order:
        return list(game.alive_players)
    alive_names = {p.name for p in game.alive_players}
    name_to_player = {p.name: p for p in game.alive_players}
    return [name_to_player[name] for name in speaking_order if name in alive_names]


def notify_divine_result(game: GameState) -> GameState:
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
    last_target = find_player(game, last_target_name)
    if last_target is not None:
        is_werewolf = last_target.role == Role.WEREWOLF
        result_text = "人狼" if is_werewolf else "人狼ではない"
        game = game.add_log(f"[占い結果] {seer.name} の占い: {last_target_name} は {result_text}")

    return game


def get_divine_candidates(game: GameState, seer: Player) -> tuple[Player, ...]:
    """占い可能な対象候補を取得する。"""
    already_divined = set(game.get_divined_history(seer.name))
    return tuple(p for p in game.alive_players if p.name != seer.name and p.name not in already_divined)


def execute_divine(game: GameState, seer: Player, target_name: str) -> tuple[GameState, tuple[str, str, bool] | None]:
    """占い対象名が確定した後の占い実行（検証＋ログ）。"""
    target = find_player(game, target_name, alive_only=True)
    if target is None:
        return game, None

    try:
        can_divine(game, seer, target)
    except ValueError:
        return game, None

    is_werewolf = target.role == Role.WEREWOLF
    game = game.add_log(f"[占い] {seer.name} が {target.name} を占った")
    return game, (seer.name, target_name, is_werewolf)


def get_attack_candidates(game: GameState) -> tuple[Player, ...]:
    """襲撃可能な対象候補を取得する。"""
    return tuple(p for p in game.alive_players if p.role != Role.WEREWOLF)


def execute_attack(game: GameState, werewolf: Player, target_name: str) -> tuple[GameState, str | None]:
    """襲撃対象名が確定した後の襲撃実行（検証のみ、キルは呼び出し側で行う）。"""
    target = find_player(game, target_name, alive_only=True)
    if target is None:
        return game, None

    try:
        can_attack(game, werewolf, target)
    except ValueError:
        return game, None

    return game, target_name


def tally_votes(votes: dict[str, str], rng: random.Random) -> str | None:
    """投票を集計し、処刑対象の名前を返す。同票時はランダム。"""
    if not votes:
        return None

    vote_counts = Counter(votes.values())
    max_votes = max(vote_counts.values())
    top_candidates = [name for name, count in vote_counts.items() if count == max_votes]
    return rng.choice(top_candidates) if len(top_candidates) > 1 else top_candidates[0]


def rotate_speaking_order(speaking_order: tuple[str, ...], removed_name: str) -> tuple[str, ...]:
    """襲撃された人の次から発言順を回転させる（襲撃された人は除外）。"""
    order = list(speaking_order)
    if removed_name not in order:
        return speaking_order
    idx = order.index(removed_name)
    rotated = order[idx + 1 :] + order[:idx]
    return tuple(rotated)


def get_discussion_rounds(day: int) -> int:
    """議論ラウンド数を返す。Day 1 は 1巡、Day 2 以降は 2巡。"""
    return 1 if day == 1 else 2
