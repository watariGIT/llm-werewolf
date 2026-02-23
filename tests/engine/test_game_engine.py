import random
from dataclasses import replace

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import create_game
from llm_werewolf.domain.value_objects import Phase, PlayerStatus, Role
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider


def _create_all_random_providers(game: GameState, rng: random.Random) -> dict[str, RandomActionProvider]:
    """全プレイヤーに RandomActionProvider を割り当てる。"""
    return {p.name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for p in game.players}


class TestGameEngineFullSimulation:
    """seed 固定で1ゲーム分のシミュレーションが完走することを確認する。"""

    def test_simulation_completes_with_winner(self) -> None:
        rng = random.Random(42)
        game = create_game(["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"], rng=rng)
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        # ゲームが終了していること
        assert any("ゲーム終了" in log for log in result.log)
        # 勝利陣営が記録されていること
        assert any("勝利" in log for log in result.log)

    def test_simulation_with_different_seeds(self) -> None:
        """複数の seed でシミュレーションが完走することを確認する。"""
        for seed in [1, 10, 100, 999, 12345]:
            rng = random.Random(seed)
            game = create_game(["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"], rng=rng)
            providers = _create_all_random_providers(game, rng)
            engine = GameEngine(game=game, providers=providers, rng=rng)

            result = engine.run()
            assert any("ゲーム終了" in log for log in result.log)

    def test_dead_players_are_marked_dead(self) -> None:
        rng = random.Random(42)
        game = create_game(["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"], rng=rng)
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        dead_players = [p for p in result.players if p.status == PlayerStatus.DEAD]
        assert len(dead_players) > 0


class TestDayPhase:
    """昼フェーズの個別テスト。"""

    def _setup_game(self, seed: int = 42) -> tuple[GameEngine, GameState]:
        rng = random.Random(seed)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)
        return engine, game

    def test_discussion_logs_created_day1(self) -> None:
        engine, _ = self._setup_game()
        result = engine._day_phase()  # noqa: SLF001

        # Day 1 は 1巡 = 5人分の発言
        discussion_logs = [log for log in result.log if "[発言]" in log]
        assert len(discussion_logs) == 5

    def test_discussion_logs_created_day2(self) -> None:
        engine, game = self._setup_game()
        # Day 2 に設定
        engine._game = replace(game, day=2)  # noqa: SLF001
        result = engine._day_phase()  # noqa: SLF001

        # Day 2 は 2巡 = 10人分の発言
        discussion_logs = [log for log in result.log if "[発言]" in log]
        assert len(discussion_logs) == 10

    def test_vote_logs_created(self) -> None:
        engine, _ = self._setup_game()
        result = engine._day_phase()  # noqa: SLF001

        vote_logs = [log for log in result.log if "[投票]" in log]
        assert len(vote_logs) == 5

    def test_execution_happens(self) -> None:
        engine, _ = self._setup_game()
        result = engine._day_phase()  # noqa: SLF001

        execution_logs = [log for log in result.log if "[処刑]" in log]
        assert len(execution_logs) == 1


class TestNightPhase:
    """夜フェーズの個別テスト。"""

    def test_attack_kills_player(self) -> None:
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)
        engine._game = game  # noqa: SLF001

        result = engine._night_phase()  # noqa: SLF001

        attack_logs = [log for log in result.log if "[襲撃]" in log]
        assert len(attack_logs) == 1
        dead_count = sum(1 for p in result.players if p.status == PlayerStatus.DEAD)
        assert dead_count == 1

    def test_divine_recorded_when_seer_survives(self) -> None:
        rng = random.Random(100)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)
        engine._game = game  # noqa: SLF001

        result = engine._night_phase()  # noqa: SLF001

        # 占い師が生存していれば占い履歴が記録される
        seer_alive = any(p.name == "Alice" and p.is_alive for p in result.players)
        if seer_alive:
            assert len(result.divined_history) == 1
        else:
            # 占い師が襲撃された場合、占い結果は無効
            assert len(result.divined_history) == 0

    def test_night_transitions_to_next_day(self) -> None:
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)
        engine._game = game  # noqa: SLF001

        result = engine._night_phase()  # noqa: SLF001

        assert result.phase == Phase.DAY
        assert result.day == 2


