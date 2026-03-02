import random

import pytest

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.game_log import filter_log_entries, format_log_for_context, format_public_log
from llm_werewolf.domain.services import create_game
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider


def _run_game(seed: int = 42) -> tuple[list[str], GameState]:
    """テスト用にゲームを実行し、(player_names, game) を返す。"""
    rng = random.Random(seed)
    player_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Heidi", "Ivan"]
    game = create_game(player_names, rng=rng)
    providers = {p.name: RandomActionProvider(rng=rng) for p in game.players}
    engine = GameEngine(game, providers, rng=rng)
    final = engine.run()
    return player_names, final


class TestFormatLogForContext:
    def test_raises_for_unknown_player(self) -> None:
        _, game = _run_game()
        with pytest.raises(ValueError, match="Player 'Unknown' not found"):
            format_log_for_context(game, "Unknown")

    def test_villager_cannot_see_others_role_assignment(self) -> None:
        _, game = _run_game()
        # 村人を探す
        from llm_werewolf.domain.value_objects import Role

        villager = next(p for p in game.players if p.role == Role.VILLAGER)
        log_text = format_log_for_context(game, villager.name)

        # 自分の配役は見える
        assert f"[配役] {villager.name}" in log_text

        # 他のプレイヤーの配役は見えない
        for p in game.players:
            if p.name != villager.name:
                assert f"[配役] {p.name}" not in log_text

    def test_seer_can_see_divine_logs(self) -> None:
        _, game = _run_game()
        from llm_werewolf.domain.value_objects import Role

        seer = next(p for p in game.players if p.role == Role.SEER)
        log_text = format_log_for_context(game, seer.name)

        # 占い師は占いログが見える
        if "[占い]" in "\n".join(game.log):
            assert "[占い]" in log_text

    def test_non_seer_cannot_see_divine_logs(self) -> None:
        _, game = _run_game()
        from llm_werewolf.domain.value_objects import Role

        non_seer = next(p for p in game.players if p.role != Role.SEER)
        log_text = format_log_for_context(game, non_seer.name)

        # 占い師以外は占いログが見えない
        assert "[占い]" not in log_text
        assert "[占い結果]" not in log_text

    def test_all_players_can_see_discussion_and_vote(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "[発言]" in log_text
            assert "[投票]" in log_text

    def test_all_players_can_see_game_start_and_end(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "=== ゲーム開始 ===" in log_text
            assert "=== ゲーム終了" in log_text

    def test_all_players_can_see_execution(self) -> None:
        _, game = _run_game()
        for p in game.players:
            log_text = format_log_for_context(game, p.name)
            assert "[処刑]" in log_text


class TestGuardLogVisibility:
    """護衛ログの可視性テスト"""

    def test_knight_can_see_own_guard_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.KNIGHT),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[護衛] Aliceが Charlieを護衛した",))
        log_text = format_log_for_context(game, "Alice")
        assert "[護衛]" in log_text

    def test_non_knight_cannot_see_guard_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.KNIGHT),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[護衛] Aliceが Charlieを護衛した",))
        for name in ("Bob", "Charlie"):
            log_text = format_log_for_context(game, name)
            assert "[護衛]" not in log_text


class TestMediumResultLogVisibility:
    """霊媒結果ログの可視性テスト"""

    def test_medium_can_see_own_medium_result_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.MEDIUM),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[霊媒結果] Aliceの霊媒: Bobは人狼だった",))
        log_text = format_log_for_context(game, "Alice")
        assert "[霊媒結果]" in log_text

    def test_non_medium_cannot_see_medium_result_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.MEDIUM),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[霊媒結果] Aliceの霊媒: Bobは人狼だった",))
        for name in ("Bob", "Charlie"):
            log_text = format_log_for_context(game, name)
            assert "[霊媒結果]" not in log_text


