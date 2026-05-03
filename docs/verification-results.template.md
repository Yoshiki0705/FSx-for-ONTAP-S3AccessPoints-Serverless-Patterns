# 検証結果記録テンプレート

AWS 環境での検証結果を記録するためのテンプレートです。
実際の検証結果は `verification-results.md` に記録してください（gitignore 対象）。

## 検証環境

- AWS リージョン: `<your-region>`
- FSx ONTAP バージョン: `<ontap-version>`
- FSx ファイルシステム ID: `<fs-id>`
- S3 Access Point: `<s3ap-name>`
- 検証日: `<date>`

## チェックリスト

### 共通モジュール

- [ ] S3ApHelper ListObjectsV2
- [ ] S3ApHelper HeadObject
- [ ] S3ApHelper PutObject + GetObject round-trip
- [ ] S3ApHelper DeleteObject
- [ ] FsxHelper describe_file_systems
- [ ] FsxHelper describe_volumes
- [ ] OntapClient list_volumes
- [ ] OntapClient list_nfs_exports
- [ ] OntapClient list_cifs_shares
- [ ] OntapClient get_svm

### CloudFormation テンプレート

- [ ] legal-compliance/template.yaml validate-template
- [ ] financial-idp/template.yaml validate-template
- [ ] manufacturing-analytics/template.yaml validate-template
- [ ] media-vfx/template.yaml validate-template
- [ ] healthcare-dicom/template.yaml validate-template

### Step Functions E2E ワークフロー

- [ ] UC1 法務・コンプライアンス SUCCEEDED
- [ ] UC2 金融・保険 SUCCEEDED
- [ ] UC3 製造業 SUCCEEDED
- [ ] UC4 メディア VFX SUCCEEDED
- [ ] UC5 医療 DICOM SUCCEEDED

### AI/ML サービス実呼び出し

- [ ] Amazon Athena (UC1, UC3)
- [ ] Amazon Bedrock (UC1, UC2)
- [ ] Amazon Rekognition (UC3, UC4, UC5)
- [ ] Amazon Comprehend (UC2)
- [ ] Amazon Textract (UC2) — クロスリージョン呼び出し
- [ ] Amazon Comprehend Medical (UC5) — クロスリージョン呼び出し

### 拡張パターン

- [ ] Bedrock Knowledge Bases (RAG)
- [ ] Transfer Family SFTP
- [ ] EMR Serverless Spark