class TestVoteTie:
    """同票時のランダム処刑テスト。"""

    def test_tie_resolved_by_random(self) -> None:
        """同一 seed で同票時の結果が決定的であることを確認する。"""
        results = []
        for _ in range(2):
            rng = random.Random(42)
            game = GameState(
                players=(
                    Player(name="Alice", role=Role.SEER),
                    Player(name="Bob", role=Role.WEREWOLF),
                    Player(name="Charlie", role=Role.VILLAGER),
                    Player(name="Dave", role=Role.VILLAGER),
                    Player(name="Eve", role=Role.VILLAGER),
                )
            )
            providers = _create_all_random_providers(game, rng)
            engine = GameEngine(game=game, providers=providers, rng=rng)
            result = engine._day_phase()  # noqa: SLF001
            execution_log = [log for log in result.log if "[処刑]" in log]
            results.append(execution_log)

        assert results[0] == results[1]


class TestDivineResultNotification:
    """占い結果通知テスト。"""

    def test_divine_result_notified_on_day2(self) -> None:
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            ),
            day=2,
            divined_history=(("Alice", "Charlie"),),
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine._day_phase()  # noqa: SLF001

        divine_result_logs = [log for log in result.log if "[占い結果]" in log]
        assert len(divine_result_logs) == 1
        assert "Charlie" in divine_result_logs[0]
        assert "人狼ではない" in divine_result_logs[0]

    def test_no_divine_result_on_day1(self) -> None:
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            ),
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine._day_phase()  # noqa: SLF001

        divine_result_logs = [log for log in result.log if "[占い結果]" in log]
        assert len(divine_result_logs) == 0


class TestSpeakingOrder:
    """発言順のテスト。"""

    def _setup_engine(self, seed: int = 42) -> GameEngine:
        rng = random.Random(seed)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        return GameEngine(game=game, providers=providers, rng=rng)

    def _extract_speaker_order(self, game: GameState, round_num: int = 1) -> list[str]:
        """ログから指定ラウンドの発言順を抽出する。"""
        in_round = False
        speakers: list[str] = []
        current_round = 0
        for log in game.log:
            if "[議論] ラウンド" in log:
                current_round += 1
                in_round = current_round == round_num
                continue
            if in_round and "[発言]" in log:
                # "[発言] Alice: ..." → "Alice"
                name = log.split("[発言] ")[1].split(":")[0]
                speakers.append(name)
        return speakers

    def test_day1_discussion_follows_speaking_order(self) -> None:
        """Day 1 の発言順が speaking_order に基づくことを確認する。"""
        engine = self._setup_engine()
        speaking_order = list(engine._speaking_order)  # noqa: SLF001
        result = engine._day_phase()  # noqa: SLF001

        speakers = self._extract_speaker_order(result, round_num=1)
        assert len(speakers) == 5

        # speaking_order と一致すること（Day 1 は全員生存なので全員含まれる）
        assert speakers == speaking_order

    def test_speaking_order_rotates_after_night_attack(self) -> None:
        """夜襲撃後に発言順が回転することを確認する。"""
        engine = self._setup_engine()
        original_order = engine._speaking_order  # noqa: SLF001

        # 夜フェーズを実行（襲撃が発生する）
        engine._game = engine._day_phase()  # noqa: SLF001
        engine._game = engine._night_phase()  # noqa: SLF001

        new_order = engine._speaking_order  # noqa: SLF001
        # 襲撃があれば発言順が変わっているはず
        attack_logs = [log for log in engine._game.log if "[襲撃]" in log]  # noqa: SLF001
        if attack_logs:
            assert new_order != original_order
            # 襲撃された人は新しい発言順に含まれない
            attacked_name = attack_logs[0].split("[襲撃] ")[1].split(" が")[0]
            assert attacked_name not in new_order

    def test_speaking_order_maintained_across_rounds(self) -> None:
        """Day 2 の 2 ラウンドで発言順が同じことを確認する。"""
        engine = self._setup_engine()

        # Day 2 に設定
        engine._game = replace(engine._game, day=2)  # noqa: SLF001
        result = engine._day_phase()  # noqa: SLF001

        round1_speakers = self._extract_speaker_order(result, round_num=1)
        round2_speakers = self._extract_speaker_order(result, round_num=2)
        assert round1_speakers == round2_speakers