class TestWerewolfAllyLogVisibility:
    """人狼仲間ログの可視性テスト"""

    def test_werewolf_can_see_ally_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.WEREWOLF),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
        )
        game = GameState(players=players, log=("[人狼仲間] 人狼はAlice, Bobです",))
        for name in ("Alice", "Bob"):
            log_text = format_log_for_context(game, name)
            assert "[人狼仲間]" in log_text

    def test_non_werewolf_cannot_see_ally_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.WEREWOLF),
            Player(name="Bob", role=Role.WEREWOLF),
            Player(name="Charlie", role=Role.VILLAGER),
            Player(name="Diana", role=Role.SEER),
            Player(name="Eve", role=Role.MADMAN),
        )
        game = GameState(players=players, log=("[人狼仲間] 人狼はAlice, Bobです",))
        for name in ("Charlie", "Diana", "Eve"):
            log_text = format_log_for_context(game, name)
            assert "[人狼仲間]" not in log_text


class TestFormatPublicLog:
    """format_public_log のテスト。"""

    def test_excludes_private_entries(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.SEER),
            Player(name="Bob", role=Role.WEREWOLF),
        )
        game = GameState(
            players=players,
            log=(
                "[配役] Alice: seer",
                "[発言] Alice: おはよう",
                "[占い結果] Alice の占い: Bob は人狼",
                "[占い] Alice が Bob を占った",
                "[護衛] Eve が Alice を護衛した",
                "[霊媒結果] Frank の霊媒: Bob は人狼だった",
                "[人狼仲間] 人狼はBobです",
                "[護衛成功] Alice への襲撃は護衛により阻止された",
                "[投票] Alice → Bob",
                "[処刑] Bob が処刑された",
            ),
        )
        result = format_public_log(game)
        assert "[発言] Alice: おはよう" in result
        assert "[投票] Alice → Bob" in result
        assert "[処刑] Bob が処刑された" in result
        assert "[配役]" not in result
        assert "[占い結果]" not in result
        assert "[占い]" not in result
        assert "[護衛]" not in result
        assert "[霊媒結果]" not in result
        assert "[人狼仲間]" not in result
        assert "[護衛成功]" not in result

    def test_empty_log(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (Player(name="Alice", role=Role.VILLAGER),)
        game = GameState(players=players)
        result = format_public_log(game)
        assert result == ""


class TestFilterLogEntries:
    """filter_log_entries のテスト。"""

    def test_filters_entries_by_player(self) -> None:
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [
            "[配役] Alice: villager",
            "[配役] Bob: werewolf",
            "[発言] Alice: test",
        ]
        result = filter_log_entries(entries, player)
        assert "[配役] Alice" in result
        assert "[配役] Bob" not in result
        assert "[発言] Alice: test" in result


class TestFilterLogEntriesWithLimit:
    """filter_log_entries の max_recent_statements パラメータのテスト。"""

    def test_default_no_limit(self) -> None:
        """デフォルト（max_recent_statements=-1）では全件保持する。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [f"[発言] Alice: 発言{i}" for i in range(10)]
        result = filter_log_entries(entries, player)
        for i in range(10):
            assert f"発言{i}" in result

    def test_limits_statements(self) -> None:
        """max_recent_statements で発言ログが制限されること。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [f"[発言] Alice: 発言{i}" for i in range(10)]
        result = filter_log_entries(entries, player, max_recent_statements=3)
        for i in range(7):
            assert f"発言{i}" not in result
        for i in range(7, 10):
            assert f"発言{i}" in result

    def test_events_always_kept(self) -> None:
        """イベントログは制限の対象外で常に保持される。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [
            "[投票] Alice → Bob",
            "[発言] Alice: 発言0",
            "[発言] Alice: 発言1",
            "[発言] Alice: 発言2",
            "[処刑] Bob が処刑された",
        ]
        result = filter_log_entries(entries, player, max_recent_statements=1)
        assert "[投票] Alice → Bob" in result
        assert "[処刑] Bob が処刑された" in result
        assert "発言0" not in result
        assert "発言1" not in result
        assert "発言2" in result

    def test_maintains_original_order(self) -> None:
        """トリム後も元の順序が維持されること。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [
            "[投票] Alice → Bob",
            "[発言] Alice: 発言0",
            "[発言] Alice: 発言1",
            "[処刑] Bob が処刑された",
        ]
        result = filter_log_entries(entries, player, max_recent_statements=1)
        lines = result.split("\n")
        vote_idx = next(i for i, line in enumerate(lines) if line.startswith("[投票]"))
        statement_idx = next(i for i, line in enumerate(lines) if line.startswith("[発言]"))
        exec_idx = next(i for i, line in enumerate(lines) if line.startswith("[処刑]"))
        assert vote_idx < statement_idx < exec_idx

    def test_zero_removes_all_statements(self) -> None:
        """0 を指定した場合は全発言が除外される。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        player = Player(name="Alice", role=Role.VILLAGER)
        entries = [
            "[投票] Alice → Bob",
            "[発言] Alice: 発言0",
            "[発言] Alice: 発言1",
        ]
        result = filter_log_entries(entries, player, max_recent_statements=0)
        assert "[発言]" not in result
        assert "[投票]" in result


class TestLogVolumeControl:
    """format_log_for_context のログ量制御テスト。"""

    def _create_game_with_statements(self, count: int) -> GameState:
        """指定数の発言ログ + イベントログを含むゲーム状態を作成する。"""
        from llm_werewolf.domain.player import Player
        from llm_werewolf.domain.value_objects import Role

        players = (
            Player(name="Alice", role=Role.VILLAGER),
            Player(name="Bob", role=Role.VILLAGER),
        )
        log: list[str] = ["[配役] Alice: villager", "=== ゲーム開始 ===", "--- Day 1 ---"]
        for i in range(count):
            log.append(f"[発言] Alice: 発言{i}")
        log.append("[投票] Alice → Bob")
        log.append("[処刑] Bob が処刑された")
        return GameState(players=players, log=tuple(log))

    def test_keeps_all_when_under_limit(self) -> None:
        """発言数がデフォルト制限(30)以下の場合、全件保持する。"""
        game = self._create_game_with_statements(5)
        result = format_log_for_context(game, "Alice")
        for i in range(5):
            assert f"発言{i}" in result

    def test_trims_old_statements(self) -> None:
        """発言数が max_recent_statements を超える場合、古い発言をトリムする。"""
        game = self._create_game_with_statements(10)
        result = format_log_for_context(game, "Alice", max_recent_statements=3)
        # 古い発言（0〜6）はトリムされる
        for i in range(7):
            assert f"発言{i}" not in result
        # 直近3件は残る
        for i in range(7, 10):
            assert f"発言{i}" in result

    def test_events_always_kept(self) -> None:
        """イベントログは量制御の対象外で常に保持される。"""
        game = self._create_game_with_statements(10)
        result = format_log_for_context(game, "Alice", max_recent_statements=0)
        # 発言は全て除外される
        assert "[発言]" not in result
        # イベントは残る（[配役] は自分のもののみ見える）
        assert "[配役] Alice: villager" in result
        assert "=== ゲーム開始 ===" in result
        assert "--- Day 1 ---" in result
        assert "[投票] Alice → Bob" in result
        assert "[処刑] Bob が処刑された" in result
        # 結果の行数を確認（配役1 + 開始1 + Day区切り1 + 投票1 + 処刑1 = 5行）
        lines = [line for line in result.split("\n") if line]
        assert len(lines) == 5

    def test_maintains_original_order(self) -> None:
        """トリム後もイベントと発言の出現順が維持される。"""
        game = self._create_game_with_statements(5)
        result = format_log_for_context(game, "Alice", max_recent_statements=2)
        lines = result.split("\n")
        # イベント → 発言 → イベント の順番が維持されることを確認
        statement_indices = [i for i, line in enumerate(lines) if line.startswith("[発言]")]
        vote_index = next(i for i, line in enumerate(lines) if line.startswith("[投票]"))
        # 発言は投票の前にある
        assert all(si < vote_index for si in statement_indices)

    def test_negative_keeps_all(self) -> None:
        """負の値を指定した場合は全件保持する。"""
        game = self._create_game_with_statements(50)
        result = format_log_for_context(game, "Alice", max_recent_statements=-1)
        for i in range(50):
            assert f"発言{i}" in result

    def test_zero_removes_all_statements(self) -> None:
        """0を指定した場合は全発言が除外され、イベントのみ残る。"""
        game = self._create_game_with_statements(5)
        result = format_log_for_context(game, "Alice", max_recent_statements=0)
        assert "[発言]" not in result
        assert "[投票]" in result
