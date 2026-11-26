# archive-verify-delete：僅用 S3 API 複製、核對，並在批准後刪除的歸檔
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文件**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## 概述
本模式把 Amazon FSx for NetApp ONTAP（FSx for ONTAP）磁碟區上很少被讀取的檔案，轉移到 S3 Glacier 系列的儲存類別。檔案的讀取、寫入和刪除使用 S3 Access Points 的 S3 API，不使用 NFS 掛載。以下兩點需要額外的條件：依最後存取時間選擇（`selection=ATIME`）和記錄屬性要使用 ONTAP REST API（VPC 內的 Lambda 函數、ONTAP 憑據、管理端點）；恢復後把擁有者、模式和修改時間設回原值，則需要一台以 NFS 掛載該磁碟區的主機。
一個檔案按下列順序處理，中途條件不成立的檔案會被排除在刪除物件之外。
1. 在帳本（DynamoDB 資料表）中記錄大小、ETag、SHA-256 和 CRC64NVME
2. 指定儲存類別，用 `CopyObject` 複製到歸檔用儲存桶（鍵為 `<prefix><runId>/<original key>`）
3. 把儲存桶返回的校驗和與帳本中的值進行比較
4. 由人批准一致檔案的清單。批准會以 `APPROVED` 記錄在帳本中；批准者與啟動執行的主體相同時會被拒絕（預設；比較的是申報的值，不是主體的證明）
5. 確認 Access Point 的 ETag 和大小仍與帳本相同後，只刪除帳本中為 `APPROVED` 的檔案

恢復時，先在帳本中查詢檔案，在儲存桶中請求恢復，等待完成後用 `CopyObject` 複製回 Access Point，再把每個恢復的檔案讀回，與帳本的 SHA-256 和 CRC64NVME 比較。
本模式不使用 S3 Object Lock、S3 Glacier Vault Lock、AWS Backup Vault Lock、SnapLock 和快照鎖定，模板中也沒有寫入。因為不設定保留期限，所以對歸檔用儲存桶中的物件，只要有權限就可以刪除。
本模式的前提，以及與其他方式的比較，見[轉移到歸檔類別的 9 種機制的比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md)。
## 已測量和未測量的內容
| 類別 | 內容 |
|---|---|
| 各組成部分已在實際環境中各確認 1 次（記錄在上述比較資料中，2026-11-24 和 2026-11-26，ap-northeast-1，第 1 代 `SINGLE_AZ_1`，ONTAP 9.19.1P4D1，UNIX 樣式磁碟區，Access Point 使用者為 UNIX root） | 給 `CopyObject` 指定 `ChecksumAlgorithm=SHA256` 後，儲存桶的 `ChecksumSHA256` 為 `FULL_OBJECT`，與檔案的 SHA-256 一致（最大 8 MiB）。5.5 GiB 的分段上傳中 SHA-256 變為 `COMPOSITE`，CRC64NVME 為 `FULL_OBJECT` 且一致。使用舊 ETag 的 `--copy-source-if-match` 返回 `PreconditionFailed`。Access Point 的 `DeleteObject` 不支援 `If-Match`。在 Step Functions 的 SDK 整合中，可以把 Access Point 別名傳給 `Bucket` |
| 在本儲存庫中確認 | 使用 moto 的單元測試，以及狀態機和 IAM 結構的測試。未連接 AWS。上述實機端到端執行中發現的 7 個缺陷（ONTAP REST 函數的呼叫權限、TLS 驗證、重複恢復請求的錯誤名稱、狀態機的日誌寫入權限、`HeadObject` 的 403、告警的發佈權限）已透過能夠重現它們的測試修復 |
| 在包含 5.5 GiB 的 7 個檔案的執行中各確認 1 次（2026-11-26，與上述相同的環境，`selection=ATIME`，`GLACIER`，7 個檔案） | 透過 ONTAP REST API 按 `accessed_time` 選擇，並獲取 uid、gid、mode、mtime、atime（根是磁碟區的根，路徑開頭沒有斜槓；`unix_permissions` 以整數 `640` 返回）。Distributed Map 的 `ItemReader` 和 `ResultWriter`。用 Fargate 進行 5.5 GiB 的分段複制（帶 `CopySourceIfMatch`，CRC64NVME 與帳本一致）。在 Lambda 中對 5.3 GB（約 4.94 GiB）計算雜湊（69.8 秒，設定記憶體 2048 MB，使用 152 MB）。第二份副本。批准後的刪除。等待批准期間在 NFS 上改寫的檔案變為 `CHANGED`，沒有被刪除。拒絕批准後什麼都沒有被刪除。用 `Expedited` 恢復（含 5.5 GiB），恢復的 6 個檔案 SHA-256 一致（7 個檔案中剩下的 1 個已被改寫，既沒有被刪除也沒有被恢復）。用 `reapply.sh` 恢復 uid、gid、mode、mtime |
| 在確認排除與批准的執行中各確認 1 次（2026-11-26，相同環境，`GLACIER`，開啟第二份副本。dry run 使用 `selection=ATIME`，正式執行使用 `selection=MTIME` 並從 ONTAP REST 取得屬性。檔案從 64 B 到 1 MiB，另有 1 個 51 GiB 的稀疏檔案） | 包含 5.5 GiB 的 7 個檔案的執行中沒有的項目的確認。`maxFiles=50` 時，3 個 64 B 的檔案和 1 個 131,071 B 的檔案低於最小大小而被排除，131,073 B 的檔案被保留。`*.vmdk` 和法律保全前綴被排除。51 GiB 的稀疏檔案被記錄為 `SKIPPED_TOO_LARGE`，沒有被複製。重複使用的 `runId`，以及沒有 `requestedBy` 的正式執行輸入，都作為輸入錯誤而停止。與啟動者 ARN 相同的批准以 `APPROVAL_REFUSED` 結束，沒有刪除任何檔案。不經批准直接呼叫 `delete` 函數時返回 `NOT_APPROVED`，沒有刪除任何檔案。由不同的批准者批准後刪除了 3 個檔案，等待期間被改寫的 1 個檔案保留為 `CHANGED`。對為模擬中斷而設為 `DELETING` 的項目，同一個執行的重試記錄為 `DELETED`（`already gone on retry`），其他執行被拒絕，`reconcile` 記錄為 `DELETED`（該確認使用的是加入執行狀態檢查之前的程式碼；在目前的程式碼上，重試和恢復路徑只有單元測試涵蓋，沒有在實機上執行過）。恢復後 3 個檔案為 `RESTORE_VERIFIED`。告警（修復後）已發佈到經 KMS 加密的主題 |
| 在確認直接呼叫的檢查中各確認 1 次（2026-11-26，相同帳戶和 Access Point，`selection=MTIME`，`GLACIER`，無 Fargate，8 個 256 KiB 的檔案，`MapConcurrency=1`） | 批准之後立即停止執行，留下了 7 個 `APPROVED` 項目。用其他執行的 `claim` 直接呼叫 `delete` 函數，返回 `NOT_APPROVED`（`approval not current`）。修復之前，把已停止執行本身的 ARN 作為 `claim` 的呼叫，使 1 個檔案變為 `DELETED`。加入執行狀態的檢查之後，同樣的呼叫返回 `NOT_APPROVED`（`claiming execution is not running`）。`reconcile` 把 7 個項目恢復為 `VERIFIED`。在執行中的執行裡正常刪除，7 個檔案變為 `DELETED`。批准之後和拒絕之後，任務權杖的參數都已被刪除。權杖使用堆疊的 KMS 金鑰加密 |
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
確認排除與批准的執行（2026-11-26，小檔案，開啟第二份副本，`MapConcurrency=2`）的狀態轉換，各執行 1 次；會隨檔案大小和路徑而變化。

