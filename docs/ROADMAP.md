# Roadmap

プロジェクト全体の残課題と今後の方向性を管理するファイルです。

*Last updated: 2026-08-06*

> 完了した作業の履歴は git とマージ済み PR にあります。このファイルは **未完了のものだけ** を持ちます。

---

## 🎯 Next Priority — AWS 実機検証バックログ

コードとテンプレートは揃っているが、AWS 上での動作確認が済んでいないパターン群。ここが最優先です。

| UC Group | Status | Remaining Work |
|---|---|---|
| UC1, UC3, UC6-UC14 | ✅ E2E 検証済み | — |
| UC2, UC4, UC5 | ✅ デプロイ + コンポーネント確認済み | テストデータでのフル E2E |
| UC15-UC17 (Public Sector) | ⚠️ コード完成 | AWS デプロイ + E2E 検証 |
| UC18-UC28 | ⚠️ テンプレート + テスト完成 | AWS デプロイ + 主要コンポーネント検証 |
| OPS1-OPS6 | ⚠️ テンプレート + テスト完成 | AWS デプロイ + E2E 検証 |

検証時のコスト注意点は [cost-calculator.md](cost-calculator.md)、`DemoMode=true` で FSx for ONTAP なしに動かす手順は [demo-mode-guide.md](demo-mode-guide.md) を参照。

### このファイルは撤去の判断材料でもある

`make propose-cleanup` はこのファイルの未完了マーカー（📋 / ⚠️）を読み、**1 つでも残っている
間はクリーンアップを提案しません**。全部消えたら、稼働中のリソースと Price List API で引いた
月額、撤去順の提案を出します。読み取り専用で、削除は一切しません（削除は
`scripts/cleanup_generic_ucs.py` と `scripts/teardown-uc29-uc30.sh`）。

```bash
make propose-cleanup                    # 残課題を出して、あれば提案は保留
make propose-cleanup ARGS="--anyway"    # 残課題があっても棚卸しだけ見る
```

つまり**このファイルを更新しないと撤去の判断ができません**。項目が終わったら ✅ にすること。

> **撤去に関する既知のブロッカー**: 検証用ファイルシステムの一方に SnapLock ENTERPRISE
> ボリューム（`PrivilegedDelete=PERMANENTLY_DISABLED`）が 1 本あります。この終端状態は
> ENTERPRISE を COMPLIANCE 相当にするため、privileged delete も残っていません。削除可否は
> FSx API の `AuditLogVolume` ではなく ONTAP の `snaplock.is_audit_log` と
> `snaplock.expiry_time` で判断します。詳細は
> [tamperproof-snapshot-design.md](tamperproof-snapshot-design.md)。

---

## 🔬 実機で確認できていない挙動

パターン単位のデプロイとは別に、**設計判断の根拠になるのに実測がない**もの。ここに書いていない
未検証事項は `make propose-cleanup` のゲートに乗らないため、撤去判断から漏れます。

| # | 項目 | 状態 | 必要なもの |
|---|---|---|---|
| V-1 | 本番相当負荷でのスループット共有（NFS / SMB / S3 AP の同時アクセス） | 📋 未実測 | 負荷生成環境。[s3ap-performance-considerations.md](s3ap-performance-considerations.md) の設計指針の裏付け |
| V-2 | マルチテナント S3 AP ルーティング（テナントごとの AP と認可の分離） | 📋 未実測 | 複数 SVM / 複数 AP |
| V-3 | 外部 IdP（SAML / OIDC）と Cognito の連携 | 📋 未実測 | IdP テナント。ガイドは概要のみ |
| V-4 | SnapMirror による DR フェイルオーバー | 📋 未実測 | **破壊的**。専用の検証用ファイルシステムで行う |
| V-5 | AD 参加 SVM への S3 AP データ操作 | ⚠️ 一部実測（2026-08-11） | 下記 |

V-5 の実測済みの範囲: WINDOWS タイプ Internet-origin AP に対する HeadBucket / ListObjectsV2 /
PutObject / GetObject / HeadObject / DeleteObject が VPC 外から成功すること、および **FSx API の
`ActiveDirectoryConfiguration` が判定に使えないこと**（`null` でもデータ操作は通る）。
未実測: AD DC 到達不能時の症状の再現（ONTAP 管理 LIF がプライベートなため VPC 内からの実行が必要）。
記録は [ad-joined-svm-s3ap-prerequisites.md](ja/ad-joined-svm-s3ap-prerequisites.md)。

