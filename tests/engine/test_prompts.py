"""プロンプトテンプレートのテスト。"""

import random
from dataclasses import replace as dc_replace

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.prompts import (
    _SITUATION_ENDGAME,
    _SITUATION_FIRST_DAY,
    _SITUATION_GUARD_SUCCESS,
    _SITUATION_SUSPECTED,
    NUMERIC_TRAIT_CATEGORIES,
    REACTIVITY_LEVELS,
    TRAIT_CATEGORIES,
    VOLATILITY_LEVELS,
    _build_context,
    _build_private_info,
    _build_situation_emotion_hint,
    _build_speaking_status,
    _detect_situation,
    _extract_numeric_trait,
    _extract_role_advice,
    assign_personalities,
    build_attack_prompt,
    build_discuss_continuation_prompt,
    build_discuss_prompt,
    build_divine_prompt,
    build_guard_prompt,
    build_personality,
    build_system_prompt,
    build_vote_prompt,
)


def _create_game() -> GameState:
    """テスト用のゲーム状態を作成する（9人村）。"""
    players = (
        Player(name="Alice", role=Role.SEER),
        Player(name="Bob", role=Role.VILLAGER),
        Player(name="Charlie", role=Role.WEREWOLF),
        Player(name="Dave", role=Role.VILLAGER),
        Player(name="Eve", role=Role.KNIGHT),
        Player(name="Frank", role=Role.MEDIUM),
        Player(name="Grace", role=Role.MADMAN),
        Player(name="Heidi", role=Role.WEREWOLF),
        Player(name="Ivan", role=Role.VILLAGER),
    )
    game = GameState(players=players, phase=Phase.DAY, day=1)
    game = game.add_log("[配役] Alice は占い師です")
    game = game.add_log("[配役] Bob は村人です")
    game = game.add_log("[配役] Charlie は人狼です")
    game = game.add_log("[配役] Dave は村人です")
    game = game.add_log("[配役] Eve は狩人です")
    game = game.add_log("[配役] Frank は霊媒師です")
    game = game.add_log("[配役] Grace は狂人です")
    game = game.add_log("[配役] Heidi は人狼です")
    game = game.add_log("[配役] Ivan は村人です")
    game = game.add_log("[人狼仲間] Charlie の仲間の人狼は Heidi です")
    game = game.add_log("[人狼仲間] Heidi の仲間の人狼は Charlie です")
    return game


class TestBuildSystemPrompt:
    """build_system_prompt のテスト。"""

    def test_villager_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.VILLAGER)
        assert "村人" in result
        assert "特殊能力はありません" in result

    def test_seer_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.SEER)
        assert "占い師" in result
        assert "占い結果は議論で積極的に公表" in result

    def test_werewolf_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.WEREWOLF)
        assert "人狼" in result
        assert "村人のふりをして" in result

    def test_all_roles_contain_base_rules(self) -> None:
        for role in Role:
            result = build_system_prompt(role)
            assert "人狼ゲーム" in result
            assert "日本語" in result
            assert "投票は公開" in result

    def test_base_rules_describe_nine_player_game(self) -> None:
        """ベースルールが9人村仕様であること。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "9人" in result
        assert "人狼2" in result
        assert "狩人1" in result
        assert "霊媒師1" in result
        assert "狂人1" in result

    def test_knight_prompt_contains_constraints(self) -> None:
        """狩人のプロンプトに護衛制約が含まれること。"""
        result = build_system_prompt(Role.KNIGHT)
        assert "自分自身は護衛できません" in result

    def test_medium_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.MEDIUM)
        assert "霊媒師" in result
        assert "翌朝" in result

    def test_madman_prompt_contains_role(self) -> None:
        result = build_system_prompt(Role.MADMAN)
        assert "狂人" in result
        assert "人狼陣営" in result

    def test_werewolf_prompt_mentions_two_wolves(self) -> None:
        """人狼のプロンプトに2人いる旨が含まれること。"""
        result = build_system_prompt(Role.WEREWOLF)
        assert "人狼は2人" in result

    def test_all_roles_contain_glossary_terms(self) -> None:
        for role in Role:
            result = build_system_prompt(role)
            assert "黒" in result
            assert "白" in result
            assert "処刑" in result
            assert "襲撃" in result
            assert "占い" in result

    def test_villager_does_not_contain_other_role_strategies(self) -> None:
        """村人のプロンプトに他役職の固有戦略が含まれないこと。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "偽の占い師を名乗" not in result
        assert "毎晩1人を護衛" not in result
        assert "毎晩1人を襲撃" not in result

    def test_seer_does_not_contain_guard_or_attack_details(self) -> None:
        """占い師のプロンプトに護衛・襲撃の詳細が含まれないこと。"""
        result = build_system_prompt(Role.SEER)
        assert "毎晩1人を護衛" not in result
        assert "毎晩1人を襲撃" not in result

    def test_knight_does_not_contain_divine_or_attack_details(self) -> None:
        """狩人のプロンプトに占い・襲撃の詳細が含まれないこと。"""
        result = build_system_prompt(Role.KNIGHT)
        assert "毎晩1人を占い" not in result
        assert "毎晩1人を襲撃" not in result

    def test_werewolf_knows_other_role_abilities(self) -> None:
        """人狼は対策のために他役職の能力を知っていること。"""
        result = build_system_prompt(Role.WEREWOLF)
        assert "占い師" in result
        assert "霊媒師" in result
        assert "狩人" in result

    def test_base_rules_do_not_contain_night_action_details(self) -> None:
        """ベースルールに夜行動の詳細が含まれないこと。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "人狼が1人を襲撃 / 占い師が1人を占う / 狩人が1人を護衛" not in result
        assert "霊媒師は処刑されたプレイヤーが人狼だったかどうかを翌朝知る" not in result


class TestBuildDiscussPrompt:
    """build_discuss_prompt のテスト。"""

    def test_contains_player_name(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "Bob" in result

    def test_contains_game_context(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "1日目" in result
        assert "昼" in result
        assert "生存者" in result

    def test_contains_discussion_instruction(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "発言内容を返してください" in result

    def test_contains_game_log(self) -> None:
        game = _create_game()
        game = game.add_log("[議論] Bob: おはようございます")
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "おはようございます" in result

    def test_seer_sees_own_role_log(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice (seer)
        result = build_discuss_prompt(game, player)
        assert "Alice は占い師です" in result

    def test_villager_does_not_see_other_role_log(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob (villager)
        result = build_discuss_prompt(game, player)
        assert "Alice は占い師です" not in result
        assert "Bob は村人です" in result


class TestBuildVotePrompt:
    """build_vote_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice
        candidates = (game.players[1], game.players[2], game.players[3])
        result = build_vote_prompt(game, player, candidates)
        assert "- Bob" in result
        assert "- Charlie" in result
        assert "- Dave" in result

    def test_contains_vote_instruction(self) -> None:
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "候補者リストから正確に1人選び、名前と理由を返してください" in result

    def test_contains_player_name(self) -> None:
        game = _create_game()
        player = game.players[0]  # Alice
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "Alice" in result

    def test_contains_discussion_based_instruction(self) -> None:
        """議論内容を踏まえて投票する指示が含まれること。"""
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "議論で出た発言内容をよく振り返り" in result

    def test_contains_divine_result_priority(self) -> None:
        """占い結果を最優先にする指示が含まれること。"""
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "最優先の判断材料" in result

    def test_contains_anti_bias_instruction(self) -> None:
        """発言順バイアスを避ける指示が含まれること。"""
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "発言順が最後だった" in result

    def test_contains_reasoning_first_instruction(self) -> None:
        """理由を先に考える指示が含まれること。"""
        game = _create_game()
        player = game.players[0]
        candidates = (game.players[1],)
        result = build_vote_prompt(game, player, candidates)
        assert "理由を考え" in result


