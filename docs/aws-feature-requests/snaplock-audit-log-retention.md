# 機能要望: FSx for ONTAP の SnapLock 監査ログボリュームにおける保持期間の指定と削除ロックの可視化

> 🌐 **Language / 言語**: 日本語 | [English](snaplock-audit-log-retention.en.md)

**提出者**: 藤原 慶樹 (AWS Community Builder)
**日付**: 2026-08-06
**プロジェクト**: [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
**コンテキスト**: 検証環境で SnapLock 監査ログボリュームを作成した結果、ファイルシステム全体が最短 6 か月削除できなくなった事象からの改善要望
**ステータス**: 📋 起票済み・回答待ち（一部回答受領）
**関連**: [Tamperproof Snapshot 設計ガイド](../tamperproof-snapshot-design.md) / [FR-1〜FR-4（既提出）](./fsxn-s3ap-improvements.md)

> **要望番号について**: 本ドキュメントは SnapLock スコープのため `SL-1`〜`SL-3` を用います。`FR-5`〜`FR-10` の番号は別スコープの 2 ドキュメントで先に使われています。

---

## エグゼクティブサマリー

**結論: AWS API のみを使う利用者は、SnapLock 監査ログボリュームの保持期間を選べないまま、ファイルシステム全体に対する最短 6 か月の削除ロックを受け入れることになります。**

保持期間そのものが長いことは、不変性を保証する仕組みとして妥当です。要望はロックの緩和ではなく、**ロックが発生することを操作前に知る手段**と、**保持期間を選ぶ手段**です。

| # | 要望 | 性質 |
|---|---|---|
| SL-1 | `CreateSnaplockConfiguration` に監査ログ保持期間のパラメータを追加、または適用される既定値と削除ロックの範囲を API / コンソールで明示 | 機能追加 |
| SL-2 | 未満了の WORM / 監査ログにより削除できない場合、`DeleteVolume` がエラーを返す（現状は無言で復帰） | 挙動修正 |
| SL-3 | `DescribeVolumes` の `AuditLogVolume` を ONTAP の実態と一致させる、または削除可否を判定できるフィールドを追加 | 挙動修正 |

AWS サポートからは、依頼した「保持期間満了前の削除」および「ファイルシステムの削除ロック解除」はいずれも**不可**、かつ**アカウント閉鎖以外の経路は存在しない**との回答を得ています。したがって本件は事後救済の余地がなく、事前の可視化のみが対策になります。

---

## 発生した事象

検証目的で SnapLock ENTERPRISE ボリュームを作成し、同じ SVM に SnapLock 監査ログボリュームを作成しました。保持期間は明示していません（AWS API に指定手段がないため）。結果として既定の 6 か月が適用され、以下がすべて削除できなくなりました。

```
未満了の監査ログ（保持期間 6 か月）
        ↓ ブロック
   監査ログボリューム        ← DELETE が失敗（ONTAP エラー 525057）
        ↓ ブロック
   SVM
        ↓ ブロック
   ファイルシステム          ← 満了まで課金が継続
```

このファイルシステムには検証用の他ボリュームも載っており、それらも移動・削除できません。

### 試行した手段と結果

| 手段 | 結果 |
|---|---|
| `DeleteVolume` | `DELETING` に遷移後、**エラーを返さず** `CREATED` に復帰 |
| `DeleteVolume` + `BypassSnaplockEnterpriseRetention=true` | 同上（効果なし） |
| `DeleteVolume` + `SkipFinalBackup=true` | 同上 |
| `UpdateVolume` で `AuditLogVolume=false` | 適用されない |
| ONTAP `DELETE /api/storage/snaplock/audit-logs/{svm.uuid}`（マウント状態） | 失敗（13763189: アンマウントが必要） |
| ONTAP `PATCH` で `nas.path=""` によりアンマウント | 成功 |
| ONTAP `DELETE /api/storage/snaplock/audit-logs/{svm.uuid}`（再試行） | 成功（SVM レベルの指定は解除） |
| ONTAP `PATCH` で `snaplock.is_audit_log=false` | 拒否（262196: 読み取り専用） |
| ONTAP `DELETE /api/storage/volumes/{uuid}`（オフライン後） | 失敗（525057: 未満了の SnapLock Enterprise 監査ログ） |

---

## SL-1: 監査ログ保持期間を指定する手段

### 現状

`CreateSnaplockConfiguration` のフィールドは以下の 6 つで、**監査ログの保持期間を指定するものはありません**。

| フィールド | 何を縛るか |
|---|---|
| `SnaplockType` | ボリュームの種別（`COMPLIANCE` / `ENTERPRISE`） |
| `AuditLogVolume` | このボリュームを監査ログボリュームにするか |
| `AutocommitPeriod` | 未変更ファイルが WORM に移行するまでの時間 |
| `PrivilegedDelete` | 特権削除の可否（`PERMANENTLY_DISABLED` は終端状態） |
| `RetentionPeriod` | **ボリューム上の WORM ファイル**の保持期間 |
| `VolumeAppendModeEnabled` | 追記モード |

`RetentionPeriod` は WORM ファイル用であり、監査ログの保持期間ではありません。両者は別のパラメータで、片方を最小にしても他方には影響しません。実際に本件では `RetentionPeriod` は `Default 0 YEARS` / `Minimum 0 YEARS`（最小）でしたが、監査ログ側に既定の 6 か月が適用され削除ロックが発生しました。

監査ログの保持期間は ONTAP CLI の `snaplock log create -retention-period` でのみ指定できます。

### 本プロジェクトへの影響

本プロジェクトは AWS API と CloudFormation を前提としたリファレンス実装を提供しています。`AuditLogVolume=true` を使うパターンを提示すると、利用者は保持期間を選べないまま 6 か月の削除ロックを受け入れることになります。そのため現状はポータル UI から監査ログボリュームを作成できないようにしており、必要な場合は ONTAP CLI を案内しています。AWS ネイティブな経路で完結できない状態です。

### 要望する挙動

以下のいずれか。

1. `CreateSnaplockConfiguration` に監査ログ保持期間を指定するパラメータを追加する。
2. 追加が難しい場合、`AuditLogVolume=true` を指定した際に、**適用される保持期間の既定値**と、**その期間中はボリューム・SVM・ファイルシステムが削除できないこと**を、API レスポンス、コンソール、および `CreateVolume` のドキュメントで明示する。

2 は既定値を変えないため後方互換で、可視化のみで再発を防げます。

### 検証していない点

6 か月より短い値が実際に拒否されるかは検証していません。ドキュメント記載に基づく理解です。検証には監査ログボリュームをもう 1 本作成する必要があり、同じ削除ロックを増やすため実施していません。

---

## SL-2: 削除できない場合にエラーを返す

### 現状

未満了の WORM ファイルまたは監査ログがあるボリュームに対する `DeleteVolume` は、**エラーを返しません**。`Lifecycle` が `DELETING` に遷移し、数十秒後に `CREATED` へ戻ります。`BypassSnaplockEnterpriseRetention=true` や `SkipFinalBackup=true` を付けても同じです。

同じ操作を ONTAP REST API で行うと、理由が明記されたエラーが返ります（525057）。情報は下層に存在しており、AWS API 層で失われています。

### 本プロジェクトへの影響

自動化・IaC・エージェントによる操作では、レスポンスの成否で分岐します。エラーが返らないため「削除に成功した」と解釈され、次のステップ（SVM 削除、ファイルシステム削除）へ進み、そこでも同様に失敗します。`Lifecycle` をポーリングして初めて失敗が判明しますが、それを知らなければフラグを増やして再試行する方向に進みます。

### 要望する挙動

削除が保持期間により拒否される場合、`DeleteVolume` が失敗を返し、理由（未満了の WORM ファイル / 未満了の監査ログ / リーガルホールド）と `expiry_time` をメッセージに含めること。ONTAP が返している情報をそのまま伝えるだけで足ります。

---

## SL-3: `AuditLogVolume` の表示と実態の一致

### 現状

SVM レベルの監査ログ指定を ONTAP REST API で解除すると、AWS API の `DescribeVolumes` は `AuditLogVolume: False` を返すようになります。しかしボリューム側の `snaplock.is_audit_log` は読み取り専用で解除できず（`PATCH` は 262196 で拒否）、**削除可否は変わりません**。

本記述時点でも、当該ボリュームは `AuditLogVolume: False` かつ削除不可の状態です。

### 本プロジェクトへの影響

AWS API のみを参照する利用者には「監査ログボリュームではなくなった = 削除できるはず」と読めます。実際の削除可否は変わっていないため、原因の切り分けが AWS API 層では完結せず、ONTAP REST API へのアクセスが必要になります。ポータルのような AWS API ベースのツールでは、この不一致をそのまま画面に出すと誤解を生みます。

### 要望する挙動

以下のいずれか。

1. `AuditLogVolume` が ONTAP の `snaplock.is_audit_log` と一致するようにする。
2. 一致させることが難しい場合、削除可否を判定できるフィールド（例: `SnaplockConfiguration.ExpiryTime`、あるいは削除がブロックされている理由）を `DescribeVolumes` に追加する。

---

## AWS サポートによる確認結果（2026-08）

| 依頼 | 回答 |
|---|---|
| 保持期間満了前に監査ログボリュームを削除できるか | **不可**（社内確認済み） |
| ファイルシステムの削除ロックのみ解除できるか | **不可** |
| アカウント閉鎖以外の経路が存在するか | **存在しない**（明示回答） |

SL-1〜SL-3 に相当する要望およびその他の確認事項は、継続確認中です。

---

## 関連ドキュメント

- [Tamperproof Snapshot 設計ガイド](../tamperproof-snapshot-design.md) — SnapLock ボリュームと Snapshot ロックの区別、事前チェック
- [FR-1〜FR-4（既提出）](./fsxn-s3ap-improvements.md) — FSx for ONTAP S3 AP コア機能
- [Lambda / HealthOmics 統合ギャップ](./lambda-healthomics-s3ap-gaps.md) — 別スコープの要望