| 執行 | 檔案數 | 耗時 | 狀態轉換（父 + 子 Map 執行） | 每個檔案 |
|---|---|---|---|---|
| dry run `e2e2-dry1` | 4 | 66 秒（含等待批准約 20 秒） | 12 + 60 = 72 | 18 |
| 正式執行 `e2e2-real2`（3 個已刪除，1 個 `CHANGED`） | 4 | 45 秒（含等待批准） | 14 + 64 = 78 | 19.5 |
| 恢復 `e2e2-rest2`（Expedited，含核對，1 個 `EXISTS`） | 4 | 192 秒 | 4 + 52 = 56 | 14 |
### 端到端執行中發現並修復的缺陷
均已透過能夠重現的測試修復。
| # | 現象 | 原因與修復 |
|---|---|---|
| 1 | `selection=ATIME` 的執行在選擇階段失敗 | 歸檔狀態機的角色沒有對 ONTAP REST 函數的 `lambda:InvokeFunction`。已添加權限 |
| 2 | ONTAP REST 函數因 `CERTIFICATE_VERIFY_FAILED` 失敗 | 始終驗證 TLS，但 FSx for ONTAP 管理端點的證書不是由公共 CA 簽發。已添加參數 `OntapVerifySsl`（預設 `false`） |
| 3 | 重複提交恢復請求被當作檔案失敗 | Step Functions 的 SDK 集成把 `RestoreAlreadyInProgress` 以 `S3.S3Exception` 返回，因此與 `S3.RestoreAlreadyInProgressException` 的 `Catch` 不匹配。已改為把進行中的恢復送入等待完成的循環 |
確認排除與批准的執行（2026-11-26）又發現並修復了 3 個缺陷。

