"""投票・夜行動の並行実行に関するテスト。

ThreadPoolExecutor による並行実行で結果が正しく収集・適用されることを検証する。
"""

import random
import threading

from llm_werewolf.domain.game import GameState
from llm_werewolf.domain.player import Player
from llm_werewolf.domain.services import create_game, create_game_with_role
from llm_werewolf.domain.value_objects import Role
from llm_werewolf.engine.game_engine import GameEngine
from llm_werewolf.engine.interactive_engine import InteractiveGameEngine
from llm_werewolf.engine.random_provider import RandomActionProvider

AI_NAMES = ["AI-1", "AI-2", "AI-3", "AI-4", "AI-5", "AI-6", "AI-7", "AI-8"]
ALL_NAMES_9 = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"]


def _create_all_random_providers(game: GameState, rng: random.Random) -> dict[str, RandomActionProvider]:
    return {p.name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for p in game.players}


class TestParallelVoteInteractiveEngine:
    """InteractiveGameEngine の投票並行実行テスト。"""

    def _create_engine(
        self,
        seed: int = 42,
        human_name: str = "Alice",
        role: Role | None = None,
    ) -> InteractiveGameEngine:
        rng = random.Random(seed)
        all_names = [human_name] + AI_NAMES
        if role is not None:
            game = create_game_with_role(all_names, human_name, role, rng=rng)
        else:
            game = create_game(all_names, rng=rng)
        game = game.add_log("=== ゲーム開始 ===")
        for p in game.players:
            game = game.add_log(f"[配役] {p.name}: {p.role.value}")

        providers = {name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES}
        speaking_order = tuple(rng.sample(all_names, len(all_names)))

        return InteractiveGameEngine(
            game=game,
            providers=providers,
            human_player_name=human_name,
            rng=rng,
            speaking_order=speaking_order,
        )

    def test_parallel_vote_collects_all_ai_votes(self) -> None:
        """並行投票で全AIプレイヤーの投票が収集されること。"""
        engine = self._create_engine(role=Role.VILLAGER)
        votes: dict[str, str] = {}
        votes["Alice"] = "AI-1"

        engine._collect_ai_votes(votes)  # noqa: SLF001

        # ユーザー + 全AI の投票が収集されている
        assert "Alice" in votes
        assert len(votes) == len(engine.game.alive_players)
        # 自分に投票していないこと
        for voter, target in votes.items():
            assert voter != target

    def test_parallel_vote_uses_multiple_threads(self) -> None:
        """並行投票が複数スレッドで実行されることを確認する。"""
        thread_ids: set[int] = set()
        barrier = threading.Barrier(len(AI_NAMES))
        original_vote = RandomActionProvider.vote

        def tracking_vote(
            self_prov: RandomActionProvider, game: GameState, player: Player, candidates: tuple[Player, ...]
        ) -> str:
            thread_ids.add(threading.current_thread().ident or 0)
            # バリアで全スレッドが揃うまで待機し、並行実行を保証
            barrier.wait(timeout=5)
            return original_vote(self_prov, game, player, candidates)

        engine = self._create_engine(role=Role.VILLAGER)
        for name in AI_NAMES:
            provider = engine._providers[name]  # noqa: SLF001
            provider.vote = lambda g, p, c, prov=provider: tracking_vote(prov, g, p, c)  # type: ignore[assignment]

        votes: dict[str, str] = {}
        engine._collect_ai_votes(votes)  # noqa: SLF001

        # 複数のスレッドIDが記録されている（並行実行の証拠）
        assert len(thread_ids) > 1

    def test_parallel_vote_progress_callback(self) -> None:
        """並行投票で progress コールバックが全AIに対して呼ばれること。"""
        progress_calls: list[tuple[str, str]] = []

        def on_progress(player_name: str, action_type: str) -> None:
            progress_calls.append((player_name, action_type))

        engine = self._create_engine(role=Role.VILLAGER)
        engine._on_progress = on_progress  # noqa: SLF001

        votes: dict[str, str] = {}
        engine._collect_ai_votes(votes)  # noqa: SLF001

        vote_progress = [(name, action) for name, action in progress_calls if action == "vote"]
        assert len(vote_progress) == len(AI_NAMES)


class TestParallelNightInteractiveEngine:
    """InteractiveGameEngine の夜行動並行実行テスト。"""

    def _create_engine_at_night(self, seed: int = 42) -> InteractiveGameEngine:
        rng = random.Random(seed)
        all_names = ["Alice"] + AI_NAMES
        game = create_game_with_role(all_names, "Alice", Role.VILLAGER, rng=rng)
        game = game.add_log("=== ゲーム開始 ===")

        providers = {name: RandomActionProvider(rng=random.Random(rng.randint(0, 2**32))) for name in AI_NAMES}
        speaking_order = tuple(rng.sample(all_names, len(all_names)))

        return InteractiveGameEngine(
            game=game,
            providers=providers,
            human_player_name="Alice",
            rng=rng,
            speaking_order=speaking_order,
        )

    def test_parallel_night_resolves_correctly(self) -> None:
        """並行夜行動で結果が正しく適用されること。"""
        engine = self._create_engine_at_night()
        engine.start_night()
        night_messages, winner = engine.resolve_night()

        # 夜フェーズが正常に解決されている
        game = engine.game
        assert game.day == 2  # 次の日に進んでいる

    def test_parallel_night_progress_callback(self) -> None:
        """並行夜行動で progress コールバックが呼ばれること。"""
        progress_calls: list[tuple[str, str]] = []

        def on_progress(player_name: str, action_type: str) -> None:
            progress_calls.append((player_name, action_type))

        engine = self._create_engine_at_night()
        engine._on_progress = on_progress  # noqa: SLF001
        engine.start_night()
        engine.resolve_night()

        night_actions = [action for _, action in progress_calls if action in ("divine", "guard", "attack")]
        assert len(night_actions) > 0


class TestParallelVoteGameEngine:
    """GameEngine の投票並行実行テスト。"""

    def test_simulation_completes_with_parallel_votes(self) -> None:
        """並行投票でゲームが最後まで完走すること。"""
        rng = random.Random(42)
        game = create_game(ALL_NAMES_9, rng=rng)
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        assert any("ゲーム終了" in log for log in result.log)
        assert any("勝利" in log for log in result.log)

    def test_simulation_multiple_seeds(self) -> None:
        """複数の seed で並行投票ゲームが完走すること。"""
        for seed in [1, 10, 100, 999]:
            rng = random.Random(seed)
            game = create_game(ALL_NAMES_9, rng=rng)
            providers = _create_all_random_providers(game, rng)
            engine = GameEngine(game=game, providers=providers, rng=rng)

            result = engine.run()
            assert any("ゲーム終了" in log for log in result.log)


class TestParallelNightGameEngine:
    """GameEngine の夜行動並行実行テスト。"""

    def test_night_phase_resolves_with_parallel_decisions(self) -> None:
        """並行夜行動でゲームが正常に進行すること。"""
        rng = random.Random(42)
        game = create_game(ALL_NAMES_9, rng=rng)
        providers = _create_all_random_providers(game, rng)
        engine = GameEngine(game=game, providers=providers, rng=rng)

        result = engine.run()

        # 夜フェーズのログが正しく記録されている
        assert any("夜フェーズ" in log for log in result.log)
        # 襲撃ログが存在する
        assert any("[襲撃]" in log for log in result.log)
