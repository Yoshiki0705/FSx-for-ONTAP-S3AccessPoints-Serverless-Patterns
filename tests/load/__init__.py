"""tests.load — 負荷テスト

FPolicy イベントパイプラインの負荷テスト。
実環境（FSx ONTAP、ECS Fargate、SQS）を使用する。
CI 環境では pytest.mark.skipif で skip 可能。

テスト対象:
- Replay Storm Testing (Feature 8)
- High-Load Testing (Feature 9)
"""