class TestBuildDivinePrompt:
    """build_divine_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        seer = game.players[0]  # Alice (seer)
        candidates = (game.players[1], game.players[2])
        result = build_divine_prompt(game, seer, candidates)
        assert "- Bob" in result
        assert "- Charlie" in result

    def test_contains_divine_instruction(self) -> None:
        game = _create_game()
        seer = game.players[0]
        candidates = (game.players[1],)
        result = build_divine_prompt(game, seer, candidates)
        assert "候補者リストから正確に1人選び、名前と理由を返してください" in result

    def test_contains_seer_role_label(self) -> None:
        game = _create_game()
        seer = game.players[0]
        candidates = (game.players[1],)
        result = build_divine_prompt(game, seer, candidates)
        assert "占い師" in result


class TestBuildAttackPrompt:
    """build_attack_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        werewolf = game.players[2]  # Charlie (werewolf)
        candidates = (game.players[0], game.players[1])
        result = build_attack_prompt(game, werewolf, candidates)
        assert "- Alice" in result
        assert "- Bob" in result

    def test_contains_attack_instruction(self) -> None:
        game = _create_game()
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "候補者リストから正確に1人選び、名前と理由を返してください" in result

    def test_contains_werewolf_role_label(self) -> None:
        game = _create_game()
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "人狼" in result

    def test_night_phase_context(self) -> None:
        game = _create_game()
        from dataclasses import replace

        game = replace(game, phase=Phase.NIGHT)
        werewolf = game.players[2]
        candidates = (game.players[0],)
        result = build_attack_prompt(game, werewolf, candidates)
        assert "夜" in result

    def test_contains_ally_werewolf_info(self) -> None:
        """人狼の仲間情報がプロンプトに含まれること。"""
        game = _create_game()
        werewolf = game.players[2]  # Charlie (werewolf)
        candidates = (game.players[0], game.players[1])
        result = build_attack_prompt(game, werewolf, candidates)
        assert "## 仲間の人狼" in result
        assert "Heidi" in result

    def test_no_ally_section_when_alone(self) -> None:
        """人狼が1人の場合は仲間セクションが含まれないこと。"""
        from dataclasses import replace as dc_replace

        game = _create_game()
        # Heidi を死亡させる
        heidi = game.players[7]
        dead_heidi = dc_replace(heidi, status=heidi.status.__class__("dead"))
        game = game.replace_player(heidi, dead_heidi)
        werewolf = game.players[2]  # Charlie (werewolf)
        candidates = (game.players[0], game.players[1])
        result = build_attack_prompt(game, werewolf, candidates)
        assert "## 仲間の人狼" not in result


