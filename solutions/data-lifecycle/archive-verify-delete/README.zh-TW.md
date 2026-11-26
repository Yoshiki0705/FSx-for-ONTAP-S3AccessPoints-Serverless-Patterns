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
| 在本儲存庫中確認 | 使用 moto 的單元測試，以及狀態機和 IAM 結構的測試。未連接 AWS。上述實機端到端執行中發現的 3 個缺陷（ONTAP REST 函數的呼叫權限、TLS 驗證、重複恢復請求的錯誤名稱）已透過能夠重現它們的測試修復 |
| 在實機端到端執行中各確認 1 次（2026-11-26，與上述相同的環境，`selection=ATIME`，`GLACIER`，7 個檔案） | 透過 ONTAP REST API 按 `accessed_time` 選擇，並獲取 uid、gid、mode、mtime、atime（根是磁碟區的根，路徑開頭沒有斜槓；`unix_permissions` 以整數 `640` 返回）。Distributed Map 的 `ItemReader` 和 `ResultWriter`。用 Fargate 進行 5.5 GiB 的分段複制（帶 `CopySourceIfMatch`，CRC64NVME 與帳本一致）。在 Lambda 中對 5.3 GB（約 4.94 GiB）計算雜湊（69.8 秒，設定記憶體 2048 MB，使用 152 MB）。第二份副本。批准後的刪除。等待批准期間在 NFS 上改寫的檔案變為 `CHANGED`，沒有被刪除。拒絕批准後什麼都沒有被刪除。用 `Expedited` 恢復（含 5.5 GiB），恢復的 6 個檔案 SHA-256 一致（7 個檔案中剩下的 1 個已被改寫，既沒有被刪除也沒有被恢復）。用 `reapply.sh` 恢復 uid、gid、mode、mtime |
### 環境與各步驟的結果
環境為 ap-northeast-1、FSx for ONTAP 第 1 代 `SINGLE_AZ_1`、ONTAP 9.19.1P4D1、UNIX 安全樣式的磁碟區，Access Point 的檔案系統使用者為 UNIX root。執行日期為 2026-11-26（時間為日本標準時間），每個步驟只執行了 1 次。設定為 `selection=ATIME`、`GLACIER`、有第二份副本，Fargate 為 arm64 的 2 vCPU 和 8 GiB。資料為 6 個小檔案（3 個 64 B、3 個 8 MiB，所有者 1234:5678，模式 640，mtime 和 atime 為 2020-01-02）和 1 個 5,905,580,032 B 的檔案。
| 步驟 | 結果 | 耗時 |
|---|---|---|
| 1. 部署 | 成功。但執行中發現 2 個缺陷，修復後重新部署 | 從准備到部署約 30 分鐘（16:19 至 16:50） |
| 2. dry run（`dryRun=true`） | 修復後成功。7 個檔案全部 `VERIFIED`（SHA-256 一致 6 個，CRC64NVME 一致 1 個），第二份副本也是 `VERIFIED`。刪除 0 字節，NFS 上 7 個檔案全部保留 | 244 秒（含等待批准約 70 秒） |
| 3. 等待批准期間的改寫 | 在 NFS 上把 1 個檔案以相同大小覆寫 4 KiB（mtime 更新）。批准後變為 `CHANGED`（ETag 或大小不一致），沒有被刪除 | |
| 4. 正式執行（`dryRun=false`）與批准 | 6 個 `DELETED`，1 個 `CHANGED`。`bytesDeleted` 為 5,922,357,440。NFS 上 6 個檔案消失，只剩被改寫的 1 個 | 310 秒（到發出批准請求 172 秒，從批准到完成約 6 秒） |
| 5. 恢復（`tier=Expedited`，`days=1`） | 6 個 `RESTORED`（含 5.5 GiB）。6 個檔案的 SHA-256 都與步驟 1 之前在 NFS 上記錄的值一致。`CHANGED` 的 1 個不在物件內 | 287 秒（5 個小檔案約 2.5 分鐘，5.5 GiB 的 Fargate 複制用時 2 分 38 秒） |
| 6. 拒絕批准（`send-task-failure`） | 執行以 `REJECTED_OR_TIMED_OUT` 結束，3 個檔案仍為 `VERIFIED`。`deletedBy` 為空，NFS 上 3 個檔案都保留 | 16 秒 |
| 追加：在 Lambda 中對 5.3 GB（約 4.94 GiB）計算雜湊 | `VERIFIED`（SHA-256 與 NFS 的值一致），第二份副本也是 `VERIFIED` | `record` 函數 69.8 秒（設定記憶體 2048 MB，使用 152 MB） |
| 追加：重複提交恢復請求 | 第二次返回 HTTP 409 `RestoreAlreadyInProgress`。Step Functions 的 SDK 集成以 `S3.S3Exception` 返回 | |
之後已刪除全部資源，並透過讀回確認。
### 使用量（各執行 1 次，不是帳單）
| 執行 | 檔案數 | 耗時 | 狀態轉換（父 + 子 Map 執行） | Fargate 任務 |
|---|---|---|---|---|
| dry run | 7 | 244 秒 | 12 + 107 = 119 | 2 次（雜湊與複制 96 秒，第二份副本 35 秒） |
| 正式執行 | 7 | 310 秒 | 13 + 114 = 127 | 2 次（94 秒，35 秒） |
| 恢復 | 6 | 287 秒 | 4 + 103 = 107 | 1 次（156 秒） |
| 拒絕 | 3 | 16 秒 | 10 + 45 = 55 | 0 次 |
- Lambda 執行時間合計（CloudWatch。含失敗的呼叫，不含 4.94 GiB 的執行）：`select` 13 次 5.9 秒，`ontap_rest` 11 次 13.4 秒（失敗 2 次），`record` 17 次 11.7 秒，`ledger` 34 次 9.1 秒，`approval` 6 次 4.3 秒，`delete` 7 次 5.6 秒，`summarize` 5 次 5.1 秒，`restore` 26 次 9.2 秒
- Fargate 共 5 個任務，合計約 416 秒（2 vCPU、8 GiB、arm64）。DynamoDB（按需）讀取 68.5 RCU、寫入 74 WCU（全部執行合計）
- 未測量 S3 請求數（未啟用請求指標）
### 端到端執行中發現並修復的 3 個缺陷
均已透過能夠重現的測試修復。
| # | 現象 | 原因與修復 |
|---|---|---|
| 1 | `selection=ATIME` 的執行在選擇階段失敗 | 歸檔狀態機的角色沒有對 ONTAP REST 函數的 `lambda:InvokeFunction`。已添加權限 |
| 2 | ONTAP REST 函數因 `CERTIFICATE_VERIFY_FAILED` 失敗 | 始終驗證 TLS，但 FSx for ONTAP 管理端點的證書不是由公共 CA 簽發。已添加參數 `OntapVerifySsl`（預設 `false`） |
| 3 | 重複提交恢復請求被當作檔案失敗 | Step Functions 的 SDK 集成把 `RestoreAlreadyInProgress` 以 `S3.S3Exception` 返回，因此與 `S3.RestoreAlreadyInProgressException` 的 `Catch` 不匹配。已改為把進行中的恢復送入等待完成的循環 |
### 端到端執行中得知的行為
這些行為沒有作為缺陷修復。
- 在 `selection=ATIME` 下，本模式自身的讀取會更新 `accessed_time`。用 `dryRun=true` 執行一次後，計算雜湊的讀取使檔案的 atime 變為執行時間，因此用相同輸入執行 `dryRun=false` 也不會被選中（以 0 個檔案結束；在 dry run 之後立即正式執行時確認）。也就是說，執行 dry run 會讓這些檔案看起來像是最近被讀取過。若要在 dry run 之後立即對相同的候選正式執行，請使用 `selection=MTIME`（`LastModified` 不會因讀取而改變）
- Access Point 的 ETag 隨 mtime 和大小變化，而不是隨內容變化。大小和 mtime 相同、內容不同的 3 個檔案返回了相同的 ETag。因此刪除前對 ETag 和大小的確認，無法發現大小和 mtime 都不變的內容變更。大小相同但 mtime 更新的改寫被檢測到了（步驟 3）
- 透過 Access Point 刪除最後一個檔案時，變空的上級目錄也會一並消失（在 `arc-e2e/large/` 上確認）。恢復時的 `CopyObject` 會重新創建上級目錄
- 恢復後的檔案所有者為 0:1，模式為 644，修改時間為恢復的時間。在透過 NFS 掛載了磁碟區的主機上，以 root 執行生成的 `reapply.sh` 後，恢復為原來的 uid、gid、mode、mtime（1234:5678、640、2020-01-02 03:04:05），內容的 SHA-256 沒有變化
- 本次執行在 Access Point 策略中允許了各個角色（`select`、`record`、`delete`、`restore` 各函數的角色、Fargate 任務角色、兩個狀態機的角色）
- 5.5 GiB 的 `Expedited` 恢復請求被接受，並在約 4 分鐘內完成
### 未確認的事項
- 大量檔案時的耗時和費用
- `Standard` 和 `Bulk` 恢復的完成等待（實機上只執行了 `Expedited`）
- `S3.SlowDownException` 的重試（未觀察到 SDK 集成返回的名稱，可能出現與缺陷 3 同類的不匹配）
- CloudTrail 資料事件中的刪除記錄（未確認帳戶的追蹤是否包含物件 Access Point 的資料事件）
- NTFS 磁碟區、非 root 使用者、第 2 代、Multi-AZ
- Access Point 未附加策略時的行為
- 恢復中除了不選擇 `CHANGED` 檔案之外的 `EXISTS` 路徑（NFS 上已有同名檔案的情況）
- 有 1 次執行的候選為 0 個，原因不明。在用 `touch -d` 還原 atime 約 10 秒後的執行中候選為 0 個。約 17 分鐘後的確認返回了 2020 年的值，`touch` 之後立即進行的另一次確認也返回了 6 個檔案。未能確定原因，也未能重現
### 刪除前確認中殘留的寫入視窗
刪除前的確認中仍殘留一個寫入視窗。Access Point 的 `DeleteObject` 不支持條件刪除，因此在用 `HeadObject` 確認之後到刪除之前被改寫的情況無法檢測。該視窗相當於一次 API 呼叫往返。
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
- 僅在使用 `selection=ATIME` 和屬性記錄時需要：VPC、子網、保存 ONTAP 憑據的金鑰、管理端點、磁碟區 UUID、`OntapVerifySsl`。FSx for ONTAP 管理端點的證書不是由公共 CA 簽發，因此預設值為 `false`（不驗證），此時 ONTAP 憑據會透過不對對端進行認證的連接發送（路徑在 VPC 內）。設為 `true` 時，選擇階段因證書錯誤而停止（已觀察到）。需要從 VPC 內的 Lambda 到 Secrets Manager 和 S3 的路徑（VPC 端點或 NAT）
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
- 在 UNIX 樣式的磁碟區上確認。大小和 mtime 都不變的內容變更，無法透過 ETag 和大小的確認檢測到（參見上文“端到端執行中得知的行為”）。`chown` 是否會改變 ETag 尚未確認
- 屬性是透過目錄清單獲取的。為了一個檔案要讀取整個父目錄，因此對大目錄會變慢
- 歸檔用儲存桶的版本控制不是 Object Lock。版本會保留，但有許可權就可以刪除版本
## 相關文件
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 相容性備忘](../../../docs/s3ap-compatibility-notes.md)
- [轉移到歸檔類別的 8 種機制的比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）

---

<!-- playbook-reading:start -->
## 上線前需要閱讀的內容

部署後才會遇到的限制如何轉化為設計決策，記錄在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一內容放在兩處時，停止更新的那份會比已修正的那份留存更久。

- [資料活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 透過存取點存取資料的限制（所有模式通用）
- [資料保護](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — 該模式的決策集中之處
- [建置](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上線前通讀（所有模式通用）
<!-- playbook-reading:end -->
