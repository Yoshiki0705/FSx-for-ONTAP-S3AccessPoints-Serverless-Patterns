"""tests.e2e — エンドツーエンドテスト

実環境（FSx ONTAP、ECS Fargate、SQS、Step Functions）を使用した
統合テスト。CI 環境では pytest.mark.skipif で skip 可能。

テスト対象:
- Persistent Store Replay E2E Validation (Feature 7)
- Production UC Deployment Validation (Feature 12)
"""
