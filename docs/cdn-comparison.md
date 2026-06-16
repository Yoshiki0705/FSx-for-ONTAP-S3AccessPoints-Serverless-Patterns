# CDN/エッジ配信統合比較 — FSx ONTAP S3 Access Points を起点とした配信

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. このドキュメントの位置づけ

FSx for ONTAP の S3 Access Points (以下 S3 AP) 上のデータを、CDN/エッジ配信ネットワーク経由で
配信する際の **技術的な実現可否** を整理した資料です。

本ドキュメントは以下を **目的としません**:

- ベンダー間の優劣比較・推奨
- 性能・価格・カバレッジの定量比較
- マーケティング的な訴求

本ドキュメントが扱うのは **「FSx ONTAP S3 AP の技術制約に対して、各統合メカニズムで何が実現でき、
何が実現できず、何が要検証か」** のみです。配信ベンダーの選定は、顧客の既存契約・SLA・運用体制・
リージョン要件など、本ドキュメントの範囲外の要素を含めて顧客が判断するものです。

---

## 1. 配信可否を決める FSx ONTAP S3 AP の技術制約

CDN 統合の設計は、すべて以下の S3 AP の仕様から導かれます。**ここがすべての出発点**です。

| 制約 | 内容 | 配信設計への影響 |
|------|------|----------------|
| **Block Public Access 強制** | S3 AP は BPA がデフォルトで有効、かつ無効化不可 | 認証なしのパブリックオリジンとして使えない。オリジン認証が必須 |
| **オリジン認証は SigV4（IAM）** | リクエストは IAM/Access Point policy で評価 | CDN はオリジン取得時に AWS SigV4 署名が必要 |
| **二段階認可（AWS 側 + ONTAP 側）** | IAM 認可の後、AP に紐づく ONTAP ファイルシステム ID（UNIX UID / Windows AD）でも認可 | 配信対象は ONTAP 側 ID で読める範囲に限定される |
| **Presigned URL 非対応** | S3 Presigned URL は公式に未サポート | 視聴者向けトークン認証に S3 Presigned URL を使えない。CDN ネイティブのトークン機構を使う |
| **NetworkOrigin（Internet / VPC、作成後変更不可）** | CDN は AWS マネージド/外部網からアクセス | CDN 連携には **Internet origin** が必要。VPC origin はクラウド外 CDN から到達不可 |
| **PutObject 上限 5 GB** | 単一 PUT は 5 GB まで | 配信成果物の書き戻しは大容量時にマルチパート |

> 上記は FSx ONTAP S3 AP の仕様であり、配信ベンダー側の制約ではありません。
> いずれの CDN を使う場合も、この制約の上で設計します。

---

## 2. 統合メカニズム（ベンダー非依存）

S3 AP を配信に繋ぐ方法は、技術的に次の4つに分類できます。

### M1: ネイティブ SigV4 オリジンプル（CDN が S3 AP を直接取得）

```
視聴者 → CDN Edge ──(SigV4 署名)──> S3 AP (Internet origin) → FSx for ONTAP
```

- CDN がキャッシュミス時に AWS SigV4 でオリジン要求に署名する機能を**標準搭載**している場合。
- **実現できること**: データを移動せず、FSx 上の成果物を直接配信。
- **実現できないこと / 要検証**: S3 AP は通常の S3 バケットと **アドレッシング（accesspoint alias ホスト名）が異なる**。
  各 CDN の SigV4 実装が AP alias ホスト + リージョン + `s3` サービス名の組み合わせで正しく署名できるかは
  **実機検証が必要**（標準バケットでの動作実績がそのまま AP に当てはまる保証はない）。

### M2: エッジコンピュートによる SigV4 署名

```
視聴者 → CDN Edge (Worker/Compute で SigV4 署名) → S3 AP → FSx for ONTAP
```

