# AD参加SVM: S3 Access Point 前提条件

> AD参加SVM（CIFS有効）で FSx for ONTAP S3 Access Points を使用する際の前提条件と運用ガイダンス。

## エグゼクティブサマリ

AD参加SVM では、全ての S3 Access Point データ操作に Active Directory Domain Controller (AD DC) への接続が必須。AD DC に到達不能な場合、ListObjectsV2/GetObject/PutObject は `AccessDenied` で失敗する（HeadBucket は成功 = 偽陽性）。本ドキュメントでは前提条件、推奨アーキテクチャパターン、トラブルシューティング手順を説明する。

---

## 目次

1. [AD DC 到達性要件](#ad-dc-到達性要件)
2. [Internet-Origin AP + VPC外Lambda パターン](#internet-origin-ap--vpc外lambda-パターン)
3. [同一アカウント AP リソースポリシー](#同一アカウント-ap-リソースポリシー)
4. [Pre-Flight ヘルスチェック](#pre-flight-ヘルスチェック)
5. [トラブルシューティング](#トラブルシューティング)
6. [FAQ](#faq)
7. [関連ドキュメント](#関連ドキュメント)

---

## AD DC 到達性要件

### AD DC が必要な理由

AD参加SVM（CIFS有効）では、ONTAP のマルチプロトコル ID パイプラインが全ての S3 AP データ操作で `unix→win` 逆引き name-mapping lookup を実行する。この lookup には SVM から AD DC への LDAP/Kerberos 接続が必要。

以下の状況でも AD DC 接続が必要:
- UNIX セキュリティスタイルのボリューム
- UNIX FileSystemUserType の S3 AP
- SMB 共有が構成されていないボリューム

唯一の条件は SVM で CIFS が**有効化**されていること。

### 診断パターン

| 操作 | AD DC 到達可能 | AD DC 到達不能 |
|------|:---:|:---:|
| HeadBucket | ✅ | ✅ (偽陽性) |
| ListObjectsV2 | ✅ | ❌ AccessDenied |
| GetObject | ✅ | ❌ AccessDenied |
| PutObject | ✅ | ❌ AccessDenied |

> **セキュリティに関する補足**: HeadBucket は S3 メタデータ層（AP の存在と IAM）のみを検証する。ONTAP ファイルシステム層は通過しない。このため、AD参加SVM での S3 AP データプレーン準備状態のヘルスチェックとしては信頼できない。

### 必要なネットワーク接続

SVM ENI から AD DC IP への以下のポートが必要:

| ポート | プロトコル | サービス |
|--------|----------|---------|
| 53 | TCP/UDP | DNS |
| 88 | TCP/UDP | Kerberos |
| 389 | TCP/UDP | LDAP |
| 445 | TCP | SMB/CIFS |
| 636 | TCP | LDAPS |

FSx for ONTAP の preferred/standby サブネットのセキュリティグループで、AD DC IP への上記ポートのアウトバウンドトラフィックを許可すること。

---

## Internet-Origin AP + VPC外Lambda パターン

### 使用ケース

S3 AP **データアクセス**（ListObjectsV2, GetObject, PutObject）を Lambda から行う場合:

- **Internet-origin AP** (`NetworkOrigin: Internet`, `VpcConfiguration` なし)
- **VPC外 Lambda** (Lambda に `VpcConfig` を設定しない)

### VPC-Origin を使わない理由

VPC-origin AP には S3 Gateway または Interface VPC Endpoint が必要。しかし:

1. S3 **Gateway** VPC Endpoint は Internet-origin の S3 Access Points をサポート**しない**
2. S3 **Interface** VPC Endpoint はコスト増（各 AZ ~$7.20/月）と複雑化を伴う
3. VPC 内 Lambda から Internet-origin S3 AP にアクセスするには NAT Gateway が必要

最もシンプルかつコスト効率の高いパターンは、VPC外 Lambda から Internet-origin S3 AP を直接呼び出すこと。

### アーキテクチャ

```
┌─────────────────────┐       ┌──────────────────┐       ┌─────────────────────┐
│ Lambda (VPC外)      │──────▶│ S3 AP (Internet) │──────▶│ FSx for ONTAP Vol   │
│ IAM: s3:GetObject   │       │ NetworkOrigin:   │       │ (ONTAP ファイル      │
│      s3:ListBucket  │       │   Internet       │       │  システム層認証)      │
└─────────────────────┘       └──────────────────┘       └─────────────────────┘
```

### VPC 分割アーキテクチャ

ONTAP REST API アクセス（管理 LIF は VPC 内）も必要な場合:

| Lambda | アクセス先 | VpcConfig |
|--------|-----------|-----------|
| Discovery/ONTAP管理 Lambda | ONTAP REST API (`/api/...`) | ✅ VPC サブネット + SG |
| S3 AP データ Lambda | S3 AP (ListObjectsV2/GetObject/PutObject) | ❌ VPC なし |

> **コストに関する補足**: ONTAP 管理 API と Internet-origin S3 AP アクセスを単一の Lambda で混在させないこと。VPC内 Lambda から Internet-origin S3 AP にアクセスするには NAT Gateway（$32+/月）が必要になる。

---

## 同一アカウント AP リソースポリシー

### 重要な知見

**同一アカウント**アクセス（呼び出し元 IAM プリンシパルと S3 Access Point が同一 AWS アカウント内）の場合、明示的な S3 Access Point リソースポリシー (`put_access_point_policy`) は**不要**。

IAM アイデンティティポリシーのみで十分:

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:ListBucket",
    "s3:GetObject",
    "s3:PutObject"
  ],
  "Resource": [
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-access-point",
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-access-point/object/*"
  ]
}
```

### AP リソースポリシーが必要なケース

- **クロスアカウントアクセス** — 呼び出し元 IAM プリンシパルが別の AWS アカウント
- **条件キー制約** — `aws:PrincipalAccount`, `s3:DataAccessPointAccount` 等
- **IAM を超える制約** — IAM が許可していても特定プリンシパルを拒否する場合

### CloudFormation 例（同一アカウント、AP ポリシー不要）

```yaml
S3ApDataReaderRole:
  Type: AWS::IAM::Role
  Properties:
    Policies:
      - PolicyName: S3ApAccess
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - s3:ListBucket
                - s3:GetObject
              Resource:
                - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3ApName}"
                - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3ApName}/object/*"
```

---

## Pre-Flight ヘルスチェック

### プログラムチェック（Python — Lambda/Step Functions 用）

```python
from shared.ad_health_check import require_ad_dc_reachability
from shared.ontap_client import OntapClient, OntapClientConfig

# ONTAP クライアント初期化
config = OntapClientConfig(management_ip="10.0.1.100", secret_name="fsxn/admin")
client = OntapClient(config)

# AD DC 到達不能時は AdDcUnreachableError を raise
status = require_ad_dc_reachability(client, svm_name="svm1")
# status.is_ad_joined, status.dc_reachable, status.discovered_servers
```

### シェルチェック（スクリプト/自動化用）

```bash
# ONTAP REST API で AD DC 検出状態を確認
curl -sku "$USER:$PASS" \
  "https://$MGMT_IP/api/protocols/cifs/domains?svm.name=$SVM&fields=discovered_servers" \
  | jq '.records[0].discovered_servers | length'
# 結果: 0 = AD DC 到達不能, >0 = 正常
```

### Step Functions 統合

AD参加SVM で S3 AP データ操作を使うワークフローの**最初の状態**に AD DC チェックを追加:

```json
{
  "StartAt": "AdDcHealthCheck",
  "States": {
    "AdDcHealthCheck": {
      "Type": "Task",
      "Resource": "${AdDcHealthCheckFunctionArn}",
      "Next": "MainWorkflow",
      "Retry": [{"ErrorEquals": ["States.TaskFailed"], "MaxAttempts": 2, "IntervalSeconds": 30}],
      "Catch": [{"ErrorEquals": ["AdDcUnreachableError"], "Next": "NotifyAdFailure"}]
    }
  }
}
```

---

## トラブルシューティング

### 症状: ListObjectsV2 で AccessDenied だが HeadBucket は成功

**根本原因**: SVM から AD DC に到達不能。

**確認方法**:
```bash
curl -sku user:pass \
  "https://<mgmt-ip>/api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers"
```

`discovered_servers` が `[]`（空配列）の場合、AD DC に到達不能。

**解決策**:
1. SVM DNS IP がアクティブな AD DC アドレスを指しているか確認
2. セキュリティグループが SVM ENI サブネットからポート 53/88/389/445/636 を許可しているか確認
3. AWS Managed AD の場合、ディレクトリのステータスが `Active` か確認
4. AD を再作成した場合、SVM は CIFS force-delete + re-join が必要（新しい NetBIOS 名が必要）

### 症状: WINDOWS タイプの S3 AP 作成が失敗

**根本原因**: SVM がまだ AD に参加していない。

**解決策**: まず `scripts/demo-ad-join-svm.sh --stack-name <stack>` を実行。

### 症状: 正しい IAM ポリシーなのに AccessDenied

**チェックリスト**:
1. IAM ARN が S3 AP 形式: `arn:aws:s3:<region>:<account>:accesspoint/<name>/object/*`
2. `WindowsUser.Name` はユーザー名のみ（`DOMAIN\` プレフィックスなし）
3. AD DC に到達可能（上記参照）
4. ファイルシステム ID に対象パスへの適切な NTFS/UNIX パーミッションがある

---

## FAQ

### Q: 純粋な UNIX SVM（CIFS なし）に AD DC は必要？

不要。SVM に CIFS サービスが有効化されていなければ、S3 AP 操作に AD は不要。`unix→win` 逆引き lookup は CIFS が構成されている場合にのみ発生する。

### Q: HeadBucket をヘルスチェックに使える？

使えない。HeadBucket は S3 層メタデータのみを検証する。AD DC ステータスに関係なく常に成功する。データプレーンのヘルスチェックには `MaxKeys=1` の ListObjectsV2、または ONTAP API `/protocols/cifs/domains?fields=discovered_servers` を使用すること。

### Q: 同一アカウントアクセスに `put_access_point_policy` は必要？

不要。同一アカウントアクセスでは、呼び出し元ロールの IAM アイデンティティポリシーで十分。明示的な AP リソースポリシーはクロスアカウントアクセスまたは条件キー制約の場合のみ必要。

### Q: Internet-origin S3 AP が VPC Lambda から動作しない理由は？

VPC Lambda のトラフィックは VPC ネットワーキングを経由する。Internet-origin S3 AP トラフィックは S3 Gateway VPC Endpoint を通過**しない**。Lambda には NAT Gateway（コスト高）が必要か、VpcConfig なし（VPC外）で構成する必要がある。

### Q: ワークフロー実行中に AD DC が到達不能になった場合は？

S3 AP データ操作は即座に AccessDenied で失敗する。Step Functions ワークフローには、バックオフ付き Retry（AD DC が一時的に利用不能な場合）と `AdDcUnreachableError` の Catch（オペレーターへのアラート）を含めるべき。

---

## 関連ドキュメント

- [ONTAP Integration Notes](../ontap-integration-notes.md) — NAS 共存、ID マッピング
- [S3AP Compatibility Notes](../s3ap-compatibility-notes.md) — 既知の制約
- [S3AP Authorization Model](../s3ap-authorization-model.md) — 二層認証モデル
- [Incident Response Playbook](../incident-response-playbook.md) — セキュリティインシデント対応
- [ROADMAP](../../ROADMAP.md) — SnapMirror DR テスト自動化（将来）
- Global Steering: `~/.kiro/steering/global-fsx-ontap-ad-integration.md` — 完全な検証済みパターン
