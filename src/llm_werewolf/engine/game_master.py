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
from llm_werewolf.engine.llm_config import LLMConfig

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


class GameBoardState(BaseModel):
    """統合された盤面情報（確定情報 + 分析情報）。"""

    alive: list[str]
    dead: list[DeadPlayerInfo]
    vote_history: list[DayVotes]
    claims: list[RoleClaim]
    contradictions: list[str]
    player_summaries: list[PlayerSummary]
    role_advice: list[RoleAdvice] = Field(default_factory=list)


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
- 各行動には merit（メリット）と demerit（デメリット）を1文ずつ付記
- 公開情報のみに基づいて提案すること（真の役職は不明なので、各役職が取りうる最善の行動を想定する）
- 具体的なプレイヤー名を挙げて、盤面に即した具体的な提案をすること
- 例: role="占い師", options=[{action="まだ占っていない Dave を占う",
  merit="情報が少ないプレイヤーの白黒が判明する",
  demerit="既に怪しい Grace を放置するリスクがある"}, ...]

## 注意事項
- 公開情報のみに基づいて分析してください
- claims/contradictions/player_summaries では推測や憶測は含めず、ログに記録された事実のみを抽出してください
- player_summaries は生存者全員を含めてください
- role_advice は6役職すべてを含めてください"""


def _build_gm_user_prompt(game: GameState) -> str:
    """GM-AI 用のユーザープロンプトを生成する。"""
    public_log = format_public_log(game)
    alive_names = "、".join(p.name for p in game.alive_players)
    return f"## 生存者\n{alive_names}\n\n## ゲームログ\n{public_log}"


# --- GameMasterProvider ---


class GameMasterProvider:
    """GM-AI プロバイダー。ゲーム状態を要約し、JSON 文字列を返す。"""

    def __init__(self, config: LLMConfig) -> None:
        self._llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key),
        )
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

        analysis = self._call_llm_analysis(game)

        board = GameBoardState(
            alive=alive,
            dead=dead,
            vote_history=vote_history,
            claims=analysis.claims if analysis else [],
            contradictions=analysis.contradictions[:3] if analysis else [],
            player_summaries=analysis.player_summaries if analysis else [],
            role_advice=analysis.role_advice if analysis else [],
        )

        return board.model_dump_json(ensure_ascii=False)

    def _call_llm_analysis(self, game: GameState) -> GameAnalysis | None:
        """LLM を呼び出して GameAnalysis を構造化出力で取得する。

        API エラー時は指数バックオフで最大 MAX_RETRIES 回リトライする。
        リトライ上限到達時は None を返す。
        """
        structured_llm = self._llm.with_structured_output(GameAnalysis, include_raw=True)
        user_prompt = _build_gm_user_prompt(game)
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