class TestBuildGuardPrompt:
    """build_guard_prompt のテスト。"""

    def test_contains_candidates(self) -> None:
        game = _create_game()
        knight = game.players[4]  # Eve (knight)
        candidates = (game.players[0], game.players[1])
        result = build_guard_prompt(game, knight, candidates)
        assert "- Alice" in result
        assert "- Bob" in result

    def test_contains_guard_instruction(self) -> None:
        game = _create_game()
        knight = game.players[4]  # Eve (knight)
        candidates = (game.players[0],)
        result = build_guard_prompt(game, knight, candidates)
        assert "候補者リストから正確に1人選び、名前と理由を返してください" in result

    def test_contains_knight_role_label(self) -> None:
        game = _create_game()
        knight = game.players[4]  # Eve (knight)
        candidates = (game.players[0],)
        result = build_guard_prompt(game, knight, candidates)
        assert "狩人" in result

    def test_contains_player_name(self) -> None:
        game = _create_game()
        knight = game.players[4]  # Eve (knight)
        candidates = (game.players[0],)
        result = build_guard_prompt(game, knight, candidates)
        assert "Eve" in result


class TestPersonalitySystem:
    """人格特性システムのテスト。"""

    def test_trait_categories_have_enough_options(self) -> None:
        """各特性軸に4つ以上の選択肢があること。"""
        for category in TRAIT_CATEGORIES:
            assert len(category) >= 4

    def test_trait_has_tag_field(self) -> None:
        """各特性に tag フィールドが存在すること。"""
        for category_traits in TRAIT_CATEGORIES:
            for trait in category_traits:
                assert trait.tag, f"特性 {trait.description} に tag が未設定"
                assert trait.category in ("tone", "stance", "style")

    def test_assign_personalities_returns_correct_count(self) -> None:
        """assign_personalities が指定人数分の人格を返すこと。"""
        rng = random.Random(42)
        result = assign_personalities(4, rng)
        assert len(result) == 4

    def test_assign_personalities_returns_correct_count_for_large_group(self) -> None:
        """9人村（AI 8人）でも正しく動作すること。"""
        rng = random.Random(42)
        result = assign_personalities(8, rng)
        assert len(result) == 8

    def test_assign_personalities_each_has_all_categories(self) -> None:
        """各AIに全カテゴリから1つずつ特性が割り当てられること（数値感情軸を含む）。"""
        rng = random.Random(42)
        result = assign_personalities(4, rng)
        for traits in result:
            assert len(traits) == len(TRAIT_CATEGORIES) + len(NUMERIC_TRAIT_CATEGORIES)
            categories = {t.category for t in traits}
            expected_categories = {cat[0].category for cat in TRAIT_CATEGORIES} | {
                cat[0].category for cat in NUMERIC_TRAIT_CATEGORIES
            }
            assert categories == expected_categories

    def test_assign_personalities_deterministic_with_seed(self) -> None:
        """同じシードで同じ結果が返ること。"""
        result1 = assign_personalities(4, random.Random(42))
        result2 = assign_personalities(4, random.Random(42))
        assert result1 == result2

    def test_build_personality_returns_tag_format(self) -> None:
        """build_personality がタグ形式の文字列を返すこと。"""
        rng = random.Random(42)
        traits = assign_personalities(1, rng)[0]
        result = build_personality(traits)
        assert result.startswith("personality: ")
        for trait in traits:
            assert f"{trait.category}={trait.tag}" in result

    def test_build_personality_tag_format_structure(self) -> None:
        """build_personality がカンマ区切りのタグ形式であること。"""
        from llm_werewolf.engine.prompts import DISCUSSION_ATTITUDES, SPEAKING_STYLES, THINKING_STYLES

        traits = (SPEAKING_STYLES[0], DISCUSSION_ATTITUDES[1], THINKING_STYLES[2])
        result = build_personality(traits)
        assert result == "personality: tone=polite, stance=evidence-based, style=silence-focus"

    def test_build_system_prompt_contains_personality_tag_rules(self) -> None:
        """システムプロンプトに人格タグ解釈ルールが含まれること。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "人格タグ" in result
        assert "tone" in result
        assert "stance" in result
        assert "style" in result

    def test_build_system_prompt_is_fixed_for_same_role(self) -> None:
        """同じ役職のシステムプロンプトが常に同一であること（Prompt Caching 対応）。"""
        result1 = build_system_prompt(Role.VILLAGER)
        result2 = build_system_prompt(Role.VILLAGER)
        assert result1 == result2

    def test_build_system_prompt_does_not_contain_personality_section(self) -> None:
        """システムプロンプトに「あなたの性格」セクションが含まれないこと。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "あなたの性格" not in result


class TestBuildDiscussPromptRules:
    """build_discuss_prompt の発言ルールに関するテスト。"""

    def test_contains_no_name_prefix_instruction(self) -> None:
        """発言の冒頭に名前を付けない指示が含まれること。"""
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "名前を付けない" in result

    def test_contains_clear_stance_instruction(self) -> None:
        """自分の立場を明確にする指示が含まれること。"""
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "自分の立場を明確に" in result


class TestBuildSystemPromptGameSummarySchema:
    """システムプロンプトに盤面情報スキーマが含まれることのテスト。"""

    def test_contains_game_summary_schema(self) -> None:
        result = build_system_prompt(Role.VILLAGER)
        assert "盤面情報の読み方" in result

    def test_all_roles_contain_game_summary_schema(self) -> None:
        for role in Role:
            result = build_system_prompt(role)
            assert "盤面情報の読み方" in result


