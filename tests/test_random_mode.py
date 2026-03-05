"""--random モード（RANDOM_MODE 環境変数）のテスト。"""

import argparse
import random

from starlette.testclient import TestClient

from llm_werewolf.main import app, interactive_store

client = TestClient(app, raise_server_exceptions=False)


class TestRandomModeStartup:
    """RANDOM_MODE 環境変数によるサーバー起動のテスト。"""

    def test_interactive_game_works_in_random_mode(self) -> None:
        """ランダムモードでインタラクティブゲームを作成・プレイできる。"""
        session = interactive_store.create("TestPlayer", rng=random.Random(42))
        try:
            assert session.game_id
            assert session.human_player_name == "TestPlayer"
            # RandomActionProvider が使用されている（LLMActionProvider ではない）
            for name, provider in session.providers.items():
                assert type(provider).__name__ == "RandomActionProvider"
        finally:
            interactive_store.delete(session.game_id)

    def test_play_endpoint_creates_game(self) -> None:
        """ランダムモードで /play エンドポイントがゲームを作成できる。"""
        response = client.post("/play", data={"player_name": "TestPlayer", "role": "random"}, follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/play/")


class TestRandomModeCliArgParsing:
    """__main__.py の --random 引数パースのテスト。"""

    def test_random_flag_parsed(self) -> None:
        """--random フラグが正しくパースされる。"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--random", action="store_true")
        args = parser.parse_args(["--random"])
        assert args.random is True

    def test_no_random_flag_default(self) -> None:
        """--random フラグなしではデフォルト False。"""
        parser = argparse.ArgumentParser()
        parser.add_argument("--random", action="store_true")
        args = parser.parse_args([])
        assert args.random is False