---

## 📝 AWS Feature Requests

| Document | Scope | FRs | Status |
|---|---|---|---|
| [`fsxn-s3ap-improvements.md`](aws-feature-requests/fsxn-s3ap-improvements.md) | FSx for ONTAP S3 AP core | FR-1 to FR-4 | ✅ Submitted 2026-05-10 |
| [`file-portal-service-gap.md`](aws-feature-requests/file-portal-service-gap.md) | File Portal UI + SaaS gap | FR-5 to FR-10 | 📋 Draft |
| [`lambda-healthomics-s3ap-gaps.md`](aws-feature-requests/lambda-healthomics-s3ap-gaps.md) | Lambda / HealthOmics 統合 | FR-5 to FR-7 | 📋 Draft |
| [`snaplock-audit-log-retention.md`](aws-feature-requests/snaplock-audit-log-retention.md) | SnapLock 監査ログの保持期間と削除ロック | SL-1 to SL-3 | 📋 起票済み・一部回答受領 |

**Priority chain**: FR-7 (Presigned URL) → FR-5 (Storage Browser for S3) → FR-6 (Amplify Storage)。

FR-7 について: Presigned URL は互換性表では "Not supported" だが実測では動作し、AWS Support も ONTAP 側の対応（v4 は 9.11.1 以降、v2 は 9.16.1 以降）を確認してドキュメント修正を提出済み。**未公開**のため、本番前提での依存は引き続き避ける。詳細は [s3ap-compatibility-notes.md](s3ap-compatibility-notes.md)。

**Next actions**:

- FR-5/6/7 を re:Post とサポートケースで提出
- `aws-amplify/amplify-ui`（Storage Browser + S3 AP）と `aws-amplify/amplify-backend`（Storage category + S3 AP）に issue 起票

---

## 🖥️ File Portal UI — Remaining

| Item | Priority | Notes |
|---|---|---|
| FlexCache/SnapMirror のスクリーンショット + デモガイド追記 | Medium | `docs/en/admin-resource-management-demo.md` に手順追加 |
| SAML/OIDC Cognito 連携ガイド | Low | Hosting ガイドに概要のみ記載済み |
| モバイル向け CSS の調整 | Low | 基本的なレスポンシブは動作、実機確認が必要 |

データ取得は全パネルが TanStack Query に移行済み。`react-hooks/set-state-in-effect` と `react-hooks/exhaustive-deps` は `error` に昇格し、`npm run lint` は `--max-warnings 0` です。

---

## 🌐 Other Repositories README Redesign

ハブ&スポーク型 README を他の公開リポジトリにも適用する。

| Repository | Status |
|---|---|
| `fsxn-lakehouse-integrations` | 📋 Prompt ready |
| `fsxn-observability-integrations` | 📋 Prompt ready |
| `fsxn-cyber-resilience-patterns` | 📋 Prompt ready |
| `ontap-edge-to-cloud-ai` | 📋 Prompt ready |
| `vmware-migration-ec2-ontap` | 📋 Prompt ready |
| `blea-fsxn-usecase` | 📋 Prompt ready |
| `FSx-for-ONTAP-Agentic-Access-Aware-RAG` | 📋 Prompt ready |

---

## 🏗️ Infrastructure & CI

| Item | Status |
|---|---|
| Nextcloud test CI | 📋 CI 未組み込み（Docker ベース、ローカルのみ） |
| KNFSD File Cache | 📋 Preview、統合テストはローカル実行のみ |

Renovate は稼働中（アカウント単位でインストール済み、2026-07 から PR を自動作成・マージ）。メジャーバージョンは Dependency Dashboard での承認待ちになるため、`Pending Approval` が並んでいるのは正常な状態です。

---

## 📚 Published Articles

Part 1〜3 は日本語（Hatena）と英語（dev.to）とも公開済み。公開後に制約が解消された場合、記事側が古いままになるため `make drift-published` で検出します（ネットワークが必要なため PR ゲートではありません）。

| Item | Status |
|---|---|
| Part 4 以降の構成検討 | 📋 未着手 |

---

## 📐 Design Principles (enforced)

`AGENTS.md` の "Documentation Design Principles" で明文化:

- Hub & Spoke README モデル
- Progressive Disclosure (`<details>`)
- Action-First の見出し
- 7±2 ルール
- 多言語のミラー構造
- No dead weight（Phase 履歴やインラインスクリーンショットを置かない）