| # | 現象 | 原因與修復 |
|---|---|---|
| 4 | 部署失敗，出現 `The state machine IAM Role is not authorized to access the Log Destination` | 狀態機的角色缺少執行日誌所需的 `logs:CreateLogDelivery` 及相關權限。已添加 |
| 5 | 刪除重試和 `reconcile` 對已刪除的檔案執行 `HeadObject` 時收到 403 | 對沒有 `s3:ListBucket` 的呼叫者，對不存在的鍵執行 `HeadObject` 返回 403 而不是 404。已在 IAM 和 Access Point 策略中，為 `delete` 和 `restore` 函數添加 `s3:ListBucket` |
| 6 | CloudWatch 告警通知失敗，出現 `CloudWatch Alarms is not authorized to perform: SNS:Publish` | 金鑰策略允許 CloudWatch，但主題策略只允許 EventBridge。已添加 `cloudwatch.amazonaws.com` 的陳述式 |
| 7 | 不使用 Fargate（`FargateImageUri` 為空）的部署因 `is not authorized to create managed-rule` 失敗（確認直接呼叫的檢查） | 兩個定義都含有 `ecs:runTask.sync` 狀態，建立狀態機時會檢查角色的 `events:PutRule` 等權限。該權限位於 `UseFargate` 條件之內。已去掉該條件 |
### 端到端執行中得知的行為
這些行為沒有作為缺陷處理。
- 在 `selection=ATIME` 下，本模式自身的讀取會更新 `accessed_time`。用 `dryRun=true` 執行一次後，計算雜湊的讀取使每個檔案的 atime 變為執行時間，因此用相同輸入執行 `dryRun=false` 不會選中任何檔案（在 dry run 之後接著正式執行時，以 0 個檔案結束）。若要在 dry run 之後立即對相同的候選正式執行，請使用 `selection=MTIME`（`LastModified` 不會因讀取而改變）
- 關於 ETag，官方的說明和本環境的測量如下。官方頁面（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)，2026-11-26 閱讀）寫道 "The ETag reflects changes only to the contents of an object, not its metadata"。在本環境的 1 次測量中，大小和 mtime 相同、內容不同的 3 個檔案返回了相同的 ETag。因此本模式認為，刪除前對 ETag 和大小的確認，無法發現大小和 mtime 都不變的內容變更。在等待批准期間，大小相同但 mtime 更新的改寫被檢測到了（第一次執行的步驟 3，以及第二次正式執行） [E-023]
- 透過 Access Point 刪除目錄中的最後一個檔案時，變空的上級目錄也會一併消失（在 `arc-e2e/large/` 上確認）。恢復時的 `CopyObject` 會重新建立該目錄
- 恢復後的檔案擁有者為 0:1，模式為 644，修改時間為恢復的時間。在以 NFS 掛載了磁碟區的主機上，以 root 執行生成的 `reapply.sh` 後，恢復為原來的 uid、gid、mode、mtime（1234:5678、640、2020-01-02 03:04:05），內容的 SHA-256 沒有變化
- 當歸檔儲存桶中有 `CHANGED` 檔案的副本時，恢復狀態機也會選擇該檔案。如果 Access Point 上已有相同的鍵，則保留為 `EXISTS`，不覆蓋（在確認排除與批准的執行的恢復中確認過 1 次）
- 5.5 GiB 檔案的 `Expedited` 恢復請求被接受，並在約 4 分鐘內完成
### 未確認的事項
- 大量檔案時的耗時和費用。其他並行設定下檔案系統的吞吐量和用戶端延遲
- `Standard` 和 `Bulk` 恢復的完成等待（只執行了 `Expedited`）
- `S3.SlowDownException` 的重試（未觀察到 SDK 整合返回的名稱，可能出現與缺陷 3 同類的不匹配）
- CloudTrail 資料事件中的刪除和批准記錄。只有在追蹤啟用了資料事件時，才會記錄 S3 資料事件（`DeleteObject` 等）。本次執行沒有確認帳戶的追蹤是否包含此 Access Point 的資料事件。`SendTaskSuccess` 是管理事件，它的記錄也沒有確認
- 批准的拒絕和接受，是用同一個 SSO 主體在批准輸出中申報不同的 ARN 來比較的。批准者的值是申報的，因此不同的 IAM 主體應該得到相同的結果，但沒有使用真正的第二個主體
- 複製和恢復超過 50 GiB 的檔案（只用稀疏檔案確認了它們被排除在選擇之外）
- NTFS 磁碟區、非 root 使用者、第 2 代、Multi-AZ
- 恢復中除了不選擇 `CHANGED` 檔案之外的 `EXISTS` 路徑（NFS 上已有同名檔案的情況）
- 等到 `ApprovalPendingAlarm` 實際變為 `ALARM`（只確認了指標已發佈）
- 有 1 次候選為 0 個的情況原因不明。在用 `touch -d` 重設 atime 約 10 秒後的執行中沒有候選。約 17 分鐘後的確認返回了 2020 年的值，其他確認也返回了 6 個檔案。未能確定原因，也沒有再次出現
- 在實機上執行刪除的重試和恢復路徑（`DELETING`，相同的 `claimedBy`）。上面的重試確認使用的是加入執行狀態檢查之前的程式碼。在目前的程式碼上，該路徑只有單元測試涵蓋
### 刪除前確認中殘留的寫入視窗
刪除前的確認中仍殘留一個寫入視窗。Access Point 的 `DeleteObject` 不支持條件刪除，因此在用 `HeadObject` 確認之後到刪除之前被改寫的情況無法檢測。該視窗相當於一次 API 呼叫往返。
## 處理流程
### 歸檔
輸入中 `olderThanDays` 為必填，`dryRun` 的預設值為 `true`。`RequireSeparateApprover=true`（預設）時，`dryRun=false` 的執行需要在 `requestedBy` 中填入啟動者主體的 ARN。
| 步驟 | 處理 | 實現 |
|---|---|---|
| 1. 選擇 | `MTIME`：Access Point `ListObjectsV2` 的 `LastModified`。`ATIME`：ONTAP REST API 的 `accessed_time`（VPC 內的 Lambda）。套用排除條件（下表） | `select`、`ontap_rest` |
| 2. 記錄 | 把大小、ETag、SHA-256、CRC64NVME，以及可取得時的 uid、gid、mode、mtime、atime 寫入帳本。5 GiB 以下用 Lambda，超出部分用 Fargate | `record`、Fargate 任務 |
| 3. 複製 | 5 GiB 以下用 SDK 整合的 `copyObject`（`SHA256`，把帳本的 ETag 作為 `CopySourceIfMatch`）。超出部分用 Fargate 的分段複製（`CRC64NVME`） | Step Functions、Fargate |
| 4. 核對 | 把儲存桶 `HeadObject`（`ChecksumMode=ENABLED`）的大小和校驗和與帳本比較。不一致則保留為 `MISMATCH`，並排除在刪除物件之外 | `ledger` |
| 5. 第二份副本（可選） | 從 Access Point 複製到同一區域的另一個儲存桶，並做同樣的核對。不一致則排除在刪除物件之外 | Step Functions、`ledger` |
| 6. 批准 | 把一致的清單寫入 `manifests/<runId>.json`，透過 SNS 通知，並用 `waitForTaskToken` 等待。只有一份副本時，以及檔案無法恢復時，通知中會說明 | `approval` |
| 7. 記錄批准 | 僅在 `dryRun=false` 時執行。批准者與啟動者相同時拒絕。否則把清單中的每個檔案在帳本中從 `VERIFIED` 改為 `APPROVED`，並寫入 `manifests/<runId>-approval.json` | `approval` |
| 8. 刪除 | 只處理帳本中為 `APPROVED` 的檔案。逐個檔案確認 ETag 和大小，相同則 `DeleteObject`，不同則保留為 `CHANGED` | `delete` |
| 9. 記錄 | `manifests/<runId>-result.json` 和 EMF 指標（件數、位元組數、排除數）。仍有 `DELETING` 或 `APPROVED` 項目時為 `COMPLETED_WITH_ERRORS` | `summarize` |
即使 `dryRun=true`，也會執行到第 6 步。也就是說會進行複製，並產生歸檔類別的儲存費用（有最短儲存期限）。試用時請把 `maxFiles` 設小。不會執行刪除。
帳本的狀態按 `SELECTED`、`RECORDED`、`COPIED`、`VERIFIED`、`APPROVED`、`DELETING`、`DELETED`、`RESTORED`、`RESTORE_VERIFIED` 的順序推進，中途的出口是 `CHANGED`、`MISMATCH`、`FAILED`、`SKIPPED_TOO_LARGE` 和 `RESTORE_MISMATCH`。只有 `APPROVED` 的檔案（要求第二份副本時，還須完成第二份副本的核對）才能被刪除。

