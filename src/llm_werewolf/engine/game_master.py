"""GM-AI（盤面整理AI）モジュール。

Day 2 以降、ゲームログを構造化 JSON に整理し、各プレイヤー AI の情報抽出負荷を削減する。
確定情報（生存/死亡/投票）はプログラムで生成し、分析情報（CO抽出/矛盾/要約）は LLM で抽出する
ハイブリッドアプローチを採用する。
"""

from __future__ import annotations

import logging
import re
import time
import warnings
from typing import Literal

import openai
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import format_public_log
from llm_werewolf.engine.llm_config import DEFAULT_MAX_RECENT_STATEMENTS, LLMConfig

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

# --- Pydantic モデル（LLM 構造化出力用） ---


class ClaimResult(BaseModel):
    """CO に付随する占い/霊媒結果の主張。"""

    target: str = Field(description="対象プレイヤー名")
    result: Literal["white", "black"] = Field(description="結果（white=人狼でない, black=人狼）")
    day: int = Field(description="何日目の結果か")


class RoleClaim(BaseModel):
    """役職 CO 情報。"""

    player: str = Field(description="CO したプレイヤー名")
    claimed_role: str = Field(description="主張した役職（占い師, 霊媒師 等）")
    day: int = Field(description="CO した日")
    results: list[ClaimResult] = Field(default_factory=list, description="CO に付随する占い/霊媒結果の一覧")


class PlayerSummary(BaseModel):
    """各プレイヤーの立場要約。"""

    name: str = Field(description="プレイヤー名")
    summary: str = Field(description="そのプレイヤーの立場・主張の要約（1文）")


class AdviceOption(BaseModel):
    """おすすめ行動の1選択肢。"""

    action: str = Field(description="おすすめ行動（1文）")
    merit: str = Field(description="メリット（1文）")
    demerit: str = Field(description="デメリット（1文）")
    risk: int = Field(description="リスクスコア（1=低リスク〜10=高リスク）", ge=1, le=10)
    reward: int = Field(description="リターンスコア（1=低リターン〜10=高リターン）", ge=1, le=10)


class RoleAdvice(BaseModel):
    """1役職分のおすすめ行動。"""

    role: str = Field(description="役職名（村人、占い師、霊媒師、狩人、狂人、人狼）")
    options: list[AdviceOption] = Field(description="おすすめ行動の選択肢（2〜3件）")


class GameAnalysis(BaseModel):
    """LLM が抽出する分析情報。"""

    claims: list[RoleClaim] = Field(default_factory=list, description="役職 CO 情報の一覧")
    contradictions: list[str] = Field(default_factory=list, description="検出された矛盾点（最大3件）")
    player_summaries: list[PlayerSummary] = Field(default_factory=list, description="各プレイヤーの立場要約")
    role_advice: list[RoleAdvice] = Field(default_factory=list, description="役職別おすすめ行動")


# --- 確定情報モデル（プログラム生成） ---


class DeadPlayerInfo(BaseModel):
    """死亡プレイヤー情報。"""

    name: str
    cause: Literal["execution", "attack"]
    day: int


class DayVotes(BaseModel):
    """1日分の投票結果。"""

    day: int
    votes: dict[str, str] = Field(description="投票者名 → 投票先名")
    executed: str = Field(description="処刑されたプレイヤー名")


class ExecutionBudget(BaseModel):
    """処刑予算（吊り余裕）情報。"""

    alive_count: int = Field(description="生存者数")
    total_executions: int = Field(description="これまでの処刑回数")
    margin_if_two_wolves: int = Field(description="人狼2人残の場合の吊り余裕")
    margin_if_one_wolf: int = Field(description="人狼1人残の場合の吊り余裕")


class GameBoardState(BaseModel):
    """統合された盤面情報（確定情報 + 分析情報）。"""

    alive: list[str]
    dead: list[DeadPlayerInfo]
    vote_history: list[DayVotes]
    claims: list[RoleClaim]
    contradictions: list[str]
    player_summaries: list[PlayerSummary]
    role_advice: list[RoleAdvice] = Field(default_factory=list)
    execution_budget: ExecutionBudget | None = None


# --- 確定情報の抽出 ---

# ログエントリのパースパターン
_EXECUTION_PATTERN = re.compile(r"^\[処刑\] (.+?) が処刑された")
_ATTACK_PATTERN = re.compile(r"^\[襲撃\] (.+?) が人狼に襲撃された")
_VOTE_PATTERN = re.compile(r"^\[投票\] (.+?) → (.+)")
_DAY_HEADER_PATTERN = re.compile(r"^--- Day (\d+)")


