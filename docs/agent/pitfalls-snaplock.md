# SnapLock / Tamperproof の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-snaplock.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| Tamperproof 有効化 → 無効化できない | `snapshot_locking_enabled` は不可逆（400 Bad Request）。ただしポリシーの retention_period 削除で新規ロック停止は可能。詳細は [docs/tamperproof-snapshot-design.md](../tamperproof-snapshot-design.md) |
| Tamperproof 有効化 ≠ 全 Snapshot 自動ロック | 有効化は「ロック機能 ON」であり「自動ロック」ではない。ポリシーに retention_period を設定して初めて自動ロックが発動 |
| SnapLock 監査ログボリュームを作成 → ファイルシステムが最短 6 か月削除できない | 未満了の監査ログはボリューム → SVM → **ファイルシステム**の削除を連鎖ブロックする。保持期間満了前の削除はアカウント閉鎖以外に経路がない（AWS サポートでも不可）。**検証用ファイルシステムに作らない**。確認事項は [docs/tamperproof-snapshot-design.md](../tamperproof-snapshot-design.md) の事前チェック |
| `CreateSnaplockConfiguration` の `RetentionPeriod` で監査ログ保持期間は縛れない | `RetentionPeriod` はボリューム上の WORM ファイル用。監査ログ側の保持期間を指定するフィールドは AWS API に**存在しない**（6 フィールドのみ）。AWS API だけで作ると既定の 6 か月が適用される。明示指定は ONTAP CLI の `snaplock log create -retention-period` のみ |
| `DescribeVolumes` が `AuditLogVolume: False` → 削除できるはず、と読める | 読めない。SVM レベルの監査ログ指定を解除しても ONTAP の `snaplock.is_audit_log` は読み取り専用で解除できず（`PATCH` は 262196 で拒否）、削除可否は変わらない。判断は ONTAP の `snaplock.is_audit_log` と `snaplock.expiry_time` で行う |
| `DeleteVolume` がエラーを返さないのに削除されない | 未満了 WORM / 監査ログがある場合、`DELETING` に遷移後、無言で `CREATED` に復帰する。`BypassSnaplockEnterpriseRetention=true` / `SkipFinalBackup=true` を付けても同じ。レスポンスではなく数十秒後の `Lifecycle` で判定する |
| SnapLock 種別を後から変更・解除しようとする | 不可。`snaplock.type` は**作成時のみ**。`compliance` ⇄ `enterprise` の変更も、SnapLock の解除もできない。`PrivilegedDelete=PERMANENTLY_DISABLED` も終端状態（設定すると `enterprise` が `compliance` 相当になる） |
