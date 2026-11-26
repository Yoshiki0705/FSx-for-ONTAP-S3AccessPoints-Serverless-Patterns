# archive-verify-delete：僅用 S3 API 複製、核對，並在批准後刪除的歸檔
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文件**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 概述
本模式把 Amazon FSx for NetApp ONTAP（以下簡稱 FSx for ONTAP）磁碟區上很少被讀取的檔案，轉移到 S3 Glacier 系列的儲存類別。不掛載磁碟區，只使用 S3 Access Points 的 S3 API。
一個檔案按下列順序處理，中途條件不成立的檔案會被排除在刪除物件之外。
1. 在帳本（DynamoDB 資料表）中記錄大小、ETag、SHA-256 和 CRC64NVME
2. 指定儲存類別，用 `CopyObject` 複製到歸檔用儲存桶
3. 把儲存桶返回的校驗和與帳本中的值進行比較
4. 由人批准一致檔案的清單
5. 確認 Access Point 的 ETag 和大小與帳本相同後，刪除 Access Point 上的檔案

恢復時，先在帳本中查詢，在儲存桶中請求恢復，等待完成後用 `CopyObject` 複製回 Access Point。
本模式不使用 S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock 和快照鎖定，模板中也沒有寫入。因為不設定保留期限，所以對歸檔用儲存桶中的物件，只要有許可權就可以刪除。
本模式的前提，以及與其他方式的比較，見[轉移到歸檔類別的 8 種機制的比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）。
## 已測量和未測量的內容
| 類別 | 內容 |
|---|---|
| 各組成部分已在實際環境中各確認 1 次（記錄在上述比較資料中，2026-11-24 和 2026-11-26，ap-northeast-1，第 1 代 `SINGLE_AZ_1`，ONTAP 9.19.1P4D1，UNIX 樣式磁碟區，Access Point 使用者為 UNIX root） | 給 `CopyObject` 指定 `ChecksumAlgorithm=SHA256` 後，儲存桶的 `ChecksumSHA256` 為 `FULL_OBJECT`，與檔案的 SHA-256 一致（最大 8 MiB）。5.5 GiB 的分段上傳中 SHA-256 變為 `COMPOSITE`，CRC64NVME 為 `FULL_OBJECT` 且一致。使用舊 ETag 的 `--copy-source-if-match` 返回 `PreconditionFailed`。Access Point 的 `DeleteObject` 不支援 `If-Match`。在 Step Functions 的 SDK 整合中，可以把 Access Point 別名傳給 `Bucket` |
| 在本倉庫中已確認 | 使用 moto 的單元測試，以及狀態機和 IAM 結構的測試。未連線 AWS |
| 尚未確認 | 整個模式在實際環境中的端到端執行。大量檔案時的耗時和費用。Lambda 對接近 5 GiB 的檔案計算雜湊的時間。Fargate 分段複製在實際環境中的表現。ONTAP REST API 中根目錄的指定方式和 `unix_permissions` 的表示。Distributed Map 的 `ItemReader` 和 `ResultWriter` 在實際環境中的表現。需要恢復的 2 個類別的恢復。NTFS 磁碟區、非 root 使用者、第 2 代、Multi-AZ |
刪除前的確認仍留有一個寫入視窗。Access Point 的 `DeleteObject` 不支援條件刪除，因此在用 `HeadObject` 確認之後到刪除之前這段時間內發生的寫入無法被檢測到。這個視窗相當於一次 API 呼叫的往返。
## 處理流程
### 歸檔
輸入中 `olderThanDays` 為必填，`dryRun` 的預設值為 `true`。
| 步驟 | 處理 | 實現 |
|---|---|---|
| 1. 選擇 | `MTIME`：Access Point `ListObjectsV2` 的 `LastModified`。`ATIME`：ONTAP REST API 的 `accessed_time`（VPC 內的 Lambda） | `select`、`ontap_rest` |
| 2. 記錄 | 把大小、ETag、SHA-256、CRC64NVME，以及可獲取時的 uid、gid、mode、mtime、atime 寫入帳本。5 GiB 以下用 Lambda，超出部分用 Fargate | `record`、Fargate 任務 |
| 3. 複製 | 5 GiB 以下用 SDK 整合的 `copyObject`（`SHA256`，把帳本的 ETag 作為 `CopySourceIfMatch`）。超出部分用 Fargate 的分段複製（`CRC64NVME`） | Step Functions、Fargate |
| 4. 核對 | 把儲存桶 `HeadObject`（`ChecksumMode=ENABLED`）的大小和校驗和與帳本比較。不一致則保留為 `MISMATCH`，並排除在刪除物件之外 | `ledger` |
| 5. 第二份副本（可選） | 從 Access Point 複製到同一區域的另一個儲存桶，並做同樣的核對。不一致則排除在刪除物件之外 | Step Functions、`ledger` |
| 6. 批准 | 把一致的清單寫入 `manifests/<runId>.json`，透過 SNS 通知，並用 `waitForTaskToken` 等待 | `approval` |
| 7. 刪除 | 僅在 `dryRun=false` 時執行。逐個檔案確認 ETag 和大小，相同則 `DeleteObject`。不同則保留為 `CHANGED` | `delete` |
| 8. 記錄 | `manifests/<runId>-result.json` 和 EMF 指標（件數、位元組數） | `summarize` |
即使 `dryRun=true`，也會執行到第 6 步。也就是說會進行復制，併產生歸檔類別的儲存費用（S3 Glacier Deep Archive 有最短儲存期限）。試用時請把 `maxFiles` 設小。不會執行刪除。
帳本的狀態按 `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`DELETED`、`RESTORED` 的順序推進，中途的出口是 `CHANGED`、`MISMATCH`、`FAILED`。只有 `VERIFIED`（要求第二份副本時，還須完成其核對）的檔案才能被刪除。
### 恢復
輸入為 `runId`，以及 `keys` 或 `prefix` 中的一個。可以指定 `tier`（預設 `Bulk`）和 `days`（預設 7）。
1. 在帳本中選擇 `DELETED` 的檔案
2. 如果 Access Point 上已存在相同的鍵，則保留為 `EXISTS`，不覆蓋
3. 對 S3 Glacier Flexible Retrieval 和 S3 Glacier Deep Archive 的物件請求 `RestoreObject`（S3 Glacier Instant Retrieval 不需要）
4. 完成等待採用輪詢（每隔 `RestorePollMinutes` 讀取 `HeadObject` 的 `Restore` 頭，到 `RestoreMaxWaitHours` 時終止）。不使用 EventBridge 的 `Object Restore Completed`。儲存桶的 EventBridge 通知已啟用，因此以後可以切換
5. 從儲存桶向 Access Point 執行 `CopyObject`（超過 5 GiB 用 Fargate）
6. 把帳本設為 `RESTORED`，並寫出用於重新設定屬性的指令碼 `manifests/<runId>-reapply.sh`

恢復後的檔案，所有者為 0:1，模式為 644，修改時間為恢復的時刻（上述環境中的 1 次確認）。原來的值無法透過 `CopyObject` 恢復。
## 批准操作
批准通知中不包含權杖。權杖在 AWS Systems Manager Parameter Store 的 SecureString（`/<stack>/approvals/<runId>`）中。批准的人需要具有讀取該引數的許可權和 `states:SendTaskSuccess` 許可權。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# 拒絕：
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` 是自行申報的值。輸入的值會寫入帳本的 `deletedBy`，但證明實際批准主體的是 CloudTrail 的 `SendTaskSuccess` 事件。如果 `approver` 為空，或 `approved` 不是 `true`，則不會執行刪除。
## 重新設定屬性
恢復的最後會寫出 `manifests/<runId>-reapply.sh`。在透過 NFS 掛載了該磁碟區的主機上，以 root 身份執行。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
指令碼只包含 `chown`、`chmod` 和 `touch -d`，帳本中的值按嚴格的格式檢查，鍵透過 shell 引用成為一個單詞。不符合格式的值會變成註釋，不會被執行。ONTAP REST API 能否設定所有者、組、模式和修改時間尚未確認，因此未實現這條路徑。
## 部署
### 前提
- Access Point 的別名和 ARN 兩者都需要（IAM 需要兩種形式。僅有別名的策略可以部署，但執行時會被拒絕）
- 歸檔用儲存桶的名稱（由堆疊建立。`DeletionPolicy: Retain`、Block Public Access、預設 SSE-S3、KMS 可選、啟用 EventBridge 通知、必須使用 TLS）
- 僅在使用 `selection=ATIME` 和記錄屬性時需要：VPC、子網、ONTAP 憑據的金鑰、管理端點、磁碟區的 UUID。需要從 VPC 內的 Lambda 到 Secrets Manager 和 S3 的路徑（VPC 端點或 NAT）
- 僅在處理超過 5 GiB 的檔案時需要：放在 ECR 中的映象。Access Point 是 Internet-origin，因此 Fargate 的子網需要 NAT 或公網 IP
### 步驟
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # 替換 <PLACEHOLDER>
sam build && sam deploy
```
使用 Fargate 時，在倉庫根目錄構建映象，push 到自己的 ECR 倉庫，並指定給 `FargateImageUri`。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
執行時，先用省略 `dryRun`（即為 `true`）的輸入執行。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
要執行到刪除，請把 `"dryRun": false` 作為 JSON 布林值傳入。字串 `"false"` 會成為輸入錯誤，不會執行刪除。
## 目錄結構
```
archive-verify-delete/
├── template.yaml                # SAM：儲存桶、帳本、8 個 Lambda、2 個狀態機、Fargate（可選）
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
領域邏輯（校驗和、輸入檢查、帳本）位於 [`shared/archive_verify/`](../../../shared/archive_verify/)，在 `shared/tests/` 中測試。對 Access Point 的讀寫都經過 `shared/s3ap_helper.py`。
## 本地測試
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
為了確認刪除判定被破壞時能夠被檢測到，用去掉 ETag 比較的樁程式碼把 `test_does_not_delete_when_etag_changed` 和 `test_does_not_delete_when_size_differs_but_etag_equal` 執行了 1 次，2 個測試都以 `assert 'DELETED' == 'CHANGED'` 失敗。恢復原狀後，29 個測試透過。
## Success Metrics
### Outcome
把很少被讀取的檔案，經過核對和人的批准後轉移到 S3 Glacier 系列的類別，降低磁碟區的使用量。轉移後的檔案可以從帳本中查詢並恢復。
### Metrics
目標值由使用者決定。這裡不給出數值。
| 類別 | 指標 | 定義 |
|---|---|---|
| Business Outcome | 釋放的容量 | `bytesDeleted`（`-result.json`）。只要快照還在，磁碟區的使用量就不會下降 |
| Technical KPI | 核對一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 未刪除的件數 | `CHANGED`、`MISMATCH` 和 `FAILED` 的合計 |
| Quality KPI | 未經批准而被刪除的件數 | 必須為 0。統計帳本中 `deletedBy` 為空的 `DELETED` |
| Cost KPI | 每次執行的 Lambda、Fargate、DynamoDB、S3 請求、歸檔類別的儲存費用 | 未測量。先用 `dryRun=true` 和較小的 `maxFiles` 估算 |
| Go / No-Go | 在實際環境的端到端執行中，所有已複製的檔案都變為 `VERIFIED`，有意製造的 `CHANGED` 不會被刪除，恢復後檔案的 SHA-256 一致 | 在滿足之前，不要對正式環境磁碟區使用 `dryRun=false` |
### Measurement Method
Step Functions 的執行歷史、`manifests/<runId>-result.json`、CloudWatch 的 EMF 指標（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`BytesVerified`、`BytesDeleted`）、帳本。
## Performance Considerations
未測量。以下是設計上的因素。
- 原始檔會被讀取 2 次。第 1 次是為計算雜湊而透過 Access Point 讀取，第 2 次是 `CopyObject` 在伺服器端讀取。會產生讀取請求費用，位於容量池中的資料還會產生容量池的讀取費用
- 並行度為 `MapConcurrency`（預設 10）。請根據 Access Point 和 ONTAP 的負載，從較小的值開始
- Lambda 的上限為 15 分鐘。由於沒有測量從 Access Point 的讀取速度，無法確定預設的 5 GiB（`LargeFileThresholdBytes`）是否足夠。如果不夠，請調低；由 Fargate 處理的部分會增加
- 清單會把 `ListObjectsV2` 的全部結果載入一個 Lambda 的記憶體。超過數百萬件時，請用 `prefix` 分開處理
- `selection=ATIME` 以深度優先遍歷目錄。掃描上限為 200,000 個條目（`ONTAP_SCAN_LIMIT`），超出時返回到中途為止的結果
- 恢復的等待時間由類別和 `tier` 決定。AWS 記載 S3 Glacier Deep Archive 在 Standard 下 12 小時以內，在 Bulk 下 48 小時以內。`RestoreMaxWaitHours` 的預設值為 72
## Governance Note
> 本模式提供技術架構方面的指導。它不是法律、合規或監管方面的建議。請組織諮詢合格的專業人士。
- 核對結果和批准是供人做最終判斷的輔助訊號。未使用 AI
- 如果需要滿足保留期限和不可變性，本模式不支援。因為沒有使用 Object Lock 等，所以有許可權就可以刪除
- 輸出分類：帳本和清單包含檔案路徑、大小、雜湊、屬性（`dataClassification: operational-metadata`）。檔案內容會進入歸檔用儲存桶，因此請按與原始資料相同的分類處理
- Human Review：每次執行都必須批准。沒有基於置信度的自動批准
- IAM：持有 `s3:DeleteObject` 的只有 `delete` 函式的角色。Fargate 任務只負責複製，沒有刪除許可權。沒有授予任何人刪除帳本條目的許可權
- 審計：批准和刪除會記錄在帳本（`deletedBy`、`deletedAt`）、Step Functions 的執行歷史和 CloudTrail 中
## 限制與未確認事項
- 從 Access Point 直接複製到其他區域的儲存桶時返回了 `AccessDenied`（1 個 Access Point，1 次）。第二份副本僅以同一區域的儲存桶為物件
- 這是在 UNIX 樣式磁碟區上的確認。把修改時間改回原值後再改動內容的操作，以及 `chown`，能否透過 ETag 檢測到，尚未確認
- 屬性是透過目錄清單獲取的。為了一個檔案要讀取整個父目錄，因此對大目錄會變慢
- 歸檔用儲存桶的版本控制不是 Object Lock。版本會保留，但有許可權就可以刪除版本
## 相關文件
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 相容性備忘](../../../docs/s3ap-compatibility-notes.md)
- [轉移到歸檔類別的 8 種機制的比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）
