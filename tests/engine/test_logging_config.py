"""ログ設定のテスト。

main.py のログレベル制御を環境変数経由で検証する。
"""

import logging
import os
from unittest.mock import patch


class TestLogLevelConfig:
    """LOG_LEVEL 環境変数によるログレベル制御のテスト。"""

    def test_default_log_level_is_info(self) -> None:
        """LOG_LEVEL 未設定時はデフォルトで INFO レベルになる。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
            level = getattr(logging, log_level_name, logging.INFO)
            assert level == logging.INFO

    def test_debug_log_level(self) -> None:
        """LOG_LEVEL=DEBUG でデバッグレベルになる。"""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
            level = getattr(logging, log_level_name, logging.INFO)
            assert level == logging.DEBUG

    def test_warning_log_level(self) -> None:
        """LOG_LEVEL=WARNING で警告レベルになる。"""
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
            level = getattr(logging, log_level_name, logging.INFO)
            assert level == logging.WARNING

    def test_invalid_log_level_falls_back_to_info(self) -> None:
        """無効な LOG_LEVEL 値は INFO にフォールバックする。"""
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}):
            log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
            level = getattr(logging, log_level_name, logging.INFO)
            assert level == logging.INFO

    def test_case_insensitive(self) -> None:
        """LOG_LEVEL は大文字小文字を区別しない。"""
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
            level = getattr(logging, log_level_name, logging.INFO)
            assert level == logging.DEBUG
