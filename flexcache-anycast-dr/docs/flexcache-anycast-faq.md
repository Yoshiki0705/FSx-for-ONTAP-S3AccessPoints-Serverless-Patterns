# FlexCache AnyCast / DR — FAQ

## 基本概念

### Q: FlexCache とは何ですか？
A: FlexCache は ONTAP のリモートキャッシュ機能です。Origin volume のホットデータ（頻繁にアクセスされるデータ）のみをキャッシュし、リモート拠点やクラウドからの読み取り性能を向上させます。

### Q: AnyCast とは何ですか？
A: AnyCast は、複数のノードが同一 IP アドレスを広告し、ネットワークルーティング（BGP）により最も近いノードにクライアントを誘導する技術です。FlexCache AnyCast では、複数の FlexCache が同一 VIP を持ち、クライアントは自動的に最寄りのキャッシュにアクセスします。

### Q: FSx for ONTAP で AnyCast は使えますか？
A: FSx for ONTAP では Virtual IP / BGP が利用できないため、ネイティブ AnyCast は使用できません。代替として Route 53（Failover/Latency-based）、Global Accelerator、アプリケーションレベルルーティングで同等の効果を実現します。

## FlexCache + S3 Access Points

### Q: FlexCache volume に S3 Access Point を attach できますか？
A: 2026年5月時点で AWS ドキュメントに明示的な記載がなく、未確認です。PoC で検証することを推奨します。Origin volume への S3 AP attach は確認済みです。

### Q: FlexCache volume の S3 AP 経由で読み取りできますか？
A: 上記と同様、未確認です。可能であれば、キャッシュ済みデータを S3 API 経由でサーバーレス処理に渡す理想的な構成が実現できます。

### Q: FlexCache volume に S3 AP が attach できない場合はどうしますか？
A: 以下の代替構成を使用します:
- NFS/SMB クライアント → FlexCache volume（読み取り高速化）
- Lambda/Step Functions → Origin volume の S3 AP（サーバーレス処理）
- 両方を組み合わせて、クライアントアクセスとサーバーレス処理を分離

## 性能

### Q: FlexCache の cache hit ratio はどのくらいですか？
A: ワークロードに依存しますが、EDA Tools/Libraries のような読み取り中心のデータでは 80-95% の cache hit ratio が期待できます。Prepopulate を使用すると初期段階から高い hit ratio を実現できます。

### Q: FlexCache の初回読み取りレイテンシはどのくらいですか？
A: Cache miss 時は Origin からデータをフェッチするため、Origin への RTT + データ転送時間がかかります。同一リージョン内であれば数十 ms、クロスリージョンでは 100-300ms 程度です。

### Q: Prepopulate にはどのくらい時間がかかりますか？
A: データ量とネットワーク帯域に依存します。100GB のデータを 1Gbps リンクで prepopulate する場合、約 15-20 分です。

## DR

### Q: Origin が障害になった場合、FlexCache はどうなりますか？
A: ONTAP 9.12.1+ の disconnected mode が有効な場合、既にキャッシュ済みのデータは引き続き読み取り可能です。新規データ（キャッシュにないデータ）の読み取りは失敗します。

### Q: フェイルオーバーの RTO はどのくらいですか？
A: 構成により異なります:
- FSx Multi-AZ HA: <60秒（自動）
- Route 53 Failover: 60-300秒（TTL 依存）
- Global Accelerator: 数秒
- 手動切替: 数分〜数時間

## コスト

### Q: FlexCache のコストはどのくらいですか？
A: FlexCache volume のストレージコスト（FSx for ONTAP のストレージ料金）+ Origin からのデータ転送コスト（初回フェッチ時）です。ジョブ単位の Dynamic FlexCache であれば、ジョブ実行時のみコストが発生します。

### Q: AnyCast 代替（Route 53/Global Accelerator）のコストは？
A: Route 53: ホストゾーン $0.50/月 + クエリ $0.40/100万クエリ。Global Accelerator: $0.025/時間 + データ転送料金。Lambda routing: Lambda 実行料金のみ。

## 運用

### Q: Orphan FlexCache とは何ですか？
A: ジョブ完了後に削除されずに残った Dynamic FlexCache volume です。cleanup 失敗や Lambda タイムアウトで発生する可能性があります。定期的な検出・削除メカニズムが必要です。

### Q: FlexCache のサイズはどのくらいに設定すべきですか？
A: ホットデータ量の 1.2-1.5 倍を推奨します。小さすぎるとキャッシュ eviction が頻発し、大きすぎるとコストが増加します。

### Q: ヘルスチェックの間隔はどのくらいが適切ですか？
A: 通常は 5 分間隔を推奨します。高可用性要件がある場合は 1 分間隔。コスト最適化を優先する場合は 15 分間隔。