def extract_board_info(game: GameState) -> tuple[list[str], list[DeadPlayerInfo], list[DayVotes]]:
    """GameState のログから確定的な盤面情報を抽出する。

    Args:
        game: ゲーム状態

    Returns:
        (alive, dead, vote_history) のタプル
    """
    alive = [p.name for p in game.alive_players]
    dead: list[DeadPlayerInfo] = []
    vote_history: list[DayVotes] = []

    current_day = 0
    current_votes: dict[str, str] = {}

    for entry in game.log:
        day_match = _DAY_HEADER_PATTERN.match(entry)
        if day_match:
            current_day = int(day_match.group(1))
            current_votes = {}
            continue

        vote_match = _VOTE_PATTERN.match(entry)
        if vote_match:
            voter, target = vote_match.group(1), vote_match.group(2)
            current_votes[voter] = target
            continue

        exec_match = _EXECUTION_PATTERN.match(entry)
        if exec_match:
            executed_name = exec_match.group(1)
            dead.append(DeadPlayerInfo(name=executed_name, cause="execution", day=current_day))
            if current_votes:
                vote_history.append(DayVotes(day=current_day, votes=current_votes, executed=executed_name))
            continue

        attack_match = _ATTACK_PATTERN.match(entry)
        if attack_match:
            attacked_name = attack_match.group(1)
            dead.append(DeadPlayerInfo(name=attacked_name, cause="attack", day=current_day))

    return alive, dead, vote_history


def calculate_execution_budget(alive_count: int, dead: list[DeadPlayerInfo]) -> ExecutionBudget:
    """処刑予算（吊り余裕）を計算する。

    吊り余裕の公式（毎日「処刑+襲撃」で2人ずつ減ることを考慮）:
    - 残り処刑回数 = (生存者数 - 人狼数×2 + 1) // 2
    - 吊り余裕 = 残り処刑回数 - 人狼数

    公開情報から人狼の正確な残数は不明なため、2パターンで計算する。

    Args:
        alive_count: 生存者数
        dead: 死亡プレイヤー情報のリスト

    Returns:
        ExecutionBudget
    """
    total_executions = sum(1 for d in dead if d.cause == "execution")

    def _margin(wolf_count: int) -> int:
        remaining = (alive_count - wolf_count * 2 + 1) // 2
        return remaining - wolf_count

    return ExecutionBudget(
        alive_count=alive_count,
        total_executions=total_executions,
        margin_if_two_wolves=_margin(2),
        margin_if_one_wolf=_margin(1),
    )


# --- GM プロンプト ---

