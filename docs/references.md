# 参考リンク集

本プロジェクト（FSxN S3 Access Points Serverless Patterns）の実装で参考にした AWS 公式ドキュメント、ブログ記事、サンプルリポジトリのリンク集です。

---

## AWS 公式 FSx ONTAP S3 Access Points ドキュメント

| ドキュメント | URL | 説明 |
|---|---|---|
| S3 AP 概要 | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html | FSx ONTAP S3 Access Points の概要と基本概念 |
| 対応 API 一覧 | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html | S3 AP 経由で利用可能な S3 API サブセット |
| 制約事項 | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html | S3 AP の制約事項・命名規則 |
| AWS サービス連携 | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html | S3 AP と他の AWS サービスとの連携方法 |

---

## AWS 公式チュートリアル（7 パターン）と本プロジェクトの対応表

AWS は FSx ONTAP S3 Access Points を活用した 7 つの公式チュートリアルを提供しています。本プロジェクトの各ユースケースとの対応関係は以下の通りです。

| チュートリアル | URL | 本プロジェクト対応 |
|---|---|---|
| Athena で SQL クエリ | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html | UC1（法務）、UC3（製造業） |
| Lambda でサーバーレス処理 | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html | 全 UC 基盤 |
| Glue で ETL パイプライン | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html | UC3 拡張（`manufacturing-analytics/glue-etl/`） |
| Bedrock Knowledge Bases で RAG | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html | 拡張パターン（`docs/extension-patterns.md`） |
| EMR Serverless で Spark | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-run-spark-with-emr-serverless.html | 拡張パターン（`docs/extension-patterns.md`） |
| CloudFront でストリーミング | https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html | UC4 拡張（`media-vfx/cloudfront/`） |
| Transfer Family で SFTP | https://docs.aws.amazon.com/transfer/latest/userguide/fsx-s3-access-points.html | 拡張パターン（`docs/extension-patterns.md`） |

---

## AWS ブログ記事

| 記事タイトル | URL | 関連 |
|---|---|---|
| S3 AP 発表ブログ | https://aws.amazon.com/blogs/aws/amazon-fsx-for-netapp-ontap-now-integrates-with-amazon-s3-for-seamless-data-access/ | 全体 |
| 3 つのサーバーレスアーキテクチャパターン | https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/ | 全体 |
| AD 統合 | https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/ | UC1 |
| Transfer Family SFTP | https://aws.amazon.com/blogs/storage/secure-sftp-file-sharing-with-aws-transfer-family-amazon-fsx-for-netapp-ontap-and-s3-access-points/ | 拡張パターン |
| Step Functions + Bedrock ドキュメント処理 | https://aws.amazon.com/blogs/compute/orchestrating-large-scale-document-processing-with-aws-step-functions-and-amazon-bedrock-batch-inference/ | UC2 |
| FSx ONTAP + Bedrock RAG | https://aws.amazon.com/blogs/machine-learning/build-rag-based-generative-ai-applications-in-aws-using-amazon-fsx-for-netapp-ontap-with-amazon-bedrock/ | 拡張パターン |

---

## AWS サンプルリポジトリ

| リポジトリ | URL | 関連 |
|---|---|---|
| サーバーレスパターン集 | https://github.com/aws-samples/serverless-patterns | 全体 |
| Textract 大規模処理 | https://github.com/aws-samples/amazon-textract-serverless-large-scale-document-processing | UC2 |
| Rekognition 大規模処理 | https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing | UC3, UC4, UC5 |
| Step Functions サンプル | https://github.com/aws-samples/aws-stepfunctions-examples | 全体 |
| Step Functions + Rekognition | https://github.com/aws-samples/dotnet-serverless-imagerecognition | UC3, UC4 |

---

## 元プロジェクト: Permission-aware Agentic Access-Aware RAG

本プロジェクトの共通モジュール（OntapClient、FsxHelper）は、以下のプロジェクトの検証済みパターンを継承・進化させたものです。

| 項目 | 内容 |
|------|------|
| プロジェクト名 | FSx-for-ONTAP-Agentic-Access-Aware-RAG |
| 概要 | FSx for NetApp ONTAP + Amazon Bedrock による権限ベース RAG システム |
| 主な機能 | NTFS ACL / AD SID に基づくアクセス制御付き RAG、Bedrock Agents によるエージェント型推論、Bedrock Knowledge Bases によるドキュメントインデックス |
| 技術スタック | CDK v2 (TypeScript)、Next.js 15、Python Lambda、Aurora pgvector / OpenSearch Serverless |
| 継承パターン | OntapClient（Secrets Manager 認証、urllib3、TLS 検証、リトライ）、FsxHelper（FSx API + CloudWatch メトリクス）、S3 AP ARN を Bucket パラメータとして使用するパターン |

本プロジェクトの拡張パターン（Bedrock Knowledge Bases 統合）を実装する際は、元プロジェクトの権限ベースアクセス制御設計（DynamoDB ユーザーアクセステーブル、AD SID マッピング、検索時フィルタリング）を参考にすることで、セキュアなエンタープライズ RAG を構築できます。

---

## UC 別参考リンク

### UC1: 法務・コンプライアンス（ファイルサーバー監査・データガバナンス）

- **Athena チュートリアル**: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html
- **Bedrock InvokeModel API**: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html
- **AD 統合ブログ**: https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/
- **ONTAP REST API リファレンス**: https://docs.netapp.com/us-en/ontap-automation/

### UC2: 金融・保険（契約書・請求書の自動処理）

- **Textract API リファレンス**: https://docs.aws.amazon.com/textract/latest/dg/API_Reference.html
- **Comprehend DetectEntities**: https://docs.aws.amazon.com/comprehend/latest/dg/API_DetectEntities.html
- **IDP ガイダンス**: https://aws.amazon.com/solutions/guidance/intelligent-document-processing-on-aws3/
- **Step Functions + Bedrock ドキュメント処理**: https://aws.amazon.com/blogs/compute/orchestrating-large-scale-document-processing-with-aws-step-functions-and-amazon-bedrock-batch-inference/
- **Textract 大規模処理サンプル**: https://github.com/aws-samples/amazon-textract-serverless-large-scale-document-processing

### UC3: 製造業（IoT センサーログ・品質検査画像の分析）

- **Glue ETL チュートリアル**: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html
- **Athena チュートリアル**: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html
- **Rekognition DetectLabels**: https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html
- **Rekognition 大規模処理サンプル**: https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing

### UC4: メディア（VFX レンダリングパイプライン）

- **CloudFront ストリーミングチュートリアル**: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-stream-video-with-cloudfront.html
- **Deadline Cloud API**: https://docs.aws.amazon.com/deadline-cloud/latest/APIReference/Welcome.html
- **Rekognition DetectLabels**: https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectLabels.html
- **Step Functions + Rekognition サンプル**: https://github.com/aws-samples/dotnet-serverless-imagerecognition

### UC5: 医療（DICOM 画像の自動分類・匿名化）

- **Comprehend Medical DetectPHI**: https://docs.aws.amazon.com/comprehend-medical/latest/dev/API_DetectPHI.html
- **Rekognition DetectText**: https://docs.aws.amazon.com/rekognition/latest/dg/API_DetectText.html
- **Rekognition 大規模処理サンプル**: https://github.com/aws-samples/amazon-rekognition-serverless-large-scale-image-and-video-processing
- **HIPAA on AWS**: https://docs.aws.amazon.com/whitepapers/latest/architecting-hipaa-security-and-compliance-on-aws/welcome.html
