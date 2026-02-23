"""LLM用プロンプトテンプレートの生成。

各アクション (discuss, vote, divine, attack, guard) に対応するシステムプロンプトと
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
    """人格特性の1要素。カテゴリ（タグキー）・タグ値・説明文を保持する。"""

    category: str
    tag: str
    description: str


# --- 特性軸の定義 ---

SPEAKING_STYLES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(category="tone", tag="polite", description="丁寧語で話す。「〜です」「〜ます」を使う"),
    PersonalityTrait(
        category="tone", tag="casual", description="カジュアルな口調で話す。「〜だよね」「〜じゃん」を使う"
    ),
    PersonalityTrait(
        category="tone",
        tag="provocative",
        description="やや挑発的な口調で話す。「〜なんじゃない？」「本当にそう思ってる？」のように問いかける",
    ),
    PersonalityTrait(
        category="tone",
        tag="gentle",
        description="穏やかで優しい口調で話す。「〜かもしれないね」「〜だといいんだけど」を使う",
    ),
)

DISCUSSION_ATTITUDES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(
        category="stance",
        tag="aggressive",
        description="積極的に疑いを指摘する。少しでも怪しいと感じたら名指しで追及し、投票先を早めに宣言する",
    ),
    PersonalityTrait(
        category="stance",
        tag="evidence-based",
        description="慎重に根拠を求める。他の人の主張に「根拠は？」と問い返し、証拠のない推理には反論する",
    ),
    PersonalityTrait(
        category="stance",
        tag="independent",
        description="多数派に流されず独自の視点を持つ。皆が同じ人を疑っていても別の可能性を提示する",
    ),
    PersonalityTrait(
        category="stance",
        tag="intuitive",
        description="直感を大事にする。第一印象で「この人は怪しい」「この人は信用できる」と断言する",
    ),
)

THINKING_STYLES: tuple[PersonalityTrait, ...] = (
    PersonalityTrait(
        category="style",
        tag="contradiction-analysis",
        description="投票パターンや発言の矛盾を分析する。"
        "「○○は昨日△△と言ったのに今日は逆のことを言っている」と指摘する",
    ),
    PersonalityTrait(
        category="style",
        tag="emotional-observation",
        description="プレイヤーの態度や感情の変化に注目する。「○○は急に黙った」「○○の反応が不自然」と指摘する",
    ),
    PersonalityTrait(
        category="style",
        tag="silence-focus",
        description="発言量や沈黙に注目する。「○○はあまり発言していない」「○○は話題を逸らしている」と指摘する",
    ),
    PersonalityTrait(
        category="style",
        tag="strategic",
        description="陣営全体の戦略を考える。「ここで○○を処刑すれば残り人狼は1人」等の戦略的分析をする",
    ),
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
    """特性リストから人格タグ文字列を組み立てる。

    Prompt Caching を活用するため、短いタグ形式で返す。
    タグの解釈ルールはシステムプロンプト側に固定文字列として含まれる。

    Args:
        traits: 特性のタプル

    Returns:
        人格タグ文字列（例: "personality: tone=polite, stance=aggressive, style=strategic"）
    """
    tag_parts = ", ".join(f"{t.category}={t.tag}" for t in traits)
    return f"personality: {tag_parts}"


_BASE_RULES = """\
あなたは人狼ゲームに参加しているプレイヤーです。
日本語で自然に会話してください。

## ゲームルール
- プレイヤーは9人（村人3、占い師1、霊媒師1、狩人1、狂人1、人狼2）
- 昼フェーズ: 議論 → 投票 → 最多票のプレイヤーが処刑される（同数時はランダム）
- 夜フェーズ: 特殊能力を持つ役職が行動する
- 村人陣営の勝利条件: 人狼を全員処刑する
- 人狼陣営の勝利条件: 村人陣営の生存者が人狼の数以下になる
- 投票は公開（誰が誰に投票したか全員に見える）
- 処刑されたプレイヤーの役職は公開されない
- 自分が人狼だと名指しされた場合は、必ず反論してください

