"""LLM用プロンプトテンプレートの生成。

各アクション (discuss, vote, divine, attack, guard) に対応するシステムプロンプトと
ユーザープロンプトを生成する。人格特性システムによりAIプレイヤーごとに
異なる性格・口調を付与し、議論の多様性を実現する。
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import filter_log_entries, format_log_for_context
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.llm_config import DEFAULT_MAX_RECENT_STATEMENTS

logger = logging.getLogger(__name__)


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

# --- 数値感情特性軸の定義 ---
# 感情反応強度: 1=感情を抑えた冷静な表現 / 9=感情を強く外に出す表現
REACTIVITY_LEVELS: tuple[PersonalityTrait, ...] = tuple(
    PersonalityTrait(category="reactivity", tag=str(i), description=f"感情反応強度 {i}/9") for i in range(1, 10)
)
# 感情変動レベル: 1=安定・一貫した感情表現 / 9=激しい変化・予測不能な感情
VOLATILITY_LEVELS: tuple[PersonalityTrait, ...] = tuple(
    PersonalityTrait(category="volatility", tag=str(i), description=f"感情変動 {i}/9") for i in range(1, 10)
)
NUMERIC_TRAIT_CATEGORIES: tuple[tuple[PersonalityTrait, ...], ...] = (
    REACTIVITY_LEVELS,
    VOLATILITY_LEVELS,
)


def assign_personalities(ai_count: int, rng: random.Random) -> list[tuple[PersonalityTrait, ...]]:
    """各AIプレイヤーに特性の組み合わせを割り当てる。

    カテゴリ特性軸（tone/stance/style）は独立にランダム選択し、
    数値感情軸（reactivity/volatility）はシャッフルして重複なく割り当てることで
    プレイヤー間の多様性を保証する。

    Args:
        ai_count: AIプレイヤーの人数
        rng: 乱数生成器

    Returns:
        AI人数分の特性タプルのリスト
    """
    personalities: list[list[PersonalityTrait]] = [
        [rng.choice(category) for category in TRAIT_CATEGORIES] for _ in range(ai_count)
    ]
    for numeric_category in NUMERIC_TRAIT_CATEGORIES:
        shuffled = list(numeric_category)
        rng.shuffle(shuffled)
        for i in range(ai_count):
            personalities[i].append(shuffled[i % len(shuffled)])
    return [tuple(traits) for traits in personalities]


def build_personality(traits: tuple[PersonalityTrait, ...]) -> str:
    """特性リストから人格タグ文字列を組み立てる。

    Prompt Caching を活用するため、短いタグ形式で返す。
    タグの解釈ルールはシステムプロンプト側に固定文字列として含まれる。

    Args:
        traits: 特性のタプル

    Returns:
        人格タグ文字列（例: "personality: tone=polite, stance=aggressive, style=strategic, reactivity=7, volatility=3"）
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
- 自分のことを三人称（名前呼び）で語らないでください。自分に言及する場合は「私」「自分」を使用してください

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
    lines.append(
        "- reactivity: 1〜9の数値。9に近いほど感情を強く外に表現し（怒り・悲しみ・喜びを率直に出す）、"
        "1に近いほど感情を抑えた冷静な発言をする"
    )
    lines.append(
        "- volatility: 1〜9の数値。9に近いほど感情の波が激しく発言ごとに変化しやすい、"
        "1に近いほど安定した一貫した感情表現をする"
    )
    return "\n".join(lines)


_PERSONALITY_TAG_RULES = _build_personality_tag_rules()

_GAME_SUMMARY_SCHEMA = """\
## 盤面情報の読み方
議論の前に、JSON形式で整理された盤面情報が提供される場合があります:
- alive/dead: 生存・死亡者情報
- vote_history: 日ごとの投票履歴
- claims: 役職CO情報と主張した結果
- contradictions: 矛盾点（最大3件）
- player_summaries: 各プレイヤーの立場要約
- role_advice: あなたの役職向けのおすすめ行動（複数の選択肢とメリット・デメリット）
この情報を活用して推理を行ってください。
GMからのアドバイスがある場合は参考にしつつ、最終的な判断は自分で行ってください。"""