已使用過的 `runId` 是輸入錯誤。要繼續被中斷的執行，請給出相同的 `runId` 並加上 `"resume": true`（見下文「從中斷的刪除中恢復」）。歸檔鍵中包含 `runId`，因此 dry run 與正式執行，或改寫後的重新歸檔，不會互相覆蓋物件。沒有版本控制時，覆蓋會刪除先前的物件，在有最短儲存期限的類別中，這可能產生提前刪除費用。

選擇時排除的內容：

| 條件 | 預設 | 理由 |
|---|---|---|
| 超過 50 GiB | 被排除，並在帳本中記錄為 `SKIPPED_TOO_LARGE`。`allowOversize: true` 會將其納入 | 官方頁面（[Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)，2026-11-26 閱讀）寫道 "Maximum object size is 50 GiB for uploads, but you can download objects larger than that"。恢復是透過 Access Point 寫入，因此本模式無法把更大的檔案恢復到那裡（可以直接從儲存桶下載） [E-021] |
| 小於 `MinFileSizeBytes` | 131,072 位元組（128 KiB）。輸入的 `minSizeBytes` 可以更改 | 根據 [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)（2026-11-26 閱讀），Standard-IA 和 Glacier Instant Retrieval 每個物件至少按 128 KB 計費，Glacier Flexible Retrieval 和 Deep Archive 每個物件另加 40 KB 的中繼資料（32 KB 按該類別的費率，8 KB 按 Standard 的費率）。對小檔案來說，這比資料本身還大 |
| `ExcludePatterns`（glob）、`ExcludePrefixes` | `ExcludePatterns` 為下面的清單，`ExcludePrefixes` 為空 | 堆疊的值始終適用；輸入的 `excludePatterns` 和 `excludePrefixes` 只能追加。法律保全的前綴請放在這裡 |

請始終排除 Iceberg、Delta 或 Hive 資料表的資料檔案、執行中的資料庫的檔案，以及虛擬機器磁碟映像（`*.vmdk`、`*.vhd`、`*.qcow2` 等）。本模式逐個移動檔案，不瞭解資料表的中繼資料，也不知道哪個行程正在開啟檔案。請用資料表自身的功能（分離分割區、使快照過期）整理資料表，只以整理後剩下的路徑為物件。是否處於法律保全，由貴公司的法務部門決定，本模式不做此判斷。
`ExcludePatterns` 的預設值是起點而不是完整清單，列出的是容易造成實際事故的檔案類型。虛擬機器磁碟映像（`*.vmdk`、`*.vhd`、`*.vhdx`、`*.vdi`、`*.qcow2`）在虛擬機器開啟期間持續寫入，逐個檔案複製會得到損毀的副本。資料庫的資料和日誌檔案（SQL Server 的 `*.mdf`、`*.ndf`、`*.ldf`，MySQL InnoDB 的 `*.ibd`，Oracle 的 `*.dbf`）由資料庫開啟並寫入。資料表格式的中繼資料目錄（Delta 的 `_delta_log/`、Hudi 的 `.hoodie/`、Iceberg 的 `metadata/`）保存資料檔案的清單，只移動資料檔案會破壞資料表。比對區分大小寫（`*.VMDK` 不相符）。名為 `metadata/` 但不是 Iceberg 的目錄也會被排除。`*.parquet` 這類資料表的資料檔案不在預設值中，請加入適合您環境的模式。只有磁碟區上完全沒有這類檔案時，才可以設為空。
### 恢復
輸入為 `runId`，以及 `keys` 或 `prefix` 中的一個。可以指定 `tier`（預設 `Bulk`）和 `days`（預設 7）。
1. 在帳本中選擇 `DELETED` 的檔案。當歸檔儲存桶中有 `DELETING` 和 `CHANGED` 檔案的副本時，這些檔案也會被選中（以便恢復被中斷的刪除所留下的項目）
2. 如果 Access Point 上已存在相同的鍵，則保留為 `EXISTS`，不覆蓋
3. 對 S3 Glacier Flexible Retrieval 和 S3 Glacier Deep Archive 的物件請求 `RestoreObject`（S3 Glacier Instant Retrieval 不需要）
4. 完成等待採用輪詢（每隔 `RestorePollMinutes` 讀取 `HeadObject` 的 `Restore` 標頭，到 `RestoreMaxWaitHours` 時放棄）。不使用 EventBridge 的 `Object Restore Completed`。儲存桶的 EventBridge 通知已啟用，因此以後可以切換
5. 從儲存桶向 Access Point 執行 `CopyObject`（超過 5 GiB 用 Fargate）。帳本設為 `RESTORED`
6. 透過 Access Point 把恢復的檔案讀回，計算雜湊，與帳本的 SHA-256、CRC64NVME 和大小比較（超過 5 GiB 用 Fargate）。一致則為 `RESTORE_VERIFIED`，不一致則為 `RESTORE_MISMATCH`
7. 只針對 `RESTORE_VERIFIED` 的檔案，寫出用於重新設定屬性的指令碼 `manifests/<runId>-reapply.sh`

