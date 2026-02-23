"""LLM用プロンプトテンプレートの生成。

各アクション (discuss, vote, divine, attack) に対応するシステムプロンプトと
ユーザープロンプトを生成する。人格特性システムによりAIプレイヤーごとに
異なる性格・口調を付与し、議論の多様性を実現する。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import format_log_for_context
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role


@dataclass(frozen=True)
class PersonalityTrait:
    """人格特性の1要素。カテゴリ（軸）とプロンプト用テキストを保持する。"""

    category: str
    description: str


# --- 特性軸の定義 ---

SPEAKING_STYLES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(category="口調", description="丁寧語で話す。「〜です」「〜ます」を使う"),
    PersonalityTrait(category="口調", description="カジュアルな口調で話す。「〜だよね」「〜じゃん」を使う"),
    PersonalityTrait(
        category="口調",
        description="やや挑発的な口調で話す。「〜なんじゃない？」「本当にそう思ってる？」のように問いかける",
    ),
    PersonalityTrait(
        category="口調", description="穏やかで優しい口調で話す。「〜かもしれないね」「〜だといいんだけど」を使う"
    ),
)

DISCUSSION_ATTITUDES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(category="議論態度", description="積極的に疑いを指摘する。怪しいと感じたらすぐに追及する"),
    PersonalityTrait(category="議論態度", description="慎重に根拠を求める。発言の論理的な裏付けを重視する"),
    PersonalityTrait(category="議論態度", description="全体の意見をまとめようとする。対立する意見の共通点を見つける"),
    PersonalityTrait(category="議論態度", description="直感を大事にする。第一印象や雰囲気で判断し、それを率直に伝える"),
)

THINKING_STYLES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(
        category="思考スタイル", description="論理的・分析的に考える。投票パターンや発言の整合性を重視する"
    ),
    PersonalityTrait(category="思考スタイル", description="感情的・共感的に考える。プレイヤーの態度や感情の変化に敏感"),
    PersonalityTrait(category="思考スタイル", description="観察重視で考える。発言量の変化や沈黙のタイミングに注目する"),
    PersonalityTrait(category="思考スタイル", description="戦略的に考える。誰を残すべきか、陣営全体の利益を意識する"),
)

TRAIT_CATEGORIES: tuple[tuple[PersonalityTrait, ...], ...] = (
    SPEAKING_STYLES,
    DISCUSSION_ATTITUDES,
    THINKING_STYLES,
)


def assign_personalities(ai_count: int, rng: random.Random) -> list[tuple[PersonalityTrait, ...]]:
    """各AIプレイヤーに特性の組み合わせを割り当てる。

    各特性軸からランダムに1つずつ選択し、AI人数分の組み合わせを生成する。

    Args:
        ai_count: AIプレイヤーの人数
        rng: 乱数生成器

    Returns:
        AI人数分の特性タプルのリスト
    """
    personalities: list[tuple[PersonalityTrait, ...]] = []
    for _ in range(ai_count):
        traits = tuple(rng.choice(category) for category in TRAIT_CATEGORIES)
        personalities.append(traits)
    return personalities


def build_personality(traits: tuple[PersonalityTrait, ...]) -> str:
    """特性リストから人格プロンプトテキストを組み立てる。

    Args:
        traits: 特性のタプル

    Returns:
        プロンプトに埋め込む人格テキスト
    """
    return "\n".join(f"- {t.description}" for t in traits)


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
    Role.KNIGHT: """\
## あなたの役職: 狩人
- 毎晩1人を護衛し、人狼の襲撃から守ることができます
- 占い師など重要な役職を守ることを優先しましょう
- 自分が狩人であることを公表するかどうかは戦略的に判断してください""",
    Role.MEDIUM: """\
## あなたの役職: 霊媒師
- 処刑されたプレイヤーが人狼だったかどうかを知ることができます
- 霊媒結果を活用して村人陣営を勝利に導いてください
- 霊媒師であることを公表するかどうかは戦略的に判断してください""",
    Role.MADMAN: """\
## あなたの役職: 狂人
- 人狼陣営ですが、占いでは村人と判定されます
- 人狼が誰かは分かりませんが、人狼陣営の勝利を目指してください
- 村人のふりをしながら、人狼陣営に有利な議論を誘導しましょう
- 偽の占い師や霊媒師を名乗るなど、村を混乱させる戦略も有効です""",
}


def build_system_prompt(role: Role, personality: str = "") -> str:
    """役職と人格に応じたシステムプロンプトを生成する。

    Args:
        role: プレイヤーの役職
        personality: 人格プロンプトテキスト（空文字列の場合は人格セクションなし）

    Returns:
        システムプロンプト文字列
    """
    parts = [_BASE_RULES, _ROLE_INSTRUCTIONS[role]]
    if personality:
        parts.append(f"## あなたの性格\n{personality}")
    return "\n\n".join(parts)


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
短く簡潔に、1〜3文程度で発言してください。

## 発言のルール
- 発言の冒頭に自分の名前を付けないでください（「{player.name}: 」のような接頭辞は不要です）
- 初日でも他プレイヤーの発言の特徴や態度を具体的に指摘してください
- 「怪しい人はいない」「まだわからない」だけで終わらず、具体的な観察や推理を述べてください"""


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