_GM_SYSTEM_PROMPT = """\
あなたはゲームマスター（GM）AIです。人狼ゲームの公開ログを分析し、構造化された情報を抽出してください。

## 抽出すべき情報

### 1. claims（役職CO情報）
- 議論中に「占い師です」「霊媒師です」等の役職COを行ったプレイヤーを抽出
- CO に付随する占い結果・霊媒結果も抽出（例: 「○○を占った結果、白でした」）
- 結果は white（人狼でない）/ black（人狼）で記録

### 2. contradictions（矛盾点）
- 複数の占い師COがあり結果が矛盾する場合
- 発言内容と投票行動が矛盾する場合
- その他の論理的矛盾
- **最大3件**に絞り、重要度の高いものを優先

### 3. player_summaries（各プレイヤーの立場要約）
- 生存者全員について、現時点での立場・主張を1文で要約
- 例: 「占い師COし、○○を黒と主張している」「○○への投票を主張し積極的に追及している」

### 4. role_advice（役職別おすすめ行動）
- 6役職（村人、占い師、霊媒師、狩人、狂人、人狼）すべてについて、現在の盤面状況に応じたおすすめ行動を2〜3件提案
- 各行動には merit・demerit を1文ずつ、risk（1-10）・reward（1-10）を付記
- 公開情報のみに基づいて提案すること（真の役職は不明なので、各役職が取りうる最善の行動を想定する）
- 具体的なプレイヤー名を挙げて、盤面に即した具体的な提案をすること
- risk/reward スコアの基準: 1=極めて低い、5=中程度、10=極めて高い

#### 各役職の戦略観点（アドバイス生成時に考慮すること）

**村人:**
- 吊り余裕の計算: 残り処刑可能回数と人狼残数を比較し、余裕がある/ないで戦略が変わる
- 占いローラーのリスク: 偽物が狂人の場合（人狼0人排除+真占い喪失）は最悪、人狼の場合は許容範囲
- グレー吊り: 占い対抗に狂人がいる可能性を考慮し、グレーから吊る方が効率的な場合もある
- 情報の優先度: 占い結果 > 霊媒結果 > 議論での印象
- 偽役職CO（身代わり戦略）: 真の役職者を人狼の襲撃から守る戦略もある

**占い師:**
- 占い先の優先度: 未確認のグレーを優先、情報が少ない相手を占う
- 対抗占い師が出た場合: 対抗の占い先と被らないようにして情報量を最大化
- 潜伏（COしない）: 襲撃を回避できるが、村の推理が進まないリスクがある

**霊媒師:**
- COタイミング: 処刑結果が出た翌朝にCOして結果を報告するのが基本
- 占い対抗がある場合: 霊媒結果で占い師の真偽検証ができることを意識する

**狩人:**
- 占い対抗時のリスク計算: 占い2人対抗では1/2で偽物を護衛してしまう。霊媒師1人のみCOなら確実に村側を護衛できる
- 護衛優先度: 霊媒師（1人のみCO）> 信頼度の高い占い師 > 有力な推理をしている村人
- 護衛成功（GJ）後: 同じ相手を護衛し続けるか、別の相手に変えるかの判断
- COしない原則: 基本はCOしない（襲撃対象になるリスク）。例外は自分が処刑されそうな時

**狂人:**
- 偽占い師CO: 村人に黒判定を出して混乱させる（人狼に黒を出すのは利敵行為）
- 3人占いCOリスク: 人狼も占いCOした場合はローラーリスク。撤回や霊媒COに切り替える選択肢
- 終盤の立ち回り: あえて怪しい発言で投票を人狼から自分に向ける身代わり戦略
- 人狼特定時の勝負手: 人狼と票を合わせて多数派を作る

**人狼:**
- 議論戦略: 潜伏（村人として振る舞う）か、占いCO（偽占い師として名乗り出る）か
  - 占いCO判断基準: 狂人が既にCOしているか、3人COローラーリスクはあるか
- 襲撃先: 占い師狙い、霊媒師狙い、占い済み白確定者狙い、グレー狙い
  - 注意: 偽占い（味方の狂人）が黒判定を出した相手を噛むと偽占いであることがバレる
- 投票: 仲間の人狼をかばいすぎない（不自然な庇い立ては疑われる）

#### risk/reward スコアの例
- 霊媒師を護衛（1人のみCO）→ risk: 2, reward: 7
- 占い師を護衛（2人対抗あり）→ risk: 5, reward: 8
- 占いローラー（偽物が狂人の可能性高）→ risk: 8, reward: 3
- 人狼が占いCO（狂人が既にCO済み）→ risk: 9, reward: 6

## 注意事項
- 公開情報のみに基づいて分析してください
- claims/contradictions/player_summaries では推測や憶測は含めず、ログに記録された事実のみを抽出してください
- player_summaries は生存者全員を含めてください
- role_advice は6役職すべてを含めてください"""


def _build_gm_user_prompt(game: GameState, budget: ExecutionBudget, *, max_recent_statements: int = -1) -> str:
    """GM-AI 用のユーザープロンプトを生成する。"""
    public_log = format_public_log(game, max_recent_statements=max_recent_statements)
    alive_names = "、".join(p.name for p in game.alive_players)
    budget_section = (
        f"\n\n## 処刑予算（吊り余裕）\n"
        f"- 生存者数: {budget.alive_count}人\n"
        f"- これまでの処刑: {budget.total_executions}回\n"
        f"- 人狼2人残の場合: 吊り余裕{budget.margin_if_two_wolves}回\n"
        f"- 人狼1人残の場合: 吊り余裕{budget.margin_if_one_wolf}回\n"
        f"※ 狂人が生存している場合、投票で人狼陣営が多数派を形成しやすく実質的な余裕はさらに厳しい\n"
        f"※ role_advice で各役職に吊り余裕を考慮したアドバイスを出してください"
    )
    return f"## 生存者\n{alive_names}\n\n## ゲームログ\n{public_log}{budget_section}"


# --- GameMasterProvider ---