恢復後的檔案，擁有者為 0:1，模式為 644，修改時間為恢復的時刻（上述環境中的確認）。原來的值無法透過 `CopyObject` 恢復。
`RESTORE_MISMATCH` 的檔案預設不會被選為恢復對象：Access Point 上的副本與帳本不一致，若直接選中會作為 `EXISTS` 保留。要重做時，在恢復輸入中加上 `"retryMismatched": true`（JSON 布林值）。只有此時，該 `runId` 的帳本目前為 `RESTORE_MISMATCH` 的項目才會被選中，並用儲存桶中的副本覆寫 Access Point 上不一致的副本。其他狀態的項目即使指定了該旗標，也不會覆寫既有檔案。覆寫之後，同樣的回讀會得到 `RESTORE_VERIFIED` 或 `RESTORE_MISMATCH`。
### 從中斷的刪除中恢復
Lambda 在刪除途中停止，或重試次數用盡，可能使帳本中的項目停留在 `DELETING` 或 `APPROVED`。結果中會以 `COMPLETED_WITH_ERRORS`、`stuckDeleting` 和 `notDeleted` 顯示，並觸發 `FilesStuckDeletingAlarm`。用相同的 `runId` 和 `"resume": true` 啟動歸檔狀態機，會執行 `reconcile`，按下表處理這些項目，然後對剩下的檔案請求新的批准。
| 帳本 | Access Point | 結果 |
|---|---|---|
| `DELETING` | 沒有檔案 | `DELETED`（刪除已經發生；`reconciled: true`） |
| `DELETING`、`APPROVED` | 檔案存在，ETag 和大小與帳本相同 | 回到 `VERIFIED`；刪除需要新的批准 |
| `DELETING`、`APPROVED` | 檔案存在，與帳本不同 | `CHANGED` |
| 任一 | 持有該項目的執行仍在進行 | 不處理 |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
需要找回停留在 `DELETING` 的項目時，由恢復狀態機從歸檔儲存桶的副本中恢復它。
## 批准操作
批准通知中不包含權杖。權杖在 AWS Systems Manager Parameter Store 的 SecureString（`/<stack>/approvals/<runId>`）中。批准的人是具有讀取該參數的權限和 `states:SendTaskSuccess` 權限的人。
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# 拒絕：
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
批准之後，`approval` 函數會把 `approver` 與啟動輸入中的 `requestedBy` 比較（`RequireSeparateApprover=true`，預設）。相同的主體會使執行以 `APPROVAL_REFUSED` 結束，不會把任何檔案標為 `APPROVED`。角色 ARN 和該角色的工作階段 ARN 視為同一個主體。否則清單中的每個檔案在帳本中成為 `APPROVED`，並記錄 `approvedBy`、`approvedAt` 和執行 ARN。`delete` 函數只刪除有這條記錄的檔案；直接呼叫它，也不會刪除沒有記錄的檔案。

`approver` 和 `requestedBy` 都是呼叫者自行申報的值。帳本的 `deletedBy` 取自它的 `approvedBy`。實際啟動和批准的主體記錄在 CloudTrail 的 `StartExecution` 和 `SendTaskSuccess` 事件中。若要按主體保證職責分離，請在 IAM 中分開啟動和批准的角色。 啟動者與批准者的比較，是對兩個自行申報的值的比較。它不強制由其他主體批准，本文件也不宣稱它能強制。事後的控制是 CloudTrail 的 `userIdentity`：核對執行 `StartExecution` 和 `SendTaskSuccess` 的主體。
### 批准的有效範圍與權杖的處理
`delete` 函數只刪除這樣的項目：帳本為 `APPROVED`，`approvalExecutionArn` 與目前的執行相同，且 `approvedAt` 在 `ApprovalValidityHours`（預設 24 小時）以內。批准之後停止執行會留下 `APPROVED` 項目，但它們與其他執行的 `claim` 不一致，因此直接呼叫 `delete` 函數也會得到 `NOT_APPROVED`。超過期限的批准同樣被拒絕。留下的項目由 `reconcile` 恢復為 `VERIFIED`。 即使 `claim` 是已停止的執行本身的 ARN（帳本中有記錄），只要該執行不是 `RUNNING`，也會被拒絕。無法讀取執行狀態時同樣拒絕。

任務權杖在批准成立時（`approval` 函數）、拒絕與啟動者相同主體的批准時，以及批准被拒絕、逾時或執行失敗之後（`summarize`）刪除。沒有到達 `summarize` 而殘留的權杖，由 `watchdog` 在超過批准逾時加 1 小時後刪除。權杖使用堆疊的客戶受管 KMS 金鑰（輸出 `ApprovalTokenKeyArn`）加密，因此讀取它需要 `ssm:GetParameter`，以及該金鑰的 `kms:Decrypt`。

