"""LLM用プロンプトテンプレートの生成。

各アクション (discuss, vote, divine, attack) に対応するシステムプロンプトと
ユーザープロンプトを生成する。
"""

from __future__ import annotations

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import format_log_for_context
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role

_BASE_RULES = """\
あなたは人狼ゲームに参加しているプレイヤーです。
日本語で自然に会話してください。

## ゲームルール
- プレイヤーは5人（村人3、占い師1、人狼1）
- 昼フェーズ: 議論 → 投票 → 最多票のプレイヤーが処刑される（同数時はランダム）
- 夜フェーズ: 人狼が1人を襲撃 / 占い師が1人を占う
- 村人陣営の勝利条件: 人狼を処刑する
- 人狼陣営の勝利条件: 村人陣営の生存者が人狼の数以下になる
- 投票は公開（誰が誰に投票したか全員に見える）
- 処刑されたプレイヤーの役職は公開されない

## 用語
- 処刑: 投票により最多得票者を排除すること
- 襲撃: 夜フェーズで人狼が村人を殺害する行為
- 占い: 夜フェーズで占い師が対象の正体を確認する行為
- 黒: 人狼（またはその疑いがある）こと。例:「Aさんの発言は黒っぽい」
- 白: 人狼でない（またはその可能性が高い）こと。例:「占い結果、Bさんは白だった」"""

_ROLE_INSTRUCTIONS: dict[Role, str] = {
    Role.VILLAGER: """\
## あなたの役職: 村人
- 特殊能力はありません
- 議論での発言や投票の傾向から人狼を推理してください
- 怪しいと思うプレイヤーに投票して処刑を目指しましょう""",
    Role.SEER: """\
## あなたの役職: 占い師
- 毎晩1人を占い、そのプレイヤーが人狼かどうかを知ることができます
- 占い結果を活用して村人陣営を勝利に導いてください
- 占い師であることを公表するかどうかは戦略的に判断してください
- 人狼に襲撃されないよう注意しましょう""",
    Role.WEREWOLF: """\
## あなたの役職: 人狼
- 毎晩1人を襲撃して殺害できます
- 自分が人狼であることを悟られないよう、村人のふりをしてください
- 占い師に占われると正体がバレるので、占い師を早めに排除することを検討しましょう
- 議論では村人陣営に疑いを向けるよう誘導しましょう""",
}


def build_system_prompt(role: Role) -> str:
    """役職に応じたシステムプロンプトを生成する。

    Args:
        role: プレイヤーの役職

    Returns:
        システムプロンプト文字列
    """
    return f"{_BASE_RULES}\n\n{_ROLE_INSTRUCTIONS[role]}"


def _format_candidates(candidates: tuple[Player, ...]) -> str:
    """候補者リストを箇条書きに整形する。"""
    return "\n".join(f"- {c.name}" for c in candidates)


def _build_context(game: GameState, player: Player) -> str:
    """ゲームコンテキスト（状況 + ログ）を生成する。"""
    alive_names = "、".join(p.name for p in game.alive_players)
    game_log = format_log_for_context(game, player.name)

    parts = [
        f"現在: {game.day}日目の{'昼' if game.phase.value == 'day' else '夜'}フェーズ",
        f"生存者: {alive_names}",
    ]
    if game_log:
        parts.append(f"\n## これまでのログ\n{game_log}")

    return "\n".join(parts)


def build_discuss_prompt(game: GameState, player: Player) -> str:
    """議論フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        player: 発言するプレイヤー

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, player)
    return f"""{context}

あなたは{player.name}です。議論での発言内容を返してください。
短く簡潔に、1〜3文程度で発言してください。"""


def build_vote_prompt(game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
    """投票フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        player: 投票するプレイヤー
        candidates: 投票候補者（自分を除く生存者）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, player)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{player.name}です。以下の候補者から処刑したいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

投票先の名前のみを返してください。"""


def build_divine_prompt(game: GameState, seer: Player, candidates: tuple[Player, ...]) -> str:
    """占いフェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        seer: 占い師プレイヤー
        candidates: 占い候補者（自分と占い済みを除く生存者）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, seer)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{seer.name}（占い師）です。以下の候補者から占いたいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

占い対象の名前のみを返してください。"""


def build_attack_prompt(game: GameState, werewolf: Player, candidates: tuple[Player, ...]) -> str:
    """襲撃フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        werewolf: 人狼プレイヤー
        candidates: 襲撃候補者（自分を除く生存者）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, werewolf)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{werewolf.name}（人狼）です。以下の候補者から襲撃したいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

襲撃対象の名前のみを返してください。"""