class TestBuildContextWithGmSummary:
    """_build_context の GM 要約ありテスト。"""

    def test_uses_gm_summary_when_available(self) -> None:
        game = _create_game()
        gm_json = (
            '{"alive":["Alice"],"dead":[],"vote_history":[],'
            '"claims":[],"contradictions":[],"player_summaries":[],"role_advice":[]}'
        )
        game = dc_replace(game, gm_summary=gm_json, gm_summary_log_offset=len(game.log))
        player = game.players[1]  # Bob
        result = _build_context(game, player)
        assert "盤面情報" in result
        assert gm_json in result

    def test_falls_back_to_full_log_without_gm_summary(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = _build_context(game, player)
        assert "これまでのログ" in result
        assert "盤面情報" not in result

    def test_includes_execution_budget_when_present(self) -> None:
        game = _create_game()
        gm_json = (
            '{"alive":["Alice","Bob"],"dead":[],"vote_history":[],'
            '"claims":[],"contradictions":[],"player_summaries":[],"role_advice":[],'
            '"execution_budget":{"alive_count":7,"total_executions":1,'
            '"margin_if_two_wolves":0,"margin_if_one_wolf":2}}'
        )
        game = dc_replace(game, gm_summary=gm_json, gm_summary_log_offset=len(game.log))
        player = game.players[1]  # Bob
        result = _build_context(game, player)
        assert "処刑予算" in result
        assert "吊り余裕0回" in result
        assert "吊り余裕2回" in result
        assert "狂人" in result

    def test_no_execution_budget_without_field(self) -> None:
        game = _create_game()
        gm_json = (
            '{"alive":["Alice"],"dead":[],"vote_history":[],'
            '"claims":[],"contradictions":[],"player_summaries":[],"role_advice":[]}'
        )
        game = dc_replace(game, gm_summary=gm_json, gm_summary_log_offset=len(game.log))
        player = game.players[1]
        result = _build_context(game, player)
        assert "処刑予算" not in result

    def test_includes_new_entries_after_offset(self) -> None:
        game = _create_game()
        gm_json = (
            '{"alive":[],"dead":[],"vote_history":[],'
            '"claims":[],"contradictions":[],"player_summaries":[],"role_advice":[]}'
        )
        game = dc_replace(game, gm_summary=gm_json, gm_summary_log_offset=len(game.log))
        # offset 以降にログを追加
        game = game.add_log("[発言] Bob: こんにちは")
        player = game.players[1]  # Bob
        result = _build_context(game, player)
        assert "本日の出来事" in result
        assert "こんにちは" in result


class TestBuildPrivateInfo:
    """_build_private_info のテスト。"""

    def test_seer_sees_divine_results(self) -> None:
        game = _create_game()
        game = game.add_divine_history("Alice", "Bob")
        player = game.players[0]  # Alice (seer)
        result = _build_private_info(game, player)
        assert "占い結果" in result
        assert "Bob" in result

    def test_medium_sees_medium_results(self) -> None:
        game = _create_game()
        game = game.add_medium_result(1, "Charlie", True)
        player = game.players[5]  # Frank (medium)
        result = _build_private_info(game, player)
        assert "霊媒結果" in result
        assert "Charlie" in result

    def test_werewolf_sees_allies(self) -> None:
        game = _create_game()
        player = game.players[2]  # Charlie (werewolf)
        result = _build_private_info(game, player)
        assert "仲間の人狼" in result
        assert "Heidi" in result

    def test_knight_sees_guard_history(self) -> None:
        game = _create_game()
        game = game.add_guard_history("Eve", "Alice")
        player = game.players[4]  # Eve (knight)
        result = _build_private_info(game, player)
        assert "護衛履歴" in result
        assert "Alice" in result

    def test_villager_has_no_private_info(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob (villager)
        result = _build_private_info(game, player)
        assert result == ""

    def test_includes_gm_advice_for_matching_role(self) -> None:
        """GM 要約に role_advice がある場合、該当役職のアドバイスが含まれること。"""
        import json

        game = _create_game()
        gm_data = {
            "alive": ["Alice"],
            "dead": [],
            "vote_history": [],
            "claims": [],
            "contradictions": [],
            "player_summaries": [],
            "role_advice": [
                {
                    "role": "占い師",
                    "options": [
                        {
                            "action": "Dave を占う",
                            "merit": "情報が少ないプレイヤーの白黒が判明する",
                            "demerit": "Grace を放置するリスクがある",
                            "risk": 3,
                            "reward": 7,
                        },
                        {
                            "action": "Grace を占う",
                            "merit": "怪しいプレイヤーを確認できる",
                            "demerit": "他の候補を見逃す可能性がある",
                            "risk": 4,
                            "reward": 8,
                        },
                    ],
                },
            ],
        }
        game = dc_replace(game, gm_summary=json.dumps(gm_data, ensure_ascii=False))
        player = game.players[0]  # Alice (seer)
        result = _build_private_info(game, player)
        assert "GMからのアドバイス" in result
        assert "Dave を占う" in result
        assert "Grace を占う" in result
        assert "メリット" in result
        assert "デメリット" in result

    def test_does_not_include_gm_advice_for_different_role(self) -> None:
        """他の役職のアドバイスは含まれないこと。"""
        import json

        game = _create_game()
        gm_data = {
            "alive": ["Alice"],
            "dead": [],
            "vote_history": [],
            "claims": [],
            "contradictions": [],
            "player_summaries": [],
            "role_advice": [
                {
                    "role": "占い師",
                    "options": [
                        {"action": "Dave を占う", "merit": "メリット", "demerit": "デメリット"},
                    ],
                },
            ],
        }
        game = dc_replace(game, gm_summary=json.dumps(gm_data, ensure_ascii=False))
        player = game.players[1]  # Bob (villager)
        result = _build_private_info(game, player)
        assert "GMからのアドバイス" not in result
        assert "Dave を占う" not in result


class TestExtractRoleAdvice:
    """_extract_role_advice のテスト。"""

    def test_extracts_matching_role(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [
                        {
                            "action": "投票で怪しい人を処刑する",
                            "merit": "人狼を排除できる",
                            "demerit": "間違えるリスク",
                            "risk": 4,
                            "reward": 7,
                        },
                    ],
                },
                {
                    "role": "人狼",
                    "options": [
                        {
                            "action": "占い師を襲撃する",
                            "merit": "情報源を断てる",
                            "demerit": "護衛されるリスク",
                            "risk": 5,
                            "reward": 9,
                        },
                    ],
                },
            ],
        }
        result = _extract_role_advice(json.dumps(gm_data, ensure_ascii=False), Role.VILLAGER)
        assert "投票で怪しい人を処刑する" in result
        assert "占い師を襲撃する" not in result

    def test_returns_empty_for_no_match(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [{"action": "行動", "merit": "利点", "demerit": "欠点", "risk": 3, "reward": 5}],
                },
            ],
        }
        result = _extract_role_advice(json.dumps(gm_data, ensure_ascii=False), Role.SEER)
        assert result == ""

    def test_returns_empty_for_invalid_json(self) -> None:
        result = _extract_role_advice("invalid json", Role.VILLAGER)
        assert result == ""

    def test_returns_empty_for_no_role_advice(self) -> None:
        import json

        gm_data = {"alive": ["Alice"], "dead": []}
        result = _extract_role_advice(json.dumps(gm_data), Role.VILLAGER)
        assert result == ""

    def test_formats_multiple_options_with_risk_reward(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "狩人",
                    "options": [
                        {
                            "action": "Alice を護衛する",
                            "merit": "占い師COしている",
                            "demerit": "ブラフの可能性",
                            "risk": 5,
                            "reward": 8,
                        },
                        {
                            "action": "Frank を護衛する",
                            "merit": "霊媒師COしている",
                            "demerit": "狙われにくい",
                            "risk": 2,
                            "reward": 7,
                        },
                        {
                            "action": "Dave を護衛する",
                            "merit": "重要な発言をしている",
                            "demerit": "根拠が弱い",
                            "risk": 6,
                            "reward": 4,
                        },
                    ],
                },
            ],
        }
        result = _extract_role_advice(json.dumps(gm_data, ensure_ascii=False), Role.KNIGHT)
        assert "選択肢1" in result
        assert "選択肢2" in result
        assert "選択肢3" in result
        assert "Alice を護衛する" in result
        assert "Frank を護衛する" in result
        assert "Dave を護衛する" in result
        assert "リスク:5/10" in result
        assert "リターン:8/10" in result
        assert "リスク:2/10" in result
        assert "リターン:7/10" in result

    def test_includes_stance_guidance_for_aggressive(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [
                        {"action": "行動A", "merit": "利点", "demerit": "欠点", "risk": 3, "reward": 5},
                    ],
                },
            ],
        }
        result = _extract_role_advice(
            json.dumps(gm_data, ensure_ascii=False),
            Role.VILLAGER,
            personality_tag="personality: tone=polite, stance=aggressive, style=strategic",
        )
        assert "攻撃的な性格" in result
        assert "リスクが高くてもリターンが大きい" in result

    def test_includes_stance_guidance_for_evidence_based(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [
                        {"action": "行動A", "merit": "利点", "demerit": "欠点", "risk": 3, "reward": 5},
                    ],
                },
            ],
        }
        result = _extract_role_advice(
            json.dumps(gm_data, ensure_ascii=False),
            Role.VILLAGER,
            personality_tag="personality: tone=casual, stance=evidence-based, style=strategic",
        )
        assert "証拠重視" in result
        assert "リスクが低く確実な戦略" in result

    def test_no_stance_guidance_without_personality_tag(self) -> None:
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [
                        {"action": "行動A", "merit": "利点", "demerit": "欠点", "risk": 3, "reward": 5},
                    ],
                },
            ],
        }
        result = _extract_role_advice(json.dumps(gm_data, ensure_ascii=False), Role.VILLAGER)
        assert "攻撃的な性格" not in result
        assert "証拠重視" not in result
        assert "独自の判断" not in result
        assert "直感を重視" not in result

    def test_formats_without_risk_reward(self) -> None:
        """risk/reward がない場合でもスコアラベルなしで正常に動作する。"""
        import json

        gm_data = {
            "role_advice": [
                {
                    "role": "村人",
                    "options": [
                        {"action": "行動A", "merit": "利点", "demerit": "欠点"},
                    ],
                },
            ],
        }
        result = _extract_role_advice(json.dumps(gm_data, ensure_ascii=False), Role.VILLAGER)
        assert "行動A" in result
        assert "リスク:" not in result


