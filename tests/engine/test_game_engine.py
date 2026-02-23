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


class TestGuardNightPhase:
    """護衛の夜フェーズテスト。"""

    def _setup_game_with_guard(
        self, guard_target: str, attack_target: str, seed: int = 42
    ) -> tuple[GameEngine, GameState]:
        """護衛と襲撃の対象を制御できるテスト用セットアップ。"""
        rng = random.Random(seed)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.KNIGHT),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
                Player(name="Frank", role=Role.WEREWOLF),
                Player(name="Grace", role=Role.MEDIUM),
                Player(name="Heidi", role=Role.MADMAN),
                Player(name="Ivan", role=Role.VILLAGER),
            )
        )

        class FixedProvider(RandomActionProvider):
            def __init__(self, fixed_guard: str | None = None, fixed_attack: str | None = None, **kwargs: object):
                super().__init__(**kwargs)
                self._fixed_guard = fixed_guard
                self._fixed_attack = fixed_attack

            def guard(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
                if self._fixed_guard:
                    return self._fixed_guard
                return super().guard(game, player, candidates)

            def attack(self, game: GameState, player: Player, candidates: tuple[Player, ...]) -> str:
                if self._fixed_attack:
                    return self._fixed_attack
                return super().attack(game, player, candidates)

        providers: dict[str, RandomActionProvider] = {}
        for p in game.players:
            if p.name == "Charlie":
                providers[p.name] = FixedProvider(fixed_guard=guard_target, rng=random.Random(rng.randint(0, 2**32)))
            elif p.name == "Bob":
                providers[p.name] = FixedProvider(fixed_attack=attack_target, rng=random.Random(rng.randint(0, 2**32)))
            else:
                providers[p.name] = RandomActionProvider(rng=random.Random(rng.randint(0, 2**32)))

        engine = GameEngine(game=game, providers=providers, rng=rng)
        engine._game = game  # noqa: SLF001
        return engine, game

    def test_guard_success_prevents_attack(self) -> None:
        """護衛成功時に襲撃が無効化される。"""
        engine, _ = self._setup_game_with_guard(guard_target="Alice", attack_target="Alice")
        result = engine._night_phase()  # noqa: SLF001

        # 護衛成功ログがある
        assert any("[護衛成功]" in log for log in result.log)
        # 「今夜は誰も襲撃されなかった」ログがある
        assert any("今夜は誰も襲撃されなかった" in log for log in result.log)
        # Alice は生存
        alice = result.find_player("Alice")
        assert alice is not None and alice.is_alive

    def test_guard_failure_attack_succeeds(self) -> None:
        """護衛失敗時に襲撃が成功する。"""
        engine, _ = self._setup_game_with_guard(guard_target="Dave", attack_target="Alice")
        result = engine._night_phase()  # noqa: SLF001

        # 護衛成功ログがない
        assert not any("[護衛成功]" in log for log in result.log)
        # Alice が襲撃された
        assert any("Alice が人狼に襲撃された" in log for log in result.log)
        alice = result.find_player("Alice")
        assert alice is not None and not alice.is_alive

    def test_guard_success_no_speaking_order_rotation(self) -> None:
        """護衛成功時は発言順が回転しない。"""
        engine, _ = self._setup_game_with_guard(guard_target="Alice", attack_target="Alice")
        order_before = engine._speaking_order  # noqa: SLF001
        engine._night_phase()  # noqa: SLF001
        # 護衛成功 → 誰も死んでいない → 発言順は変わらない
        assert engine._speaking_order == order_before  # noqa: SLF001


class TestMediumResult:
    """霊媒結果テスト。"""

    def test_medium_result_recorded_after_execution(self) -> None:
        """処刑後に霊媒結果が記録される。"""
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.KNIGHT),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
                Player(name="Frank", role=Role.WEREWOLF),
                Player(name="Grace", role=Role.MEDIUM),
                Player(name="Heidi", role=Role.MADMAN),
                Player(name="Ivan", role=Role.VILLAGER),
            )
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine._day_phase()  # noqa: SLF001

        # 霊媒結果が記録されている
        assert len(result.medium_results) == 1

    def test_medium_result_notified_on_day2(self) -> None:
        """Day 2 の昼フェーズで霊媒結果が通知される。"""
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.KNIGHT),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.VILLAGER),
                Player(name="Frank", role=Role.WEREWOLF),
                Player(name="Grace", role=Role.MEDIUM),
                Player(name="Heidi", role=Role.MADMAN),
                Player(name="Ivan", role=Role.VILLAGER),
            ),
            day=2,
            medium_results=((1, "Bob", True),),
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine._day_phase()  # noqa: SLF001

        medium_logs = [log for log in result.log if "[霊媒結果]" in log]
        assert len(medium_logs) == 1
        assert "Bob" in medium_logs[0]
        assert "人狼" in medium_logs[0]

    def test_no_medium_result_on_day1(self) -> None:
        """Day 1 では霊媒結果は通知されない。"""
        rng = random.Random(42)
        game = GameState(
            players=(
                Player(name="Alice", role=Role.SEER),
                Player(name="Bob", role=Role.WEREWOLF),
                Player(name="Charlie", role=Role.VILLAGER),
                Player(name="Dave", role=Role.VILLAGER),
                Player(name="Eve", role=Role.MEDIUM),
            ),
        )
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine._day_phase()  # noqa: SLF001

        medium_logs = [log for log in result.log if "[霊媒結果]" in log]
        assert len(medium_logs) == 0


class TestNinePlayerFullSimulation:
    """9人でのゲーム完走テスト。"""

    def test_nine_player_game_completes(self) -> None:
        """9人村（人狼2, 狩人1, 占い師1, 霊媒師1, 狂人1, 村人3）でゲームが完走する。"""
        for seed in [42, 100, 200, 500, 999]:
            rng = random.Random(seed)
            game = create_game(["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"], rng=rng)
            providers = _create_all_random_providers(game, rng)
            engine = GameEngine(game=game, providers=providers, rng=rng)

            result = engine.run()

            assert any("ゲーム終了" in log for log in result.log)
            # 護衛ログが存在する（狩人が行動した）
            assert any("[護衛]" in log for log in result.log)

    def test_nine_player_game_has_guard_and_medium(self) -> None:
        """9人村で護衛と霊媒が実際に機能する。"""
        rng = random.Random(42)
        game = create_game(["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"], rng=rng)
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        # 護衛ログが存在する
        guard_logs = [log for log in result.log if "[護衛]" in log]
        assert len(guard_logs) > 0

        # 霊媒結果が記録されている（少なくとも1回は処刑が発生するはず）
        assert len(result.medium_results) > 0