批准者角色的 IAM 政策範例。IAM 無法為 `states:SendTaskSuccess` 和 `states:SendTaskFailure` 指定資源（[Step Functions 授權參考](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsstepfunctions.html)，2026-11-26 查閱） [E-024]，所以不能把它們限定在此狀態機的執行上。持有權杖的人就能回應該執行，因此能縮小的是讀取權杖的途徑。不要給這個角色授予 `StartExecution`。
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApprovalToken",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/<stack>/approvals/*"
    },
    {
      "Sid": "DecryptApprovalToken",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "<ApprovalTokenKeyArn>",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.<region>.amazonaws.com"}}
    },
    {
      "Sid": "ReportApproval",
      "Effect": "Allow",
      "Action": ["states:SendTaskSuccess", "states:SendTaskFailure"],
      "Resource": "*"
    }
  ]
}
```
## 重新設定屬性
恢復的最後會寫出 `manifests/<runId>-reapply.sh`。在透過 NFS 掛載了該磁碟區的主機上，以 root 身份執行。
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
指令碼只包含 `chown`、`chmod` 和 `touch -d`，帳本中的值按嚴格的格式檢查，鍵透過 shell 引用成為一個單詞。不符合格式的值會變成註釋，不會被執行。ONTAP REST API 能否設定所有者、組、模式和修改時間尚未確認，因此未實現這條路徑。
## 部署
### 前提
- Access Point 的別名和 ARN 兩者都需要（IAM 需要兩種形式。僅有別名的策略可以部署，但執行時會被拒絕）
- Access Point 策略。此堆疊不建立 Access Point（以參數接收既有的 Access Point），也不管理其策略，因此在部署後依下方步驟附加。未附加時，第一次 S3 呼叫會在執行時被拒絕
- 歸檔用儲存桶的名稱（由堆疊建立。`DeletionPolicy: Retain`、Block Public Access、預設 SSE-S3、KMS 可選、啟用 EventBridge 通知、必須使用 TLS）
- 僅在使用 `selection=ATIME` 和屬性記錄時需要：VPC、子網、保存 ONTAP 憑據的金鑰、管理端點、磁碟區 UUID、`OntapVerifySsl`。FSx for ONTAP 管理端點的憑證不是由公共 CA 簽發，因此預設值為 `false`（不驗證）。此時 ONTAP 憑據會透過不對對端進行認證的連線發送（路徑在 VPC 內）。設為 `true` 時驗證失敗，執行在選擇階段停止（在實機上觀察到）。VPC 內的 Lambda 需要到 Secrets Manager 和 S3 的路徑（VPC 端點或 NAT）
- 僅在處理超過 5 GiB 的檔案時需要：放在 ECR 中的映像。Access Point 是 Internet-origin，因此 Fargate 的子網需要 NAT 閘道或公網 IP
- 已確認的通知訂閱。SNS 電子郵件訂閱在收件者點擊確認連結之前不會生效；沒有它，就沒有人會看到批准請求
### 步驟
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # 替換每一個 <PLACEHOLDER>
sam build && sam deploy
```
部署之後，附加 Access Point 策略。該指令碼根據堆疊輸出中的角色 ARN 生成策略：只把 `s3:DeleteObject` 授予 `delete` 函數的角色，只把 `s3:PutObject` 授予恢復用的角色。
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # no PendingConfirmation left
```
如果 Access Point 已有策略，這會取代它；請先合併現有的陳述式。
使用 Fargate 時，在儲存庫根目錄建置映像，推送到自己的 ECR 儲存庫，並指定給 `FargateImageUri`。
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
首次執行時，使用省略 `dryRun`（即為 `true`）的輸入。
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
要執行到刪除，請把 `"dryRun": false` 作為 JSON 布林值傳入，並在 `requestedBy` 中填入啟動者主體。字串 `"false"` 會成為輸入錯誤，不會執行刪除。
## 目錄結構
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, ledger, 9 Lambda functions, 2 state machines, Fargate (optional), alarms
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
領域邏輯（校驗和、輸入檢查、帳本、恢復後的核對）位於 [`shared/archive_verify/`](../../../shared/archive_verify/)，在 `shared/tests/` 中測試。對 Access Point 的讀寫都經過 `shared/s3ap_helper.py`。
## 本地測試
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
為了確認刪除判定被破壞時能夠被檢測到，用去掉 ETag 比較的樁程式碼把 `test_does_not_delete_when_etag_changed` 和 `test_does_not_delete_when_size_differs_but_etag_equal` 執行了 1 次，2 個測試都以 `assert 'DELETED' == 'CHANGED'` 失敗。批准記錄的檢查和 50 GiB 的排除是先寫測試的：在實作之前，對先前的程式碼執行了 1 次，分別以 `assert 'DELETED' != 'DELETED'` 和 `KeyError: 'skippedTooLarge'` 失敗。
## Success Metrics
### Outcome
把很少被讀取的檔案，經過核對和人的批准後轉移到 S3 Glacier 系列的類別，降低磁碟區的使用量。轉移後的檔案可以從帳本中查詢並恢復。
### Metrics
目標值由使用者決定。這裡不給出數值。
| 類別 | 指標 | 定義 |
|---|---|---|
| Business Outcome | 釋放的容量 | 執行前後磁碟區已用空間的差（整理快照之後）。`bytesDeleted`（`-result.json`）是已刪除檔案的總大小，不是釋放的空間：只要快照還在，磁碟區的使用量就不會下降，對於壓縮或去重的資料，釋放的空間也小於邏輯大小 |
| Business Outcome | 預期的每月儲存節省額 | （從容量池移出的 GB 數 × 價格差）−（歸檔類別的儲存費用、每個物件的額外開銷、取回費用）。價格見下文「成本估算」 |
| Technical KPI | 核對一致率 | `VERIFIED` ÷（`VERIFIED` + `MISMATCH`） |
| Technical KPI | 未刪除的件數 | `CHANGED`、`MISMATCH` 和 `FAILED` 的合計 |
| Technical KPI | 恢復核對一致率 | `RESTORE_VERIFIED` ÷（`RESTORE_VERIFIED` + `RESTORE_MISMATCH`） |
| Quality KPI | 未經批准而被刪除的件數 | 必須為 0。統計 `approvedBy` 或 `approvedAt` 為空的 `DELETED` 項目 |
| Cost KPI | 每次執行的 Lambda、Fargate、DynamoDB、S3 請求、狀態轉換和歸檔類別的儲存費用 | 用「成本估算」中的公式，根據實測的 `dryRun=true`（較小的 `maxFiles`）執行結果估算 |
| Go / No-Go | 技術面：在實際環境的執行中，所有已複製的檔案都變為 `VERIFIED`，有意製造的 `CHANGED` 檔案不會被刪除，啟動者的自我批准被拒絕，恢復的檔案為 `RESTORE_VERIFIED`。業務面：預期的節省額超過營運成本（批准的工作量、處理恢復請求）；恢復請求的受理窗口和目標回應時間（含該類別的恢復時間）已確定；使用者已被告知 | 在全部滿足之前，不要對正式環境磁碟區使用 `dryRun=false`。請先指定每一項由誰決定（資料所有者、批准者、營運負責人） |

PoC 的規劃和上線前的確認，見 FSx for ONTAP Adoption Playbook 的[上線前審查檢查清單](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md)和[遷移前盤點](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md)（均為日文）。就本模式的 PoC 而言，把 `maxFiles` 依次提高到 20、200、2,000，並記錄父執行的耗時、狀態轉換和 Fargate 秒數，即可得到每個檔案的值。 PoC 規劃表見 Playbook 的[在自己的環境中開始](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/archive-use-cases-and-integrations.md#自環境での始め方)（日文）。
### Measurement Method
Step Functions 的執行歷史和日誌（`/aws/vendedlogs/states/<stack>-archive` 和 `-restore`，不含執行資料）、`manifests/<runId>-result.json`、`manifests/<runId>-approval.json`、CloudWatch 的 EMF 指標（`FilesVerified`、`FilesDeleted`、`FilesMismatch`、`FilesChanged`、`FilesFailed`、`FilesStuckDeleting`、`BytesVerified`、`BytesDeleted`、`RestoreVerified`、`RestoreMismatch`、`ApprovalPendingHours`）、帳本。

告警（全部發送到通知主題）：

| 告警 | 條件 |
|---|---|
| `ArchiveExecutionsFailedAlarm`、`RestoreExecutionsFailedAlarm` | 5 分鐘內有 1 個以上失敗、逾時或被中止的執行 |
| `ApprovalPendingAlarm` | 批准請求的等待時間超過 `ApprovalAlarmHours`（預設 24） |
| `FilesStuckDeletingAlarm` | 有執行結束時仍有 `DELETING` 或 `APPROVED` 的項目 |
| `FilesMismatchAlarm` | 歸檔的副本不一致（`MISMATCH`） |
| `RestoreMismatchAlarm` | 恢復的檔案與帳本不一致 |
通知主題使用客戶管理的 KMS 金鑰加密。AWS 受管金鑰（`alias/aws/sns`）的金鑰策略無法編輯，而 EventBridge 和 CloudWatch 告警要向加密的主題發佈訊息，只能使用允許服務主體執行 `kms:GenerateDataKey*` 和 `kms:Decrypt` 的客戶管理金鑰（[Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html)，2026-11-26 閱讀）。第二次執行確認了 EventBridge 的失敗通知和告警通知都能送達。 [E-022]
## Performance Considerations
預設的並行度依據下面的 1 次測量。其餘是設計上的因素，沒有測量。
- 原始檔會被讀取 2 次。第 1 次是為計算雜湊而透過 Access Point 讀取，第 2 次是 `CopyObject` 在伺服器端讀取。會產生讀取請求費用，位於容量池中的資料還會產生容量池的讀取費用
- 並行度為 `MapConcurrency`（歸檔和恢復都預設為 1）。在 1 次測量中，1 個 Lambda 函數透過 Access Point 在 69.8 秒內讀取了 5.3 GB（約 4.94 GiB），單一串流約 76 MB/s，約為本環境 128 MBps 吞吐量容量的 60%。2 個串流約為 152 MB/s，超過該容量。每個檔案被讀取 2 次，而且同一個磁碟區還在為使用者提供服務，因此預設值為 1。沒有測量並行讀取。提高之前，請在執行期間觀察檔案系統的 `DataReadBytes` 和用戶端延遲
- `LargeFileThresholdBytes` 的預設值 5 GiB 來自單次請求 `CopyObject` 的上限。以上述速度計算，Lambda 的 15 分鐘大約可以處理 63 GiB，但這只是 1 個資料點
- 清單會把 `ListObjectsV2` 的全部結果載入一個 Lambda 的記憶體。超過數百萬件時，請用 `prefix` 分開處理
- `selection=ATIME` 以深度優先遍歷目錄。掃描上限為 200,000 個項目（`ONTAP_SCAN_LIMIT`），超出時返回到中途為止的結果
- 恢復的等待時間由類別和 `tier` 決定。AWS 記載 S3 Glacier Deep Archive 在 Standard 下 12 小時以內，在 Bulk 下 48 小時以內。`RestoreMaxWaitHours` 的預設值為 72。對於等待時間長的類別，把 `RestorePollMinutes` 設大可以減少輪詢產生的狀態轉換
- Fargate 任務受 `FargateTimeoutSeconds`（預設 7200 秒）限制。每個 Task 都有 `TimeoutSeconds`，逾時會重試
## 成本估算
沒有測量帳單。以下是實測的使用量，以及用於估算的公開的每物件條件。
兩次執行中每個檔案的狀態轉換（各執行 1 次）：

| 執行 | 每個檔案的狀態轉換 | 來源 |
|---|---|---|
| 歸檔 dry run | 17（119 ÷ 7），18（72 ÷ 4） | 包含 5.5 GiB 的 7 個檔案的執行、確認排除與批准的執行 |
| 歸檔正式執行（含刪除） | 18（127 ÷ 7），19.5（78 ÷ 4） | 同上 |
| 恢復（`Expedited`；確認排除與批准的執行含核對） | 18（107 ÷ 6），14（56 ÷ 4） | 同上 |
等待時間長的類別，每次輪詢都會增加狀態轉換。
每個物件的儲存條件（[Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare)，2026-11-26 閱讀）：

| 類別 | 最短儲存期限 | 每個物件的額外開銷、最小計費大小 |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 天 | 最小計費物件大小 128 KB |
| S3 Glacier Flexible Retrieval | 90 天 | 40 KB 的中繼資料（32 KB 按該類別的費率，8 KB 按 S3 Standard 的費率） |
| S3 Glacier Deep Archive | 180 天 | 40 KB 的中繼資料（拆分相同） |
公式：每月費用 ≈ 檔案數 × 每個檔案的狀態轉換 × 每次轉換的價格 + Lambda 和 Fargate 的執行時間 × 價格 + 檔案數 ×（`CopyObject`、`HeadObject`、`DeleteObject` 等的請求價格）+（資料 + 檔案數 × 額外開銷）× 類別價格 + 恢復時的取回費用。價格請從 [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) 和 [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) 按您的區域和日期取得；此處不寫價格。
## Governance Note
> 本模式提供技術架構方面的指導。它不是法律、合規或監管方面的建議。請組織諮詢合格的專業人士。
- 核對結果和批准是供人做最終判斷的輔助訊號。未使用 AI
- 本模式不滿足保留期限和不可變性的要求。因為沒有使用 Object Lock 等功能，所以有權限就可以刪除
- 輸出分類：帳本和清單包含檔案路徑、大小、雜湊、屬性。路徑中可能包含人名或患者、案件的識別碼，因此輸出預設帶有 `data_classification` 的 `RESTRICTED`（`shared/data_classification.py` 中的 "Restricted — Limited access"）。當資料本身的分類更嚴格時，請把 `DataClassification` 參數設為該分類。分類由您決定。檔案內容會進入歸檔用儲存桶，請按與原始資料相同的分類處理
- Human Review：每次執行都必須批准。沒有基於置信度的自動批准。預設情況下，啟動者和批准者為同一主體時，不會刪除任何檔案。這是對申報值的比較，不是主體的證明；事後的控制手段是 CloudTrail 的 `userIdentity`
- IAM：在 Access Point 上持有 `s3:DeleteObject` 的只有 `delete` 函數的角色，持有 `s3:PutObject` 的只有恢復狀態機和恢復用的 Fargate 任務角色。歸檔用的 Fargate 任務只負責複製，既不能刪除也不能覆蓋來源檔案。沒有任何主體可以刪除帳本項目
- 審計：批准和刪除會記錄在帳本（`approvedBy`、`approvedAt`、`requestedBy`、`deletedBy`、`deletedAt`）、`manifests/<runId>-approval.json`，以及 Step Functions 的歷史和日誌中。只有在追蹤啟用了 S3 資料事件時，CloudTrail 才會記錄刪除；本次執行沒有確認這一點
- 副本數：沒有第二份副本時，刪除之後歸檔儲存桶中的物件就是唯一的副本。批准通知中會說明這一點
## 限制與未確認事項
- 從 Access Point 直接複製到其他區域的儲存桶時返回了 `AccessDenied`（1 個 Access Point，1 次）。第二份副本僅以同一區域的儲存桶為物件
- 在 UNIX 樣式的磁碟區上確認。大小和 mtime 都不變的內容變更，無法透過 ETag 和大小的確認檢測到（參見「端到端執行中得知的行為」）。`chown` 是否會改變 ETag 尚未確認
- 屬性是透過目錄清單取得的。為了一個檔案要讀取整個父目錄，因此對大目錄會變慢
- 歸檔用儲存桶的版本控制不是 Object Lock。版本會保留，但有權限就可以刪除版本
- 超過 50 GiB 的檔案預設不會被選擇。用 `allowOversize: true` 納入時，它們無法恢復到 Access Point；請從儲存桶下載
- `requestedBy` 和 `approver` 是申報的值。請用 IAM 和 CloudTrail 按主體檢查職責分離
## 相關文件
- [Architecture (EN)](docs/architecture.en.md)
- [S3 Access Points 相容性備忘](../../../docs/s3ap-compatibility-notes.md)
- [轉移到歸檔類別的 9 種機制的比較](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md)（日文）

---

<!-- playbook-reading:start -->
## 上線前需要閱讀的內容

部署後才會遇到的限制如何轉化為設計決策，記錄在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一內容放在兩處時，停止更新的那份會比已修正的那份留存更久。

- [資料活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 透過存取點存取資料的限制（所有模式通用）
- [資料保護](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — 該模式的決策集中之處
- [建置](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上線前通讀（所有模式通用）
<!-- playbook-reading:end -->