class TestBuildDiscussContinuationPrompt:
    """build_discuss_continuation_prompt のテスト。"""

    def test_includes_new_entries_only(self) -> None:
        """log_offset 以降の新しいエントリのみが含まれること。"""
        game = _create_game()
        game = game.add_log("[発言] Alice: ラウンド1の発言です")
        offset = len(game.log)
        game = game.add_log("[発言] Bob: ラウンド1の後半の発言です")
        game = game.add_log("[発言] Charlie: 怪しい人がいます")

        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "ラウンド1の後半の発言です" in result
        assert "怪しい人がいます" in result
        assert "ラウンド1の発言です" not in result

    def test_does_not_include_static_context(self) -> None:
        """静的コンテキスト（日/フェーズ、生存者、GM要約）が含まれないこと。"""
        game = _create_game()
        gm_json = (
            '{"alive":["Alice"],"dead":[],"vote_history":[],'
            '"claims":[],"contradictions":[],"player_summaries":[],"role_advice":[]}'
        )
        game = dc_replace(game, gm_summary=gm_json, gm_summary_log_offset=len(game.log))
        game = game.add_log("[発言] Alice: テスト発言")
        offset = len(game.log)
        game = game.add_log("[発言] Bob: 新しい発言")

        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "1日目" not in result
        assert "生存者" not in result
        assert "盤面情報" not in result
        assert gm_json not in result

    def test_contains_discussion_instruction(self) -> None:
        """議論の指示が含まれること。"""
        game = _create_game()
        offset = len(game.log)
        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "次のラウンド" in result
        assert "発言ルール" in result

    def test_filters_private_entries(self) -> None:
        """プライベートログはプレイヤー視点でフィルタリングされること。"""
        game = _create_game()
        offset = len(game.log)
        game = game.add_log("[占い結果] Alice が Bob を占った結果: 人狼ではない")
        game = game.add_log("[発言] Alice: 公開発言です")

        # Bob（村人）には占い結果は見えない
        player = game.players[1]  # Bob (villager)
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "Alice が Bob を占った結果" not in result
        assert "公開発言です" in result

    def test_contains_concise_rule_reminder(self) -> None:
        """簡潔なルールリマインダーが含まれること。"""
        game = _create_game()
        offset = len(game.log)
        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "名前の接頭辞なし" in result

    def test_no_new_entries_still_has_instruction(self) -> None:
        """新しいエントリがなくても指示は含まれること。"""
        game = _create_game()
        offset = len(game.log)
        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "次のラウンド" in result

    def test_limits_statements_with_max_recent_statements(self) -> None:
        """max_recent_statements で発言ログが制限されること。"""
        game = _create_game()
        offset = len(game.log)
        for i in range(10):
            game = game.add_log(f"[発言] Alice: 発言{i}")

        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset, max_recent_statements=3)
        for i in range(7):
            assert f"発言{i}" not in result
        for i in range(7, 10):
            assert f"発言{i}" in result

    def test_events_kept_with_max_recent_statements(self) -> None:
        """max_recent_statements を指定してもイベントログは保持されること。"""
        game = _create_game()
        offset = len(game.log)
        game = game.add_log("[投票] Alice → Bob")
        for i in range(5):
            game = game.add_log(f"[発言] Alice: 発言{i}")

        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset, max_recent_statements=2)
        assert "[投票] Alice → Bob" in result
        assert "発言3" in result
        assert "発言4" in result
        assert "発言0" not in result


