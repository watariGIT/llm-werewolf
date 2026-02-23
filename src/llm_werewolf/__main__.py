"""``python -m llm_werewolf`` エントリポイント。

uvicorn をプログラム的に起動し、CLI 引数でデバッグオプションを制御する。

Usage::

    uv run python -m llm_werewolf                 # 通常起動
    uv run python -m llm_werewolf --llm-debug      # LLM プロンプト/レスポンス/トークン数を表示
    uv run python -m llm_werewolf --port 8080      # ポート指定
"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM人狼 Web サーバー")
    parser.add_argument("--host", default="127.0.0.1", help="バインドホスト (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="バインドポート (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="ファイル変更時に自動リロード")
    parser.add_argument(
        "--llm-debug",
        action="store_true",
        help="LLM プロンプト・レスポンス・トークン使用量を標準出力に表示",
    )
    args = parser.parse_args()

    if args.llm_debug:
        os.environ["LLM_DEBUG"] = "1"

    uvicorn.run("llm_werewolf.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
