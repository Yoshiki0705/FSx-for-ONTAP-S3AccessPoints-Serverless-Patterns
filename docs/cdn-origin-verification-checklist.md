# ORIGIN_PULL SigV4 × S3 AP alias 実機検証チェックリスト

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## 目的

[CDN比較ドキュメント](cdn-comparison.md) で **要検証 (TBV)** とした項目、すなわち
**「各 CDN の SigV4 オリジン署名が FSx for ONTAP S3 Access Point の `accesspoint alias` ホストに対して
標準 S3 バケットと同様に機能するか」** を実機で確定するための再現可能な検証手順です。

本チェックリストは `solutions/edge/content-delivery` UC の `DeliveryMode=ORIGIN_PULL`（M1/M2）の採否判断に使います。
**M3（PUBLISH_PUSH）はこの検証に依存しません**（オリジン認証を回避するため）。

> **区別の明示**: 本検証は「特定テスト環境での実測」です。一般的な S3 の挙動や各 CDN の標準バケットでの
> 実績を、S3 AP alias での保証として扱わないこと。

---

## 0. 前提条件

- FSx for ONTAP ファイルシステムと **Internet-origin** の S3 Access Point（VPC-origin は CDN 不可）
- S3 AP alias（例: `<alias>-ext-s3alias`）と対象リージョン
- 配信検証用の **承認済みプレフィックス**配下のテストオブジェクト（例: `delivery-approved/test-1mb.bin`）
  - permission-aware 原則に従い、ACL 制御下のマスターは検証対象にしない
- オリジン署名用の **最小権限 IAM 認証情報**（対象 AP の `s3:GetObject` のみ）。可能なら短期クレデンシャル
- 検証端末（curl 7.75 以降は `--aws-sigv4` 対応）、AWS CLI v2

> **セキュリティ**: 検証中もアクセスキーをログ・スクリーンショット・コミットに残さない。
> 値ではなくキー名で参照する（公開リポジトリ運用ルール準拠）。

---

## 1. ベースライン検証（CDN なし／最重要）

CDN を介さず、**S3 AP alias ホストが SigV4 を受理するか**を直接確認する。ここが全 CDN 共通の核心。

### 1.1 AWS CLI（SDK 署名）

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- 期待: HTTP 200 + オブジェクト取得成功。
- 失敗時: IAM / AP ポリシー / ONTAP 側 ID（UNIX UID / AD）の二段階認可を切り分け。

### 1.2 生 SigV4（CDN のオリジン署名挙動の近似）

CDN は多くの場合、固定アクセスキーで SigV4 署名してオリジンを引く。`curl --aws-sigv4` で同等挙動を近似:

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **これが 200 なら**: alias ホストは標準バケットと同様に SigV4 を受理 → M1/M4 の実現可能性が高い。
- **これが失敗するなら**: alias 固有のアドレッシング差が原因の可能性 → 各 CDN のオリジン設定で
  ホスト形式・リージョン・サービス名（`s3`）・パススタイル/バーチャルホストの扱いを個別検証。
- 一時クレデンシャル使用時は `-H "x-amz-security-token: $AWS_SESSION_TOKEN"` を追加。

### 1.3 ネガティブ確認（仕様の再確認）

- 無署名 GET が **403/AccessDenied** であること（Block Public Access 強制の確認）。
- Presigned URL が利用不可であること（生成不可／利用非対応）→ 視聴者トークンは CDN ネイティブ機構へ。

---

## 2. CDN 別検証手順

各 CDN で「オリジン＝S3 AP alias ホスト」を設定し、キャッシュミス時のオリジンフェッチが 200 になるかを確認する。

### 2.1 Amazon CloudFront（M1 / OAC）— リファレンス

