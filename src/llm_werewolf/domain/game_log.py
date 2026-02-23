"""ゲームログのフィルタリング・整形（ドメインサービス）。

Step 2 で LLM に渡すコンテキスト用に、プレイヤー視点でログをフィルタリングする。
"""

from __future__ import annotations

from collections.abc import Sequence

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role

_PRIVATE_PREFIXES = ("[配役]", "[占い結果]", "[占い]", "[護衛]", "[霊媒結果]", "[人狼仲間]", "[護衛成功]")


def _is_visible(log_entry: str, player: Player) -> bool:
    """ログエントリがプレイヤーに見えるかどうか判定する。

    フィルタリングルール:
    - [配役]: 自分の配役のみ見える
    - [占い結果]: 占い師本人のみ見える
    - [占い]: 占い師本人のみ見える
    - [護衛]: 狩人本人のみ見える
    - [霊媒結果]: 霊媒師本人のみ見える
    - [人狼仲間]: 人狼のみ見える
    - その他: 全員に見える
    """
    if log_entry.startswith("[配役]"):
        return player.name in log_entry

    if log_entry.startswith("[占い結果]"):
        return player.role == Role.SEER and player.name in log_entry

    if log_entry.startswith("[占い]"):
        return player.role == Role.SEER and player.name in log_entry

    if log_entry.startswith("[護衛]"):
        return player.role == Role.KNIGHT and player.name in log_entry

    if log_entry.startswith("[霊媒結果]"):
        return player.role == Role.MEDIUM and player.name in log_entry

    if log_entry.startswith("[人狼仲間]"):
        return player.role == Role.WEREWOLF

    return True


def filter_log_entries(entries: Sequence[str], player: Player) -> str:
    """任意のログエントリ列をプレイヤー視点でフィルタリングして文字列を返す。

    Args:
        entries: ログエントリのシーケンス
        player: 視点プレイヤー

    Returns:
        フィルタリング済みのログ文字列（改行区切り）
    """
    visible = [entry for entry in entries if _is_visible(entry, player)]
    return "\n".join(visible)


def format_log_for_context(game: GameState, player_name: str) -> str:
    """プレイヤー視点でフィルタリングしたゲームログを返す。

    Args:
        game: ゲーム状態
        player_name: 視点プレイヤーの名前

    Returns:
        フィルタリング済みのログ文字列（改行区切り）

    Raises:
        ValueError: 指定された名前のプレイヤーが存在しない場合
    """
    player = game.find_player(player_name)
    if player is None:
        raise ValueError(f"Player '{player_name}' not found in game")

    return filter_log_entries(game.log, player)


def format_public_log(game: GameState) -> str:
    """全プレイヤーに見える公開ログのみを返す。GM-AI の入力用。

    Args:
        game: ゲーム状態

    Returns:
        公開ログ文字列（改行区切り）
    """
    public = [entry for entry in game.log if not any(entry.startswith(p) for p in _PRIVATE_PREFIXES)]
    return "\n".join(public)
