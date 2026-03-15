"""Web UI スクリーンショット自動キャプチャスクリプト。

--random モードでサーバーを起動し、Playwright で全 GameStep の
スクリーンショットを撮影する。

Usage::

    uv run playwright install chromium
    uv run python scripts/capture_ui.py
    uv run python scripts/capture_ui.py --role seer
    uv run python scripts/capture_ui.py --role werewolf --output-dir my_screenshots
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import ElementHandle, Page, sync_playwright

DEFAULT_PORT = 8765
MAX_STEPS = 200  # 無限ループ防止


def wait_for_server(base_url: str, timeout: int = 30) -> None:
    """サーバーが起動するまでポーリングで待機する。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"サーバーが {timeout} 秒以内に起動しませんでした")


def get_step(page: Page) -> str:
    """現在の GameStep を data-step 属性から取得する。"""
    return page.get_attribute("body", "data-step") or ""


def capture(page: Page, output_dir: Path, index: int, name: str) -> Path:
    """スクリーンショットを撮影して保存する。"""
    filename = f"{index:02d}_{name}.png"
    filepath = output_dir / filename
    page.screenshot(path=str(filepath), full_page=True)
    print(f"  captured: {filepath}")
    return filepath


def select_first_candidate(form: ElementHandle) -> str | None:
    """フォーム内のラジオボタンまたは select の最初の候補を選択し、その値を返す。"""
    radio = form.query_selector('input[type="radio"]')
    if radio:
        value = radio.get_attribute("value") or ""
        # カードUI では radio が非表示のため、親 label をクリックして選択する
        label = form.query_selector("label")
        if label:
            label.click()
        else:
            radio.check(force=True)
        return value
    select = form.query_selector("select")
    if select:
        option = form.query_selector("select option:not([value=''])")
        if option:
            value = option.get_attribute("value") or ""
            select.select_option(value)
            return value
    return None


def _click_submit_in(form: ElementHandle, page: Page) -> None:
    """フォーム内の submit ボタンをクリックする。見つからなければフォールバック。"""
    btn = form.query_selector('button[type="submit"]')
    if btn:
        btn.click()
        return
    page.click('button[type="submit"]')


def _submit_and_wait(page: Page, click_fn: Callable[[], None] | None = None) -> None:
    """フォーム送信してナビゲーション完了を待つ。"""
    with page.expect_navigation(wait_until="networkidle"):
        if click_fn is not None:
            click_fn()
        else:
            page.click('button[type="submit"]')


def _select_and_submit(page: Page, form_selector: str) -> None:
    """フォーム内の最初の候補を選択して送信する。"""
    form = page.query_selector(form_selector)
    if form:
        select_first_candidate(form)
        _submit_and_wait(page, lambda: _click_submit_in(form, page))
    else:
        _submit_and_wait(page)


def run_capture(role: str, output_dir: Path, base_url: str) -> list[Path]:
    """Playwright でゲームを自動操作しスクリーンショットを撮影する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    captured: list[Path] = []
    idx = 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # 1. トップページ
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        captured.append(capture(page, output_dir, idx, "index"))
        idx += 1

        # 2. ゲーム作成
        page.fill('input[name="player_name"]', "テストプレイヤー")
        # ラジオボタンは display:none なので、親の label をクリックして選択する
        page.click(f'label:has(input[name="role"][value="{role}"])')
        _submit_and_wait(page)

        # 3. ゲームループ
        captured_steps: set[str] = set()
        for _ in range(MAX_STEPS):
            step = get_step(page)
            if not step:
                break

            # 各ステップで最初の1回だけキャプチャ
            if step not in captured_steps:
                captured.append(capture(page, output_dir, idx, step))
                captured_steps.add(step)
                idx += 1

            if step == "game_over":
                break

            # ステップに応じた操作（フォーム送信 → ナビゲーション完了待ち）
            if step == "role_reveal":
                _submit_and_wait(page)
            elif step == "discussion":
                textarea = page.query_selector('textarea[name="message"]')
                if textarea:
                    textarea.fill("テスト発言です。")
                    _submit_and_wait(page, lambda: page.click('form[action*="discuss"] button[type="submit"]'))
                else:
                    _submit_and_wait(page)
            elif step == "vote":
                _select_and_submit(page, 'form[action*="vote"]')
            elif step == "execution_result":
                _submit_and_wait(page)
            elif step == "night_action":
                _select_and_submit(page, 'form[action*="night-action"]')
            elif step == "night_result":
                _submit_and_wait(page)
            else:
                break

        if not captured_steps or "game_over" not in captured_steps:
            print(
                f"警告: ゲームが正常に終了しませんでした（{len(captured_steps)} ステップをキャプチャ）", file=sys.stderr
            )

        browser.close()

    return captured


def main() -> None:
    parser = argparse.ArgumentParser(description="Web UI スクリーンショットキャプチャ")
    parser.add_argument("--role", default="villager", help="プレイヤー役職 (default: villager)")
    parser.add_argument("--output-dir", default="screenshots", help="出力ディレクトリ (default: screenshots)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"サーバーポート (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    port: int = args.port
    base_url = f"http://127.0.0.1:{port}"
    output_dir = Path(args.output_dir) / args.role

    # サーバーをサブプロセスで起動
    print(f"サーバーを --random モードでポート {port} で起動中...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "llm_werewolf", "--random", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        wait_for_server(base_url)
        print("サーバー起動完了")

        print(f"キャプチャ開始 (role={args.role}, output={output_dir})")
        captured = run_capture(args.role, output_dir, base_url)
        print(f"\n完了: {len(captured)} 枚のスクリーンショットを保存しました")
        for path in captured:
            print(f"  {path}")
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=5)
        print("サーバー停止")


if __name__ == "__main__":
    main()
