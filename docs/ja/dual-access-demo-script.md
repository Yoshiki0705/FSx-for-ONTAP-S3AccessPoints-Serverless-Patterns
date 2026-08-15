# デュアルアクセスデモ — NFS + S3 AP の同時参照

> 🌐 **Language / 言語**: 日本語 | [English](../en/dual-access-demo-script.md)

> 同一ファイルが NFS マウントと S3 AP の両方から同時に見えることを示します（本パターンの中核的な価値）。

## 前提条件

- FSx for ONTAP ボリュームを NFS マウントした EC2 インスタンス
- ポータルに設定済みの S3 AP エイリアス

## デモスクリプト（tmux 分割ペイン）

```bash
#!/bin/bash
# dual-access-demo.sh — Split terminal showing NFS + S3 AP access to same file

# Start tmux session with two panes
tmux new-session -d -s demo

# Left pane: NFS access
tmux send-keys -t demo "echo '=== NFS Mount ===' && ls -la /mnt/fsxn/contracts/ && echo '---' && cat /mnt/fsxn/contracts/sample.txt" Enter

# Right pane: S3 AP access
tmux split-window -h -t demo
tmux send-keys -t demo "echo '=== S3 AP Access ===' && aws s3api list-objects-v2 --bucket <s3ap-alias> --prefix contracts/ --max-items 5 && echo '---' && aws s3api get-object --bucket <s3ap-alias> --key contracts/sample.txt /dev/stdout" Enter

tmux attach -t demo
```

## 見せるポイント

1. **同一ファイルを 2 つのプロトコルで**: `contracts/sample.txt` が NFS の `cat` と S3 AP の `get-object` の両方から参照できます
2. **リアルタイム同期**: NFS で書き込むと即座に S3 AP から参照できます（同期の遅延なし）
3. **ポータル表示**: ブラウザでファイルポータルを開き、同じ `contracts/` フォルダを表示します

## 説明の要点

- 「データのコピーも、同期エージェントも、ETL パイプラインも不要です」
- 「既存の NFS/SMB クライアントは変更なしでそのまま動作します」
- 「S3 AP が AI/Lambda 向けのプログラマティックなアクセス層を提供します」
- 「両方のアクセス経路を同一の ONTAP 権限が制御します」

## スクリーンショットの撮り方

以下の構成でスクリーンショットを撮影します。

- 左: `ls /mnt/fsxn/contracts/` を実行したターミナル
- 右: 同じ `contracts/` ディレクトリを表示したポータルのファイルエクスプローラー
- キャプション: 「同一のデータに 2 つのアクセス経路。ワークステーションには NFS、AI 処理には S3 AP」