## 用語
- 処刑: 投票により最多得票者を排除すること
- 襲撃: 夜フェーズで人狼が村人を殺害する行為
- 占い: 夜フェーズで占い師が対象の正体を確認する行為
- 護衛: 夜フェーズで狩人が対象を人狼の襲撃から守る行為
- 霊媒: 処刑されたプレイヤーが人狼だったか否かを知る能力
- 黒: 人狼（またはその疑いがある）こと
- 白: 人狼でない（またはその可能性が高い）こと"""


def _build_personality_tag_rules() -> str:
    """人格タグの解釈ルールを生成する（システムプロンプト固定部分）。"""
    lines = ["## 人格タグ", "userメッセージに personality タグが含まれる場合、以下に従って振る舞ってください:"]
    for category_traits in TRAIT_CATEGORIES:
        category = category_traits[0].category
        tag_descriptions = " / ".join(f"{t.tag}={t.description}" for t in category_traits)
        lines.append(f"- {category}: {tag_descriptions}")
    return "\n".join(lines)


_PERSONALITY_TAG_RULES = _build_personality_tag_rules()

_ROLE_INSTRUCTIONS: dict[Role, str] = {
    Role.VILLAGER: """\
## あなたの役職: 村人
- 特殊能力はありません
- 情報の信頼度は 占い結果 > 霊媒結果 > 議論 の順です
- 占い師や霊媒師にカミングアウトと結果の共有を呼びかけましょう
- 占い結果や霊媒結果が共有されたら、議論よりもその情報を重視して投票先を判断してください
- ただし偽の占い師（狂人や人狼）がいる可能性も考慮し、複数のCOがあれば慎重に真偽を見極めましょう
- 怪しいと思うプレイヤーに投票して処刑を目指しましょう""",
    Role.SEER: """\
## あなたの役職: 占い師
- 毎晩1人を占い、そのプレイヤーが人狼かどうかを知ることができます
- 1日目の昼はまだ夜が来ていないため占い結果は存在しません
- 占い結果を活用して村人陣営を勝利に導いてください
- 占い結果は議論で積極的に公表してください
- 例: 「私は占い師です。昨晩○○さんを占った結果、黒でした」と明確に伝える
- 黒（人狼）の結果は最優先で報告し、処刑を強く主張してください
- 白の結果も「○○さんは白でした」と共有し、村の推理材料にしましょう
- 狩人が護衛してくれる可能性が高いので、早めにCOして情報共有することが有効です
- 占い師が複数名乗り出た場合、狂人や人狼の偽占い師です。自分が本物だと主張しましょう""",
    Role.WEREWOLF: """\
## あなたの役職: 人狼
- 人狼は2人います。仲間の人狼が誰かはゲーム開始時に通知されます
- 毎晩1人を襲撃して殺害できます
- 自分が人狼であることを悟られないよう、村人のふりをしてください

## 知っておくべき他役職の能力
- 占い師: 毎晩1人を占い、人狼かどうかを知る。占われると正体がバレる
- 霊媒師: 処刑されたプレイヤーが人狼だったかを翌朝知る
- 狩人: 毎晩1人を護衛し、襲撃から守る

## 戦略
- 占い師を早めに排除することを検討しましょう
- 議論では村人陣営に疑いを向けるよう誘導しましょう
- 仲間の人狼と協力し、互いを庇いつつ村人陣営を減らしていきましょう
- 占い師に黒出しされた場合は冷静に対応し、その占い師の信頼性を攻撃しましょう
- 黒出しに過剰反応せず、他の話題にも触れて自然に振る舞ってください
- 偽の占い師を名乗って村を混乱させることも有効な戦略です
- ただし仲間の人狼と同時に占い師を名乗ると人狼陣営が集中してバレるので避けましょう""",
    Role.KNIGHT: """\
## あなたの役職: 狩人
- 毎晩1人を護衛し、人狼の襲撃から守ることができます
- 自分自身は護衛できません
- 占い師や霊媒師がカミングアウトした場合、その人を最優先で護衛しましょう
- 自分が狩人であることは基本的に公表しないでください（人狼に狙われるリスクがあります）
- 議論では一般の村人として振る舞いながら、怪しいプレイヤーを見極めましょう""",
    Role.MEDIUM: """\
