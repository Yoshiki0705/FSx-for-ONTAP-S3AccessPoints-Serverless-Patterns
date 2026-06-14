# 開発環境セットアップ（開発オンボーディング）

> 架空のサンプルデータです。

## 前提ツール
- Git, Python 3.12+, Node.js 20+, Docker
- AWS CLI v2, SAM CLI

## 手順
1. リポジトリをクローン
2. 依存インストール（`pip install -r requirements-dev.txt`）
3. pre-commit フック設定（`pre-commit install`）
4. ローカルテスト実行（`pytest`）

## アクセス
- 開発用 AWS アカウントは AssumeRole で利用（IAM ユーザーは作らない）
- シークレットは Secrets Manager を参照

## 困ったら
- 開発者向けチャット #dev-help