class TestBuildSpeakingStatus:
    """_build_speaking_status のテスト。"""

    def test_returns_empty_when_no_speaking_order(self) -> None:
        result = _build_speaking_status((), 0)
        assert result == ""

    def test_returns_empty_when_negative_index(self) -> None:
        result = _build_speaking_status(("Alice", "Bob"), -1)
        assert result == ""

    def test_first_speaker_has_no_spoken(self) -> None:
        order = ("Alice", "Bob", "Charlie")
        result = _build_speaking_status(order, 0)
        assert "発言済み:" not in result
        assert "未発言" in result
        assert "Bob" in result
        assert "Charlie" in result

    def test_middle_speaker_has_spoken_and_unspoken(self) -> None:
        order = ("Alice", "Bob", "Charlie", "Dave")
        result = _build_speaking_status(order, 2)
        assert "発言済み" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "未発言" in result
        assert "Dave" in result

    def test_last_speaker_has_no_unspoken(self) -> None:
        order = ("Alice", "Bob", "Charlie")
        result = _build_speaking_status(order, 2)
        assert "発言済み" in result
        assert "未発言" not in result

    def test_contains_speaking_order_display(self) -> None:
        order = ("Alice", "Bob", "Charlie")
        result = _build_speaking_status(order, 1)
        assert "発言順: Alice→Bob→Charlie" in result

    def test_contains_unspoken_constraint(self) -> None:
        order = ("Alice", "Bob", "Charlie")
        result = _build_speaking_status(order, 0)
        assert "まだ発言していないプレイヤーの発言内容や態度には言及しないでください" in result