- CDN がオリジン署名を標準搭載しない場合に、エッジ実行環境で SigV4 を自前実装する。
- **実現できること**: 標準オリジン署名がない CDN でも M1 相当を実現。署名ロジックを完全制御できる。
- **実現できないこと / 要検証**: 署名実装・鍵管理・キャッシュキー設計を自前で保守する必要がある。
  エッジに AWS 認証情報をどう供給するか（長期鍵の回避、短期クレデンシャル）が設計課題。

### M3: CDN ネイティブの S3 互換ストアへ配信（Push）

```
FSx for ONTAP ─(S3 AP 読取)→ 処理 ─push→ CDN 側 S3 互換ストア → CDN Edge → 視聴者
```

- FSx をマスターに残し、**配信用に承認・変換した成果物だけ**を CDN 側のオブジェクトストアへ書き出す。
- **実現できること**: S3 AP のオリジン認証問題を**回避**。CDN 非依存。マスターと配信系を物理分離できる。
- **実現できないこと / 要検証**: 配信ストアは FSx のコピーになるため、同期遅延・整合性・二重保管の設計が必要。
  リアルタイム性が要る配信には不向き。

### M4: 自己管理の SigV4 署名プロキシを汎用 HTTP オリジンにする

```
視聴者 → CDN Edge → 署名プロキシ(SigV4付与) → S3 AP → FSx for ONTAP
```

- SigV4 署名もエッジコンピュートも持たない CDN でも、署名を行う中間層（Lambda + Function URL / ALB 等）を
  オリジンに置けば連携できる。
- **実現できること**: ほぼすべての CDN で M1 相当を実現。
- **実現できないこと / 要検証**: 中間層が単一障害点/スケール対象になる。プロキシの可用性設計が必要。

> **共通の絶対制約**: いずれのメカニズムでも、視聴者向けトークン認証に S3 Presigned URL は使えません。
> 視聴者認証は各 CDN ネイティブのトークン/署名 URL 機構で実装します。
> また、公開配信は ONTAP の NFS/SMB ACL を経由しないため、**配信対象は承認済み成果物に限定**します（第4節参照）。

---

## 2.5 性能・スループット観点（Storage 設計）

CDN 連携は FSx for ONTAP の共有スループット設計に影響します。配信メカニズムごとの読み取り負荷特性を
押さえておく必要があります。

| 観点 | ORIGIN_PULL（M1/M2/M4） | PUBLISH_PUSH（M3） |
|------|------------------------|-------------------|
| FSx 読み取り負荷 | キャッシュミス時に発生（継続的） | 初回複製時のみ（定常時はゼロ） |
| キャッシュミス集中（cache stampede） | FSx へ同時オリジンフェッチが集中しうる | 配信ストア側で吸収（FSx 非依存） |
| 業務 NFS/SMB との帯域競合 | あり（S3AP/NFS/SMB は帯域共有） | 初回複製時のみ |
| 大容量メディアの部分取得 | Range GET が有効（CDN→S3 AP の Range 対応に依存） | 配信ストア側の Range 配信に依存 |

### 実現できること / 設計上の留意（事実ベース）

- FSx ONTAP のプロビジョンドスループットは NFS/SMB/S3AP で共有される。ORIGIN_PULL のオリジンフェッチは
  業務ワークロードと帯域を分け合うため、**キャッシュミス率と同時接続数を見積もる**必要がある。
- CDN 側の **Origin Shield / 高 TTL / 階層キャッシュ** によりオリジンフェッチ回数を削減できる（各 CDN の機能）。
- **FlexCache** を用いて配信読み取り用のキャッシュボリュームを業務ボリュームと分離する選択肢がある
  （ONTAP ネイティブ。詳細は FlexCache パターン群を参照）。これは要件・コストに応じた設計判断。
- PUBLISH_PUSH は初回複製後の定常配信で FSx 読み取りを発生させないため、業務ワークロードへの影響が小さい。

> いずれも定量値は FSx 構成（スループットキャパシティ）・ファイルサイズ・キャッシュヒット率に依存するため、
> **本番見積もりは実測に基づくこと**（一般論を特定環境の数値として提示しない）。

## 2.6 コスト観点（定性）

