# レイヤー依存ルール

- ドメイン層 (`domain/`): Python 標準ライブラリのみ
- アプリケーション層 (`engine/`): Python 標準ライブラリ + domain 層のみ
- インフラ層 (`main.py`, `templates/`): 全ライブラリ使用可。engine / domain への import 可
- 依存の方向: インフラ → アプリケーション → ドメイン（逆方向の依存禁止）