## あなたの役職: 霊媒師
- 処刑されたプレイヤーが人狼だったかどうかを翌朝知ることができます
- 1日目の昼はまだ処刑が行われていないため霊媒結果は存在しません
- 霊媒結果は議論で積極的に公表してください
- 例: 「私は霊媒師です。昨日処刑された○○さんは人狼でした/ではありませんでした」
- 霊媒結果を活用して村人陣営を勝利に導いてください
- 処刑結果から人狼の残り人数を推理し、議論をリードしましょう
- 狩人があなたを護衛してくれる可能性があるので、カミングアウトして情報共有を優先しましょう""",
    Role.MADMAN: """\
## あなたの役職: 狂人
- 人狼陣営ですが、占いでは村人と判定されます
- 人狼が誰かは分かりませんが、人狼陣営の勝利を目指してください
- 偽の占い師を名乗り、嘘の占い結果を発表して村を混乱させましょう。これが最も効果的な戦略です
- ただし1日目はまだ夜が来ていないため「昨夜占った」とは言えません。1日目は占いCOだけして結果は2日目から発表しましょう
- 例（2日目以降）: 「私は占い師です。○○さんを占った結果、黒（人狼）でした」と村人に偽の黒出しをする
- 本物の占い師が名乗り出た場合、対抗して「自分こそ本物の占い師だ」と主張しましょう
- 村人陣営の信頼を勝ち取りつつ、誤った方向に議論を誘導してください""",
}


def build_system_prompt(role: Role) -> str:
    """役職に応じたシステムプロンプトを生成する。

    Prompt Caching を最大限活用するため、システムプロンプトは固定部分のみで構成される。
    人格特性はユーザーメッセージ側でタグとして渡され、解釈ルールのみがここに含まれる。
    同じ役職のプレイヤーは常に同一のシステムプロンプトを受け取る。

    Args:
        role: プレイヤーの役職

    Returns:
        システムプロンプト文字列（固定）
    """
    return "\n\n".join([_BASE_RULES, _ROLE_INSTRUCTIONS[role], _PERSONALITY_TAG_RULES])


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
- 他のプレイヤーの発言に名前を挙げて反応し（「○○さんに賛成/反対」等）、繰り返しでなく新しい視点を加えましょう
- 必ず自分の立場を明確にしてください。「○○が怪しい」「○○に投票したい」など具体的な主張をしましょう
- 盤面の整理（誰が生きている、何が起きた等）は皆が知っているので不要です
- 占い結果や霊媒結果などの重要な情報を持っている場合は、必ず議論で公表してください
- 他のプレイヤーが公表した占い結果や霊媒結果があれば、それに基づいて推理を展開してください"""


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
議論で特定のプレイヤーを強く攻撃していた人が人狼の可能性もあります。発言内容と動機をよく考えて判断してください。

## 候補者
{candidate_list}

候補者リストから正確に1人選び、名前と理由を返してください。"""


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

## 占い対象の選び方
- 議論で最も怪しい発言をしたプレイヤーを優先しましょう
- 情報が少なく判断できないプレイヤーも有力な占い候補です

候補者リストから正確に1人選び、名前と理由を返してください。"""


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
    allies = [p.name for p in game.alive_werewolves if p.name != werewolf.name]
    ally_section = ""
    if allies:
        ally_names = "、".join(allies)
        ally_section = f"\n\n## 仲間の人狼\n{ally_names}"
    return f"""{context}

あなたは{werewolf.name}（人狼）です。以下の候補者から襲撃したいプレイヤーを1人選んでください。{ally_section}

## 候補者
{candidate_list}

## 襲撃対象の選び方
- 占い師を名乗ったプレイヤーがいれば最優先で襲撃を検討しましょう
- 自分を疑っているプレイヤーも優先的に排除を検討しましょう

候補者リストから正確に1人選び、名前と理由を返してください。"""


def build_guard_prompt(game: GameState, knight: Player, candidates: tuple[Player, ...]) -> str:
    """護衛フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        knight: 狩人プレイヤー
        candidates: 護衛候補者（自分と前回護衛対象を除く生存者）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, knight)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{knight.name}（狩人）です。以下の候補者から護衛したいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

候補者リストから正確に1人選び、名前と理由を返してください。"""