| メカニズム | 主なコスト要素 |
|-----------|--------------|
| ORIGIN_PULL | FSx 読み取り（キャッシュミス分）＋ S3 AP → CDN への AWS データ転送（egress）＋ CDN 配信料 |
| PUBLISH_PUSH | 配信ストアの保管料（承認済みレンディション分）＋ 初回複製の転送＋ CDN 配信料 |

> 上記は **コスト要素の定性整理** であり、金額は構成・トラフィック・各社料金で大きく変動する。
> 具体的な月額は、対象トラフィック量を用いて各社の最新料金で算出すること（サンプル試算と本番見積もりを混同しない）。

---

## 3. 各配信ネットワークのメカニズム対応（事実ベース）

各列は「公開ドキュメントで確認できる事実」と「FSx ONTAP S3 AP に対する要検証点」を分けて記載します。
○ = 公式機能あり / △ = 条件付き・自前実装 / − = 該当機能なし / 要検証 = S3 AP 固有の検証が必要。

| 配信網 | M1 ネイティブ SigV4 プル | M2 エッジ署名 | M3 自社 S3 互換ストア(Push) | 視聴者トークン機構 | S3 AP 固有の要検証 |
|--------|:---:|:---:|:---:|---|---|
| **Amazon CloudFront** | ○ OAC（SigV4） | △ Lambda@Edge / CloudFront Functions | （標準 S3 へ） | CloudFront 署名 URL/Cookie | **実績あり**（AWS 公式チュートリアルが S3 AP+OAC を提示） |
| **Akamai** | ○ Cloud Access Manager（AWS 署名方式） | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | AP alias ホストでの Cloud Access Manager 署名は要検証 |
| **Fastly** | ○ S3 互換プライベートオリジンへ SigV4（`digest.awsv4_hmac`） | △ Compute | ○ Fastly Object Storage | Fastly 署名 URL | AP alias ホストでの SigV4 検証 |
| **Cloudflare** | − 標準プロキシは SigV4 非搭載 | ○ Workers で SigV4 署名 | ○ R2（S3 互換） | Cloudflare 署名 URL | Workers 署名実装 + AP alias 検証 |
| **Bunny.net** | △ S3 オリジンプル対応（AWS S3 オリジン種別） | − | ○ Bunny Storage（S3 互換 API, beta） | Pull Zone トークン認証 | AP alias での署名動作は要検証 |
| **Google Cloud CDN / Media CDN** | ○ private S3 互換オリジンへ SigV4 認証（公式） | △ Media CDN ルーティング | （GCS / 任意 S3 互換） | Media CDN 署名 URL/Cookie | クロスクラウド egress + AP alias 検証 |

### 表に載せない/注記扱いとした配信網

- **Azure Front Door / Azure CDN**: クロスクラウドでのプライベート S3 オリジン認証は構成次第。
  本プロジェクトの主対象（AWS 内 + Akamai 協業）から外れるため、**「同一メカニズム（M1/M4）が適用可能・要検証」** とのみ記載。
- **Gcore**: S3 互換オブジェクトストレージ + ストレージをオリジンにする構成あり。M3 相当が可能だが、
  主対象外のため注記扱い。
- **Edgio（旧 Limelight / Edgecast）**: **2025年1月15日に CDN 事業停止**。資産の多くは Akamai が取得。
  **稼働中の選択肢ではない**ため比較対象から除外（メディア顧客の移行先として Akamai が関係する背景のみ補足）。

> 出典の所在: CloudFront OAC（AWS 公式 FSx チュートリアル）、Akamai Cloud Access Manager（techdocs.akamai.com）、
> Fastly S3 互換プライベートオリジン（fastly.com/documentation）、Cloudflare Workers/R2（developers.cloudflare.com）、
> Bunny Storage S3 互換（docs.bunny.net）、Google Media CDN private S3 origin（cloud.google.com/media-cdn）。
> いずれも「標準 S3 互換バケット」に対する記述であり、**FSx ONTAP S3 AP の accesspoint alias での動作は別途検証が必要**。

---

## 4. セキュリティ上の固定要件（メカニズム共通）

