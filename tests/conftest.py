import os

# main.py のモジュールレベルで load_llm_config() が呼ばれるため、
# テスト実行時にダミーの OPENAI_API_KEY を設定しておく必要がある。
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-testing")
