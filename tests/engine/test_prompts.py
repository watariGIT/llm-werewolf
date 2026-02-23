"""プロンプトテンプレートのテスト。"""

import random

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.value_objects import Phase, Role
from llm_werewolf.engine.prompts import (
    TRAIT_CATEGORIES,
    assign_personalities,
    build_attack_prompt,
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
        assert "占い結果を活用" in result

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
        """各AIに全カテゴリから1つずつ特性が割り当てられること。"""
        rng = random.Random(42)
        result = assign_personalities(4, rng)
        for traits in result:
            assert len(traits) == len(TRAIT_CATEGORIES)
            categories = {t.category for t in traits}
            expected_categories = {cat[0].category for cat in TRAIT_CATEGORIES}
            assert categories == expected_categories

    def test_assign_personalities_deterministic_with_seed(self) -> None:
        """同じシードで同じ結果が返ること。"""
        result1 = assign_personalities(4, random.Random(42))
        result2 = assign_personalities(4, random.Random(42))
        assert result1 == result2

    def test_build_personality_formats_traits(self) -> None:
        """build_personality が各特性を箇条書きで返すこと。"""
        rng = random.Random(42)
        traits = assign_personalities(1, rng)[0]
        result = build_personality(traits)
        for trait in traits:
            assert trait.description in result
        assert result.startswith("- ")

    def test_build_system_prompt_with_personality(self) -> None:
        """personality を渡すと性格セクションが含まれること。"""
        personality = "- 丁寧語で話す\n- 積極的に疑いを指摘する"
        result = build_system_prompt(Role.VILLAGER, personality=personality)
        assert "あなたの性格" in result
        assert "丁寧語で話す" in result
        assert "積極的に疑いを指摘する" in result

    def test_build_system_prompt_without_personality(self) -> None:
        """personality 未指定時は従来と同じ出力であること。"""
        result = build_system_prompt(Role.VILLAGER)
        assert "あなたの性格" not in result

    def test_build_system_prompt_with_empty_personality(self) -> None:
        """空文字列の personality では性格セクションが含まれないこと。"""
        result = build_system_prompt(Role.VILLAGER, personality="")
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