CDN を使う/使わないに関わらず、S3 AP 配信では以下を固定要件とします。

1. **公開配信は NFS/SMB ACL をバイパスする** — CDN 配信されたコンテンツは、ONTAP のファイル権限とは
   独立に視聴者へ届く。よって **配信対象は「承認済み・公開可」と判定された成果物に限定**し、ACL 制御下の
   マスターデータを直接配信レイヤへ流さない。
2. **マスターと配信系の分離** — マスター（ACL 制御・機微）と配信成果物（公開/準公開）を分離する。M3（Push）は
   この分離が構造的に自然。
3. **視聴者認証は CDN ネイティブ機構** — S3 Presigned URL 非対応のため、トークン/署名 URL は各 CDN の機能を使う。
4. **オリジン認証情報の最小権限** — CDN/署名層に渡す IAM 権限は対象 AP の `s3:GetObject` 等に限定。長期鍵を
   エッジに置かず、短期クレデンシャルを優先。
5. **配信ログの取り扱い** — 配信ログを分析目的で FSx へ書き戻す場合、視聴者 PII の取り扱いを設計に含める。
6. **配信承認の監査証跡** — 「どのオブジェクトを、誰が、いつ公開配信対象として承認したか」を記録する。
   承認元が未記録のオブジェクトは deny ではなく **可視化**（unrecorded として記録）し、運用で検知できるようにする。
7. **データ所在地 / 地域制限** — CDN はグローバルに配信するため、リージョン外への配信が許容されないデータは
   配信対象から除外するか、CDN の地域制限（geo-blocking）機能で制御する。承認プロセスにデータ所在地判定を含める。

## 4.1 エビデンス分類（Evidence classification）

本ドキュメントの記述は以下の2区分で扱う。混同しないこと。

| 区分 | 対象 | 性質 |
|------|------|------|
| **公開エビデンス** | 第3節の各配信網の機能（CloudFront OAC、Akamai Cloud Access Manager、Fastly SigV4、Cloudflare Workers/R2、Bunny Storage、Google Media CDN private S3 origin） | 各社の公開ドキュメントに基づく。**時点依存**であり、各社の仕様変更で変わりうる。採用前に最新版で再確認すること |
| **要検証（本プロジェクト）** | FSx ONTAP S3 AP の accesspoint alias に対する各 CDN の SigV4 オリジン署名の実動作 | 標準 S3 バケットでの実績を AP にそのまま適用できる保証はない。実機検証で確定する |

---

## 5. 実現可否サマリ（結論）

| 問い | 回答 |
|------|------|
| S3 AP を CDN オリジンに「認証なしで」公開できるか | **できない**（BPA 強制） |
| S3 AP を CDN から直接配信できるか | **できる（条件付き）** — SigV4 オリジン署名を持つ/実装できる CDN なら M1/M2。ただし AP alias での署名動作は要検証 |
| SigV4 を持たない CDN でも配信できるか | **できる** — M3（自社 S3 互換ストアへ Push）または M4（署名プロキシ）で |
| 視聴者向けに S3 Presigned URL を使えるか | **使えない** — CDN ネイティブのトークン機構を使う |
| マスターの ONTAP ACL を配信時に強制適用できるか | **できない** — 配信はファイル権限を経由しない。承認済み成果物のみ配信する運用で担保 |
| 最も検証リスクが低い初手は | **M3（Push）** — オリジン認証問題を回避でき、CDN 非依存・DemoMode 検証が容易 |

---

> **Governance Caveat**: 本資料は技術的な実現可否の参考情報です。各配信ネットワークの機能は更新されるため、
> 採用前に各社の最新公式ドキュメントで再確認してください。FSx ONTAP S3 AP の accesspoint alias に対する
> SigV4 オリジン署名の動作は、本プロジェクトでも実機検証項目（要検証）として扱います。実機検証手順は
> [ORIGIN_PULL SigV4 検証チェックリスト](cdn-origin-verification-checklist.md) を参照。配信ベンダーの選定は
> 顧客の契約・SLA・運用・規制要件を含めて顧客が判断するものです。