class GameMasterProvider:
    """GM-AI プロバイダー。ゲーム状態を要約し、JSON 文字列を返す。"""

    def __init__(self, config: LLMConfig, max_recent_statements: int = DEFAULT_MAX_RECENT_STATEMENTS) -> None:
        self._llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key),
        )
        self._max_recent_statements = max_recent_statements
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0
        self.last_cache_read_input_tokens: int = 0

    def _sleep(self, seconds: float) -> None:
        """スリープ処理。テスト時にモック可能。"""
        time.sleep(seconds)

    def summarize(self, game: GameState) -> str:
        """ゲーム状態を要約し、JSON 文字列を返す。

        1. extract_board_info() で確定情報を生成
        2. LLM に公開ログを渡し GameAnalysis を構造化出力で取得
        3. 両者を統合して GameBoardState → JSON 文字列

        Args:
            game: ゲーム状態

        Returns:
            GameBoardState の JSON 文字列
        """
        alive, dead, vote_history = extract_board_info(game)
        budget = calculate_execution_budget(len(alive), dead)

        analysis = self._call_llm_analysis(game, budget, max_recent_statements=self._max_recent_statements)

        board = GameBoardState(
            alive=alive,
            dead=dead,
            vote_history=vote_history,
            claims=analysis.claims if analysis else [],
            contradictions=analysis.contradictions[:3] if analysis else [],
            player_summaries=analysis.player_summaries if analysis else [],
            role_advice=analysis.role_advice if analysis else [],
            execution_budget=budget,
        )

        return board.model_dump_json(ensure_ascii=False)

    def _call_llm_analysis(
        self, game: GameState, budget: ExecutionBudget, *, max_recent_statements: int = -1
    ) -> GameAnalysis | None:
        """LLM を呼び出して GameAnalysis を構造化出力で取得する。

        API エラー時は指数バックオフで最大 MAX_RETRIES 回リトライする。
        リトライ上限到達時は None を返す。
        """
        structured_llm = self._llm.with_structured_output(GameAnalysis, include_raw=True)
        user_prompt = _build_gm_user_prompt(game, budget, max_recent_statements=max_recent_statements)
        messages = [
            SystemMessage(content=_GM_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        logger.debug("GM-AI プロンプト:\n  system: %s\n  user: %s", _GM_SYSTEM_PROMPT, user_prompt)

        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
                    response = structured_llm.invoke(messages)
                elapsed = time.monotonic() - start

                parsed = response.get("parsed") if isinstance(response, dict) else response
                if not isinstance(parsed, GameAnalysis):
                    logger.warning("GM-AI 構造化出力のパースに失敗しました。分析情報なしで続行します。")
                    self._reset_token_usage()
                    return None

                self._extract_token_usage(response, elapsed)
                logger.info("GM-AI 分析完了: elapsed=%.2fs", elapsed)
                return parsed

            except (openai.APITimeoutError, openai.RateLimitError) as e:
                wait = 2**attempt
                logger.warning(
                    "GM-AI API エラー (試行 %d/%d): %s。%d秒後にリトライします。",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                    wait,
                )
                self._sleep(wait)
            except openai.APIStatusError as e:
                if e.status_code >= 500:
                    wait = 2**attempt
                    logger.warning(
                        "GM-AI API サーバーエラー %d (試行 %d/%d): %s。%d秒後にリトライします。",
                        e.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        wait,
                    )
                    self._sleep(wait)
                else:
                    logger.warning("GM-AI API クライアントエラー %d: %s。分析情報なしで続行します。", e.status_code, e)
                    self._reset_token_usage()
                    return None
            except Exception as e:
                logger.warning(
                    "GM-AI 構造化出力の処理中に予期しない例外が発生しました: %s。分析情報なしで続行します。", e
                )
                self._reset_token_usage()
                return None

        logger.warning("GM-AI API リトライ上限 (%d回) に到達しました。分析情報なしで続行します。", MAX_RETRIES)
        self._reset_token_usage()
        return None

    def _extract_token_usage(self, response: dict | GameAnalysis, elapsed: float) -> None:  # type: ignore[type-arg]
        """レスポンスからトークン使用量を抽出して保存する。"""
        input_tokens = 0
        output_tokens = 0
        cache_read = 0
        if isinstance(response, dict):
            raw = response.get("raw")
            usage = getattr(raw, "usage_metadata", None) if raw else None
            if usage:
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                details = usage.get("input_token_details", {})
                if details:
                    cache_read = details.get("cache_read", 0)
                logger.debug(
                    "GM-AI トークン使用量: input=%d, output=%d, total=%d, cache_read=%d",
                    input_tokens,
                    output_tokens,
                    input_tokens + output_tokens,
                    cache_read,
                )
        self.last_input_tokens = input_tokens
        self.last_output_tokens = output_tokens
        self.last_cache_read_input_tokens = cache_read

    def _reset_token_usage(self) -> None:
        """トークン使用量をリセットする。"""
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_cache_read_input_tokens = 0