_ROLE_INSTRUCTIONS: dict[Role, str] = {
    Role.VILLAGER: """\
## あなたの役職: 村人
- 特殊能力はありません
- 情報の信頼度は 占い結果 > 霊媒結果 > 議論 の順です
- 占い結果や霊媒結果が共有されたら、議論よりもその情報を重視して投票先を判断してください
- ただし偽の占い師（狂人や人狼）がいる可能性も考慮し、複数のCOがあれば慎重に真偽を見極めましょう""",
    Role.SEER: """\
## あなたの役職: 占い師
- 毎晩1人を占い、そのプレイヤーが人狼かどうかを知ることができます
- ゲーム開始時に1人を自動で占い、その結果を持った状態でゲームが始まります（初日占い）
- 占い結果は議論で積極的に公表してください
- 黒（人狼）の結果は最優先で報告し、処刑を強く主張してください
- 白の結果も「○○さんは白でした」と共有し、村の推理材料にしましょう""",
    Role.WEREWOLF: """\
## あなたの役職: 人狼
- 人狼は2人います。仲間の人狼が誰かはゲーム開始時に通知されます
- 毎晩1人を襲撃して殺害できます
- 自分が人狼であることを悟られないよう、村人のふりをしてください
- 占い師に黒出しされた場合は冷静に対応し、その占い師の信頼性を攻撃しましょう
- 黒出しに過剰反応せず、他の話題にも触れて自然に振る舞ってください

## 知っておくべき他役職の能力
- 占い師: 毎晩1人を占い、人狼かどうかを知る。占われると正体がバレる
- 霊媒師: 処刑されたプレイヤーが人狼だったかを翌朝知る
- 狩人: 毎晩1人を護衛し、襲撃から守る""",
    Role.KNIGHT: """\
## あなたの役職: 狩人
- 毎晩1人を護衛し、人狼の襲撃から守ることができます
- 自分自身は護衛できません
- 自分が狩人であることは基本的に公表しないでください（人狼に狙われるリスクがあります）
- 議論では一般の村人として振る舞いながら、怪しいプレイヤーを見極めましょう""",
    Role.MEDIUM: """\
## あなたの役職: 霊媒師
- 処刑されたプレイヤーが人狼だったかどうかを翌朝知ることができます
- 1日目の昼はまだ処刑が行われていないため霊媒結果は存在しません
- 霊媒結果は議論で積極的に公表してください
- 例: 「私は霊媒師です。昨日処刑された○○さんは人狼でした/ではありませんでした」""",
    Role.MADMAN: """\
## あなたの役職: 狂人
- 人狼陣営ですが、占いでは村人と判定されます
- 人狼が誰かは分かりませんが、人狼陣営の勝利を目指してください
- 偽の占い師を名乗り、嘘の占い結果を発表して村を混乱させる戦略があります
- ただし1日目はまだ夜が来ていないため「昨夜占った」とは言えません。1日目は占いCOだけして結果は2日目から発表しましょう
- 占いCO以外にも、潜伏や霊媒COなど状況に応じた立ち回りがあります。GMからのアドバイスを参考にしてください""",
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
    return "\n\n".join([_BASE_RULES, _PERSONALITY_TAG_RULES, _GAME_SUMMARY_SCHEMA, _ROLE_INSTRUCTIONS[role]])


def _format_candidates(candidates: tuple[Player, ...]) -> str:
    """候補者リストを箇条書きに整形する。"""
    return "\n".join(f"- {c.name}" for c in candidates)


_ROLE_NAME_MAP: dict[Role, str] = {
    Role.VILLAGER: "村人",
    Role.SEER: "占い師",
    Role.WEREWOLF: "人狼",
    Role.KNIGHT: "狩人",
    Role.MEDIUM: "霊媒師",
    Role.MADMAN: "狂人",
}


_STANCE_STRATEGY_GUIDANCE: dict[str, str] = {
    "aggressive": ("あなたは攻撃的な性格です。リスクが高くてもリターンが大きい戦略を積極的に検討してください。"),
    "evidence-based": "あなたは証拠重視の性格です。リスクが低く確実な戦略を優先してください。",
    "independent": (
        "あなたは独自の判断を大切にします。他のプレイヤーの意見に流されず、自分の分析に基づいて戦略を選んでください。"
    ),
    "intuitive": ("あなたは直感を重視します。数値だけでなく場の空気や違和感も判断材料にしてください。"),
}


def _extract_role_advice(gm_summary: str, role: Role, *, personality_tag: str = "") -> str:
    """GM 要約 JSON から指定役職のアドバイスを抽出して整形する。

    Args:
        gm_summary: GM 要約の JSON 文字列
        role: プレイヤーの役職
        personality_tag: 人格タグ文字列（例: "personality: tone=polite, stance=aggressive, style=strategic"）

    Returns:
        整形されたアドバイス文字列。該当なしの場合は空文字列。
    """
    role_name = _ROLE_NAME_MAP.get(role, "")
    if not role_name:
        return ""

    try:
        data = json.loads(gm_summary)
    except (json.JSONDecodeError, TypeError):
        logger.debug("GM 要約の JSON パースに失敗しました。アドバイスをスキップします。")
        return ""

    role_advice_list = data.get("role_advice", [])
    if not role_advice_list:
        return ""

    for advice in role_advice_list:
        if advice.get("role") == role_name:
            options = advice.get("options", [])
            if not options:
                return ""
            lines = ["## GMからのアドバイス（参考情報）"]
            for i, option in enumerate(options, 1):
                action = option.get("action", "")
                merit = option.get("merit", "")
                demerit = option.get("demerit", "")
                risk = option.get("risk", "")
                reward = option.get("reward", "")
                score_label = ""
                if risk and reward:
                    score_label = f" [リスク:{risk}/10, リターン:{reward}/10]"
                lines.append(f"### 選択肢{i}: {action}{score_label}")
                lines.append(f"- メリット: {merit}")
                lines.append(f"- デメリット: {demerit}")

            stance_guidance = _extract_stance_guidance(personality_tag)
            if stance_guidance:
                lines.append(f"\n{stance_guidance}")

            return "\n".join(lines)

    return ""


def _extract_stance_guidance(personality_tag: str) -> str:
    """人格タグから stance に応じた戦略指向テキストを抽出する。

    Args:
        personality_tag: 人格タグ文字列

    Returns:
        stance に応じた指示文字列。該当なしの場合は空文字列。
    """
    if not personality_tag:
        return ""
    for stance, guidance in _STANCE_STRATEGY_GUIDANCE.items():
        if f"stance={stance}" in personality_tag:
            return guidance
    return ""


_SITUATION_FIRST_DAY = "初日（情報がない状況）"
_SITUATION_ENDGAME = "終盤（残り人数が少なく一手が勝敗を左右する状況）"
_SITUATION_SUSPECTED = "複数のプレイヤーから疑われている状況"
_SITUATION_GUARD_SUCCESS = "昨夜誰も死ななかった（護衛成功の可能性がある状況）"


def _detect_situation(game: GameState, player: Player) -> str | None:
    """現在のゲーム状況を検出して説明文を返す。

    複数条件が重なる場合は優先度の高い順（初日 > 終盤 > 疑われ > 護衛成功）で返す。

    Args:
        game: ゲーム状態
        player: 視点プレイヤー

    Returns:
        状況の説明文字列。特筆すべき状況がなければ None。
    """
    if game.day == 1:
        return _SITUATION_FIRST_DAY

    if len(game.alive_players) <= 4:
        return _SITUATION_ENDGAME

    recent_votes_against = sum(1 for e in game.log[-30:] if e.startswith("[投票]") and f"→ {player.name}" in e)
    if recent_votes_against >= 2:
        return _SITUATION_SUSPECTED

    for entry in reversed(game.log[-20:]):
        if entry == "[襲撃] 今夜は誰も襲撃されなかった":
            return _SITUATION_GUARD_SUCCESS
        if entry.startswith("[発言]") or entry.startswith("[処刑]"):
            break

    return None


def _extract_numeric_trait(personality_tag: str, category: str) -> int | None:
    """人格タグ文字列から指定カテゴリの数値を抽出する。

    Args:
        personality_tag: 人格タグ文字列（例: "personality: tone=polite, reactivity=7"）
        category: 抽出するカテゴリ名

    Returns:
        整数値。該当なしまたはパース失敗の場合は None。
    """
    for part in personality_tag.split(","):
        part = part.strip()
        if part.startswith(f"{category}="):
            try:
                return int(part.removeprefix(f"{category}="))
            except ValueError:
                return None
    return None


def _build_situation_emotion_hint(game: GameState, player: Player, personality_tag: str) -> str:
    """状況と感情パラメータに基づいた発言ヒントを生成する（議論プロンプト専用）。

    Args:
        game: ゲーム状態
        player: 視点プレイヤー
        personality_tag: 人格タグ文字列（reactivity/volatility の数値を含む）

    Returns:
        状況ヒント文字列。特筆すべき状況がなければ空文字列。
    """
    situation = _detect_situation(game, player)
    if not situation:
        return ""

    reactivity = _extract_numeric_trait(personality_tag, "reactivity")
    volatility = _extract_numeric_trait(personality_tag, "volatility")

    lines = [f"## 現在の状況\n{situation}"]
    if reactivity is not None and volatility is not None:
        lines.append(
            f"あなたの感情パラメータ（reactivity={reactivity}, volatility={volatility}）に基づき、"
            "この状況への感情的反応を発言に自然に反映させてください。"
        )
    return "\n".join(lines)


def _build_private_info(
    game: GameState, player: Player, *, personality_tag: str = "", include_advice: bool = True
) -> str:
    """プレイヤーの秘密情報を生成する。

    GM 要約には含まれないプレイヤー固有の秘密情報を返す。
    GM 要約に役職別アドバイスがある場合、該当役職のアドバイスも含める。

    Args:
        game: ゲーム状態
        player: 対象プレイヤー
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）
        include_advice: True の場合、GM 要約から役職別アドバイスを抽出して含める。
            投票・夜行動など簡潔なコンテキストが望ましい場面では False を指定する。

    Returns:
        秘密情報文字列。情報がない場合は空文字列。
    """
    lines: list[str] = []

    if player.role == Role.SEER and game.divined_history:
        seer_results = []
        for seer, target in game.divined_history:
            if seer == player.name:
                t = game.find_player(target)
                label = "人狼" if t and t.role == Role.WEREWOLF else "人狼ではない"
                seer_results.append(f"- {target}: {label}")
        if seer_results:
            lines.append("## あなたの占い結果")
            lines.extend(seer_results)

    if player.role == Role.MEDIUM and game.medium_results:
        medium_lines = [
            f"- Day {day} 処刑 {name}: {'人狼' if is_werewolf else '人狼ではない'}"
            for day, name, is_werewolf in game.medium_results
        ]
        if medium_lines:
            lines.append("## あなたの霊媒結果")
            lines.extend(medium_lines)

    if player.role == Role.WEREWOLF:
        allies = [p.name for p in game.alive_werewolves if p.name != player.name]
        if allies:
            lines.append(f"## 仲間の人狼\n{', '.join(allies)}")

    if player.role == Role.KNIGHT and game.guard_history:
        guard_targets = [target for knight, target in game.guard_history if knight == player.name]
        if guard_targets:
            lines.append(f"## あなたの護衛履歴\n{', '.join(guard_targets)}")

    if include_advice and game.gm_summary:
        advice = _extract_role_advice(game.gm_summary, player.role, personality_tag=personality_tag)
        if advice:
            lines.append(advice)

    return "\n".join(lines)


_MAX_RECENT_STATEMENTS = DEFAULT_MAX_RECENT_STATEMENTS

# vote/night action 用に除外するフィールド
_ACTION_EXCLUDE_FIELDS: frozenset[str] = frozenset({"role_advice", "vote_history", "claims", "contradictions"})


def _strip_gm_fields(
    gm_summary: str,
    *,
    exclude_fields: frozenset[str] = frozenset({"role_advice"}),
    compress_vote_history: bool = False,
) -> str:
    """GM要約JSONから不要フィールドを除外する。

    Args:
        gm_summary: GM 要約の JSON 文字列
        exclude_fields: 除外するフィールド名のセット
        compress_vote_history: True の場合、直近1日分のみ投票詳細を保持し、
            それ以前は処刑結果のみに圧縮する

    Returns:
        フィルタ済みの JSON 文字列。パース失敗時は元の文字列をそのまま返す。
    """
    try:
        data = json.loads(gm_summary)
    except (json.JSONDecodeError, TypeError):
        return gm_summary

    for field in exclude_fields:
        data.pop(field, None)

    if compress_vote_history and "vote_history" in data:
        vote_history = data["vote_history"]
        if isinstance(vote_history, list) and len(vote_history) > 1:
            compressed: list[dict[str, object]] = []
            for day_votes in vote_history[:-1]:
                if isinstance(day_votes, dict):
                    summary: dict[str, object] = {"day": day_votes.get("day")}
                    if "executed" in day_votes:
                        summary["executed"] = day_votes["executed"]
                    compressed.append(summary)
                else:
                    compressed.append(day_votes)
            compressed.append(vote_history[-1])
            data["vote_history"] = compressed

    return json.dumps(data, ensure_ascii=False)


def _extract_execution_budget(gm_summary: str) -> str:
    """GM 要約 JSON から処刑予算（吊り余裕）情報を抽出して整形する。

    Args:
        gm_summary: GM 要約の JSON 文字列

    Returns:
        整形された処刑予算文字列。情報がない場合は空文字列。
    """
    try:
        data = json.loads(gm_summary)
    except (json.JSONDecodeError, TypeError):
        return ""

    budget = data.get("execution_budget")
    if not budget:
        return ""

    alive = budget.get("alive_count", 0)
    m2 = budget.get("margin_if_two_wolves")
    m1 = budget.get("margin_if_one_wolf")
    if m2 is None or m1 is None:
        return ""

    lines = [
        "## 処刑予算（吊り余裕）",
        f"生存者{alive}人。人狼が2人残りなら吊り余裕{m2}回、1人残りなら吊り余裕{m1}回。",
        "※ 狂人が生存していれば投票で不利になり、実質的な余裕はさらに厳しくなります。",
    ]
    return "\n".join(lines)


def _build_context(
    game: GameState, player: Player, *, max_recent_statements: int = _MAX_RECENT_STATEMENTS, personality_tag: str = ""
) -> str:
    """ゲームコンテキスト（状況 + ログ）を生成する。

    GM 要約がある場合はそれを活用し、新しいログのみを追加する。
    GM 要約がない場合は従来通りフルログを返す（発言ログは直近 N 件に制限）。
    """
    alive_names = "、".join(p.name for p in game.alive_players)

    parts = [
        f"現在: {game.day}日目の{'昼' if game.phase.value == 'day' else '夜'}フェーズ",
        f"生存者: {alive_names}",
    ]

    if game.gm_summary:
        filtered_summary = _strip_gm_fields(
            game.gm_summary, exclude_fields=frozenset({"role_advice"}), compress_vote_history=True
        )
        parts.append(f"\n## 盤面情報\n{filtered_summary}")

        budget_info = _extract_execution_budget(game.gm_summary)
        if budget_info:
            parts.append(f"\n{budget_info}")

        private_info = _build_private_info(game, player, personality_tag=personality_tag)
        if private_info:
            parts.append(f"\n{private_info}")

        new_entries = game.log[game.gm_summary_log_offset :]
        if new_entries:
            new_log = filter_log_entries(new_entries, player, max_recent_statements=max_recent_statements)
            if new_log:
                parts.append(f"\n## 本日の出来事\n{new_log}")
    else:
        game_log = format_log_for_context(game, player.name, max_recent_statements=max_recent_statements)
        if game_log:
            parts.append(f"\n## これまでのログ\n{game_log}")

    return "\n".join(parts)


def _build_action_context(game: GameState, player: Player, *, personality_tag: str = "") -> str:
    """投票・夜行動用の軽量コンテキストを生成する。

    議論プロンプト用の ``_build_context`` と同じ構造だが、候補者選択に不要な
    フィールド（role_advice, vote_history, claims, contradictions）を GM 要約から
    除外し、role_advice テキストの注入もスキップすることでトークン数を削減する。
    """
    alive_names = "、".join(p.name for p in game.alive_players)

    parts = [
        f"現在: {game.day}日目の{'昼' if game.phase.value == 'day' else '夜'}フェーズ",
        f"生存者: {alive_names}",
    ]

    if game.gm_summary:
        filtered_summary = _strip_gm_fields(game.gm_summary, exclude_fields=_ACTION_EXCLUDE_FIELDS)
        parts.append(f"\n## 盤面情報\n{filtered_summary}")

        budget_info = _extract_execution_budget(game.gm_summary)
        if budget_info:
            parts.append(f"\n{budget_info}")

        private_info = _build_private_info(game, player, personality_tag=personality_tag, include_advice=False)
        if private_info:
            parts.append(f"\n{private_info}")

        new_entries = game.log[game.gm_summary_log_offset :]
        if new_entries:
            new_log = filter_log_entries(new_entries, player, max_recent_statements=_MAX_RECENT_STATEMENTS)
            if new_log:
                parts.append(f"\n## 本日の出来事\n{new_log}")
    else:
        game_log = format_log_for_context(game, player.name, max_recent_statements=_MAX_RECENT_STATEMENTS)
        if game_log:
            parts.append(f"\n## これまでのログ\n{game_log}")

    return "\n".join(parts)


def _build_speaking_status(speaking_order: tuple[str, ...], current_speaker_index: int) -> str:
    """発言状況（発言済み/未発言プレイヤー）を整形する。

    Args:
        speaking_order: 発言順のプレイヤー名タプル
        current_speaker_index: 現在の発言者のインデックス

    Returns:
        発言状況の説明文字列。情報がない場合は空文字列。
    """
    if not speaking_order or current_speaker_index < 0:
        return ""

    spoken = [name for name in speaking_order[:current_speaker_index]]
    unspoken = [name for name in speaking_order[current_speaker_index + 1 :]]

    lines = ["## 発言状況（このラウンド）"]
    lines.append(f"発言順: {'→'.join(speaking_order)}")
    if spoken:
        lines.append(f"発言済み: {'、'.join(spoken)}")
    if unspoken:
        lines.append(f"未発言: {'、'.join(unspoken)}")
    lines.append(
        "※ まだ発言していないプレイヤーの発言内容や態度には言及しないでください。"
        "言及できるのは既に発言したプレイヤーの発言のみです。"
    )

    return "\n".join(lines)


def build_discuss_prompt(
    game: GameState,
    player: Player,
    *,
    max_recent_statements: int = _MAX_RECENT_STATEMENTS,
    personality_tag: str = "",
    speaking_order: tuple[str, ...] = (),
    current_speaker_index: int = -1,
) -> str:
    """議論フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        player: 発言するプレイヤー
        max_recent_statements: 保持する直近の発言ログ件数。負の値で全件保持。
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）
        speaking_order: 発言順のプレイヤー名タプル
        current_speaker_index: 現在の発言者のインデックス（speaking_order 内の位置）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_context(game, player, max_recent_statements=max_recent_statements, personality_tag=personality_tag)
    situation_hint = _build_situation_emotion_hint(game, player, personality_tag)
    situation_section = f"\n\n{situation_hint}" if situation_hint else ""
    speaking_status = _build_speaking_status(speaking_order, current_speaker_index)
    speaking_section = f"\n\n{speaking_status}" if speaking_status else ""
    return f"""{context}{situation_section}

あなたは{player.name}です。以下の出力形式に従って回答してください。

## 出力形式
【思考】（ここにあなたの内部思考を書く。戦略・推理・疑い等を2〜3文以内で。他のプレイヤーには見えません）
【発言】（ここに議論での発言内容を書く。1〜3文で簡潔に）

## 発言のルール
- 発言の冒頭に自分の名前を付けないでください（「{player.name}: 」のような接頭辞は不要です）
- 他のプレイヤーの発言に名前を挙げて反応し（「○○さんに賛成/反対」等）、繰り返しでなく新しい視点を加えましょう
- 必ず自分の立場を明確にしてください。「○○が怪しい」「○○に投票したい」など具体的な主張をしましょう
- 盤面の整理（誰が生きている、何が起きた等）は皆が知っているので不要です
- 占い結果や霊媒結果などの重要な情報を持っている場合は、必ず議論で公表してください
- 他のプレイヤーが公表した占い結果や霊媒結果があれば、それに基づいて推理を展開してください{speaking_section}"""


def build_discuss_continuation_prompt(
    game: GameState,
    player: Player,
    log_offset: int,
    *,
    max_recent_statements: int = _MAX_RECENT_STATEMENTS,
    speaking_order: tuple[str, ...] = (),
    current_speaker_index: int = -1,
) -> str:
    """ラウンド2以降の議論プロンプトを生成する。

    会話履歴にラウンド1のフルコンテキストが含まれているため、
    ここでは ``log_offset`` 以降の新しいログエントリのみを差分として渡す。
    静的コンテキスト（日/フェーズ、生存者、GM要約、秘密情報）は含めない。

    Args:
        game: ゲーム状態
        player: 発言するプレイヤー
        log_offset: 前回のプロンプト生成時のログ長（``len(game.log)``）
        max_recent_statements: 保持する直近の発言ログ件数。負の値で全件保持。
        speaking_order: 発言順のプレイヤー名タプル
        current_speaker_index: 現在の発言者のインデックス（speaking_order 内の位置）

    Returns:
        差分コンテキスト + 議論指示のプロンプト文字列
    """
    new_entries = game.log[log_offset:]
    parts: list[str] = []

    if new_entries:
        new_log = filter_log_entries(new_entries, player, max_recent_statements=max_recent_statements)
        if new_log:
            parts.append(f"## 前ラウンドの発言\n{new_log}")

    speaking_status = _build_speaking_status(speaking_order, current_speaker_index)
    if speaking_status:
        parts.append(speaking_status)

    parts.append("""議論の次のラウンドです。前ラウンドの議論を踏まえて発言してください。
前ラウンドの発言ルールに従い、名前の接頭辞なし・具体的な主張・新しい視点を心がけてください。

## 出力形式
【思考】（内部思考を2〜3文以内で）
【発言】（発言内容を1〜3文で）""")

    return "\n\n".join(parts)


def build_vote_prompt(
    game: GameState, player: Player, candidates: tuple[Player, ...], *, personality_tag: str = ""
) -> str:
    """投票フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        player: 投票するプレイヤー
        candidates: 投票候補者（自分を除く生存者）
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_action_context(game, player, personality_tag=personality_tag)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{player.name}です。以下の候補者から処刑したいプレイヤーを1人選んでください。

## 投票のルール
- 議論で出た発言内容をよく振り返り、最も怪しいと思うプレイヤーに投票してください
- 占い結果や霊媒結果が共有されている場合は、それを最優先の判断材料にしてください
- まず「なぜその人が怪しいのか」の理由を考え、それから投票先を決めてください
- 発言順が最後だった、発言が少なかった等の理由だけで投票しないでください
- 議論で「怪しい人はいない」と感じた場合でも、最も疑わしいプレイヤーを選んで投票してください

## 候補者
{candidate_list}

候補者リストから正確に1人選び、名前と理由を返してください。"""


def build_divine_prompt(
    game: GameState, seer: Player, candidates: tuple[Player, ...], *, personality_tag: str = ""
) -> str:
    """占いフェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        seer: 占い師プレイヤー
        candidates: 占い候補者（自分と占い済みを除く生存者）
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_action_context(game, seer, personality_tag=personality_tag)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{seer.name}（占い師）です。以下の候補者から占いたいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

## 占い対象の選び方
- 議論で最も怪しい発言をしたプレイヤーを優先しましょう
- 情報が少なく判断できないプレイヤーも有力な占い候補です

候補者リストから正確に1人選び、名前と理由を返してください。"""


def build_attack_prompt(
    game: GameState, werewolf: Player, candidates: tuple[Player, ...], *, personality_tag: str = ""
) -> str:
    """襲撃フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        werewolf: 人狼プレイヤー
        candidates: 襲撃候補者（自分を除く生存者）
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_action_context(game, werewolf, personality_tag=personality_tag)
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
- 「今夜は誰も襲撃されなかった」という結果は、襲撃対象が狩人に護衛されていた証拠です
- 同じ相手を狙い続けると再び護衛される可能性が高いため、対象を変えることを検討してください
- GMからのアドバイスも参考にしつつ、以下の観点を総合的に判断しましょう
  - 情報源を断つ（占い師・霊媒師）
  - 護衛されにくい相手を狙う（発言力のある村人、狩人候補）
  - 数の優位を作る

候補者リストから正確に1人選び、名前と理由を返してください。"""


def build_guard_prompt(
    game: GameState, knight: Player, candidates: tuple[Player, ...], *, personality_tag: str = ""
) -> str:
    """護衛フェーズ用のユーザープロンプトを生成する。

    Args:
        game: ゲーム状態
        knight: 狩人プレイヤー
        candidates: 護衛候補者（自分と前回護衛対象を除く生存者）
        personality_tag: 人格タグ文字列（stance に応じた戦略指向の注入用）

    Returns:
        ユーザープロンプト文字列
    """
    context = _build_action_context(game, knight, personality_tag=personality_tag)
    candidate_list = _format_candidates(candidates)
    return f"""{context}

あなたは{knight.name}（狩人）です。以下の候補者から護衛したいプレイヤーを1人選んでください。

## 候補者
{candidate_list}

候補者リストから正確に1人選び、名前と理由を返してください。"""