class TestBuildDiscussPromptWithSpeakingOrder:
    """build_discuss_prompt の発言順情報テスト。"""

    def test_includes_speaking_status_when_provided(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        order = ("Alice", "Bob", "Charlie", "Dave")
        result = build_discuss_prompt(game, player, speaking_order=order, current_speaker_index=1)
        assert "発言状況" in result
        assert "発言済み" in result
        assert "Alice" in result
        assert "未発言" in result

    def test_no_speaking_status_without_order(self) -> None:
        game = _create_game()
        player = game.players[1]  # Bob
        result = build_discuss_prompt(game, player)
        assert "発言状況" not in result


class TestBuildDiscussContinuationPromptWithSpeakingOrder:
    """build_discuss_continuation_prompt の発言順情報テスト。"""

    def test_includes_speaking_status_when_provided(self) -> None:
        game = _create_game()
        offset = len(game.log)
        player = game.players[1]  # Bob
        order = ("Alice", "Bob", "Charlie")
        result = build_discuss_continuation_prompt(game, player, offset, speaking_order=order, current_speaker_index=1)
        assert "発言状況" in result
        assert "まだ発言していないプレイヤー" in result

    def test_no_speaking_status_without_order(self) -> None:
        game = _create_game()
        offset = len(game.log)
        player = game.players[1]  # Bob
        result = build_discuss_continuation_prompt(game, player, offset)
        assert "発言状況" not in result


class TestNumericEmotionalTraits:
    """数値感情特性（reactivity/volatility）のテスト。"""

    def test_reactivity_levels_has_nine_options(self) -> None:
        """REACTIVITY_LEVELS が1〜9の9オプションを持つこと。"""
        assert len(REACTIVITY_LEVELS) == 9
        tags = [t.tag for t in REACTIVITY_LEVELS]
        assert tags == [str(i) for i in range(1, 10)]

    def test_volatility_levels_has_nine_options(self) -> None:
        """VOLATILITY_LEVELS が1〜9の9オプションを持つこと。"""
        assert len(VOLATILITY_LEVELS) == 9
        tags = [t.tag for t in VOLATILITY_LEVELS]
        assert tags == [str(i) for i in range(1, 10)]

    def test_numeric_trait_categories_has_two_categories(self) -> None:
        """NUMERIC_TRAIT_CATEGORIES に reactivity と volatility の2カテゴリがあること。"""
        assert len(NUMERIC_TRAIT_CATEGORIES) == 2
        categories = {cat[0].category for cat in NUMERIC_TRAIT_CATEGORIES}
        assert categories == {"reactivity", "volatility"}

    def test_assign_personalities_includes_numeric_traits(self) -> None:
        """assign_personalities が reactivity と volatility を含む特性を返すこと。"""
        rng = random.Random(42)
        result = assign_personalities(4, rng)
        for traits in result:
            categories = {t.category for t in traits}
            assert "reactivity" in categories
            assert "volatility" in categories

    def test_build_personality_includes_numeric_traits(self) -> None:
        """build_personality が reactivity と volatility を含む出力を返すこと。"""
        rng = random.Random(42)
        traits = assign_personalities(1, rng)[0]
        result = build_personality(traits)
        assert "reactivity=" in result
        assert "volatility=" in result

    def test_system_prompt_contains_numeric_trait_rules(self) -> None:
        """システムプロンプトに reactivity と volatility の解釈ルールが含まれること。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "reactivity" in result
        assert "volatility" in result


class TestAssignPersonalitiesWithShuffle:
    """シャッフル方式の多様性テスト。"""

    def test_nine_players_have_unique_reactivity(self) -> None:
        """9人に割り当てると reactivity の値が全員異なること。"""
        rng = random.Random(42)
        result = assign_personalities(9, rng)
        reactivity_values = []
        for traits in result:
            for t in traits:
                if t.category == "reactivity":
                    reactivity_values.append(int(t.tag))
        assert len(set(reactivity_values)) == 9

    def test_nine_players_have_unique_volatility(self) -> None:
        """9人に割り当てると volatility の値が全員異なること。"""
        rng = random.Random(42)
        result = assign_personalities(9, rng)
        volatility_values = []
        for traits in result:
            for t in traits:
                if t.category == "volatility":
                    volatility_values.append(int(t.tag))
        assert len(set(volatility_values)) == 9

    def test_deterministic_with_seed(self) -> None:
        """同じシードで同じシャッフル結果が返ること。"""
        result1 = assign_personalities(9, random.Random(99))
        result2 = assign_personalities(9, random.Random(99))
        assert result1 == result2


class TestDetectSituation:
    """_detect_situation 関数のテスト。"""

    def test_first_day_returns_first_day_situation(self) -> None:
        """1日目に _SITUATION_FIRST_DAY を返すこと。"""
        game = _create_game()
        assert game.day == 1
        player = game.players[0]
        assert _detect_situation(game, player) == _SITUATION_FIRST_DAY

    def test_endgame_with_four_or_fewer_alive(self) -> None:
        """生存者4人以下で _SITUATION_ENDGAME を返すこと。"""
        game = _create_game()
        # Day 2 にする
        game = dc_replace(game, day=2)
        # 5人死亡（残り4人）
        dead_players = tuple(p.killed() if i < 5 else p for i, p in enumerate(game.players))
        game = dc_replace(game, players=dead_players)
        player = game.alive_players[0]
        assert _detect_situation(game, player) == _SITUATION_ENDGAME

    def test_suspected_with_two_votes_against(self) -> None:
        """直近ログに自分への投票が2票以上で _SITUATION_SUSPECTED を返すこと。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        # 生存者を十分に残す（5人以上）
        player = game.players[1]  # Bob
        game = game.add_log(f"[投票] Alice → {player.name}")
        game = game.add_log(f"[投票] Charlie → {player.name}")
        assert _detect_situation(game, player) == _SITUATION_SUSPECTED

    def test_guard_success_detected(self) -> None:
        """護衛成功ログがあれば _SITUATION_GUARD_SUCCESS を返すこと。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        game = game.add_log("[襲撃] 今夜は誰も襲撃されなかった")
        player = game.players[1]  # Bob
        assert _detect_situation(game, player) == _SITUATION_GUARD_SUCCESS

    def test_guard_success_not_detected_after_discussion(self) -> None:
        """護衛成功ログより後に発言ログがある場合は検出されないこと。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        game = game.add_log("[襲撃] 今夜は誰も襲撃されなかった")
        game = game.add_log("[発言] Alice: テスト発言")
        player = game.players[1]  # Bob
        # 発言ログで中断するため護衛成功は検出されない
        assert _detect_situation(game, player) is None

    def test_normal_situation_returns_none(self) -> None:
        """特筆すべき状況がなければ None を返すこと。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        player = game.players[0]
        assert _detect_situation(game, player) is None

    def test_first_day_takes_priority_over_endgame(self) -> None:
        """1日目は終盤より優先されること。"""
        game = _create_game()
        assert game.day == 1
        dead_players = tuple(p.killed() if i < 5 else p for i, p in enumerate(game.players))
        game = dc_replace(game, players=dead_players)
        player = game.alive_players[0]
        assert _detect_situation(game, player) == _SITUATION_FIRST_DAY


class TestExtractNumericTrait:
    """_extract_numeric_trait 関数のテスト。"""

    def test_extracts_reactivity(self) -> None:
        """personality タグから reactivity の数値を抽出できること。"""
        tag = "personality: tone=polite, stance=aggressive, style=strategic, reactivity=7, volatility=3"
        assert _extract_numeric_trait(tag, "reactivity") == 7

    def test_extracts_volatility(self) -> None:
        """personality タグから volatility の数値を抽出できること。"""
        tag = "personality: tone=polite, reactivity=5, volatility=9"
        assert _extract_numeric_trait(tag, "volatility") == 9

    def test_returns_none_for_missing_category(self) -> None:
        """存在しないカテゴリには None を返すこと。"""
        tag = "personality: tone=polite, stance=aggressive"
        assert _extract_numeric_trait(tag, "reactivity") is None

    def test_returns_none_for_empty_tag(self) -> None:
        """空文字列には None を返すこと。"""
        assert _extract_numeric_trait("", "reactivity") is None


class TestBuildSituationEmotionHint:
    """_build_situation_emotion_hint 関数のテスト。"""

    def test_normal_situation_returns_empty(self) -> None:
        """通常状況では空文字列を返すこと。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        player = game.players[0]
        result = _build_situation_emotion_hint(game, player, "")
        assert result == ""

    def test_first_day_with_personality_includes_hint(self) -> None:
        """初日 + personality_tag あり → 状況と感情ヒントが含まれること。"""
        game = _create_game()
        player = game.players[0]
        tag = "personality: tone=polite, stance=aggressive, style=strategic, reactivity=8, volatility=6"
        result = _build_situation_emotion_hint(game, player, tag)
        assert "## 現在の状況" in result
        assert _SITUATION_FIRST_DAY in result
        assert "reactivity=8" in result
        assert "volatility=6" in result

    def test_without_personality_tag_returns_situation_only(self) -> None:
        """personality_tag なし → 状況説明のみで感情パラメータ部分がないこと。"""
        game = _create_game()
        player = game.players[0]
        result = _build_situation_emotion_hint(game, player, "")
        # day==1 なので状況は返るが感情パラメータヒントはない
        assert "## 現在の状況" in result
        assert "reactivity" not in result

    def test_endgame_situation_included(self) -> None:
        """終盤状況が検出されてヒントに含まれること。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        dead_players = tuple(p.killed() if i < 5 else p for i, p in enumerate(game.players))
        game = dc_replace(game, players=dead_players)
        player = game.alive_players[0]
        tag = "personality: reactivity=3, volatility=2"
        result = _build_situation_emotion_hint(game, player, tag)
        assert _SITUATION_ENDGAME in result


class TestBuildDiscussPromptWithSituation:
    """build_discuss_prompt の状況ヒント注入テスト。"""

    def test_first_day_prompt_contains_situation(self) -> None:
        """初日のプロンプトに '## 現在の状況' が含まれること。"""
        game = _create_game()
        player = game.players[0]
        result = build_discuss_prompt(game, player)
        assert "## 現在の状況" in result
        assert _SITUATION_FIRST_DAY in result

    def test_normal_day_prompt_without_situation_has_no_section(self) -> None:
        """通常の2日目プロンプトには状況セクションが含まれないこと（状況が検出されない場合）。"""
        game = _create_game()
        game = dc_replace(game, day=2)
        player = game.players[0]
        # 通常状況（投票なし・護衛成功なし）
        result = build_discuss_prompt(game, player)
        assert "## 現在の状況" not in result