- `solutions/edge/content-delivery` テンプレートで `EnableCloudFront=true` をデプロイ（OAC + `SigningProtocol: sigv4`）。
- 検証: `curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200。
- 期待: AWS 公式チュートリアルに準拠し成立（**実績あり**）。OAC の `OriginAccessControlOriginType: s3`。

### 2.2 Fastly（M1 / SigV4 ネイティブ）

- S3 互換プライベートオリジンとして alias ホストを設定し、SigV4 署名（リージョン・サービス `s3`）を有効化。
- 検証: Fastly サービス経由で対象キーを GET → 200。
- 確認点: alias のバーチャルホスト形式が Fastly の SigV4 実装で正しく署名されるか。

### 2.3 Cloudflare（M2 / Workers 署名）

- Worker で SigV4 を実装し、alias ホストへ署名付きフェッチ（R2 ではなく S3 AP を直接オリジン化する場合）。
- 検証: Worker 経由 GET → 200。署名対象ヘッダ・ペイロードハッシュの扱いを確認。

### 2.4 Akamai（M1 / Cloud Access Manager）

- Cloud Access Manager で AWS 署名方式を設定し、Origin Characteristics で alias ホストを指定。
- 検証: Akamai プロパティ経由 GET → 200。AP alias ホストでの署名適用可否を確認。

### 2.5 Bunny.net（M1 / S3 オリジンプル）

- Pull Zone のオリジンを AWS S3 オリジン種別で alias ホストに設定。
- 検証: Pull Zone 経由 GET → 200。

### 2.6 Google Cloud CDN / Media CDN（M1 / private S3 origin）

- private S3 互換オリジンの SigV4 認証で alias ホストを設定。
- 検証: Media CDN 経由 GET → 200。クロスクラウド egress 経路も確認。

---

## 3. 合否基準

| 判定 | 条件 |
|------|------|
| **PASS** | ベースライン 1.2 が 200 かつ 当該 CDN 経由のキャッシュミス GET が 200。視聴者トークンが CDN ネイティブ機構で機能 |
| **CONDITIONAL** | CDN 経由は 200 だが、追加設定（パススタイル等）や制約（特定ヘッダ）が必要 |
| **FAIL** | alias ホストへの SigV4 が当該 CDN で成立せず、回避策（M2 署名実装／M4 署名プロキシ／M3 へ切替）が必要 |
| **BLOCKED** | 前提（Internet-origin、IAM、テストオブジェクト）が未整備で検証不能 |

---

## 4. 検証時のセキュリティ／ガバナンス確認

- [ ] テストオブジェクトは `delivery-approved/` 配下のみ（ACL 制御マスターを使わない）
- [ ] オリジン署名用 IAM は対象 AP の `s3:GetObject` 最小権限
- [ ] 長期キーをエッジ/設定に残さない（短期クレデンシャル優先、検証後に失効）
- [ ] アクセスキー・alias 実値・アカウント ID をログ／スクショ／コミットに残さない
- [ ] 視聴者トークンは CDN ネイティブ機構を使用（S3 Presigned URL を使わない）
- [ ] 検証で作成した一時リソース（Distribution、Pull Zone 等）をクリーンアップ

---

## 5. 結果記録テーブル（証跡）

| CDN | メカニズム | 設定完了 | 1.2 ベースライン | CDN 経由 GET | 視聴者トークン | 判定 | 証跡（HTTPステータス/ヘッダ/日時） | 検証日 | 担当ロール |
|-----|-----------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront |  M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> 記録時の注意: alias 実値・アカウント ID・IP はプレースホルダー化（`<alias>-ext-s3alias`, `123456789012`）。
> 検証結果は「特定テスト環境での実測」として扱い、一般的な保証として記載しない。

---

## 6. 検証結果のフィードバック

- 確定した結果は [CDN比較ドキュメント](cdn-comparison.md) 第3節「S3 AP 固有の要検証」列／4.1「要検証」の更新に反映する
  （TBV → 実測結果へ）。
- FAIL の CDN は `solutions/edge/content-delivery` で `DeliveryMode=PUBLISH_PUSH`（M3）を推奨経路とする。

## 関連ドキュメント

- [CDN/エッジ配信統合比較](cdn-comparison.md)
- [content-edge-delivery UC](../solutions/edge/content-delivery/README.md)
- [S3AP 互換性ノート](s3ap-compatibility-notes.md)
