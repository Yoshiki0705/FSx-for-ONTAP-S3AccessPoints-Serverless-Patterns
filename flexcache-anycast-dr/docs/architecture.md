# FlexCache AnyCast / DR — アーキテクチャ詳細

## 1. シングルリージョン / 同一クラスタ内 FlexCache AnyCast

```mermaid
graph TB
    subgraph "FSx for ONTAP Cluster"
        ORIGIN[Origin Volume<br/>/vol/project_data]
        CACHE1[FlexCache 1<br/>/vol/cache_az1]
        CACHE2[FlexCache 2<br/>/vol/cache_az2]
    end
    subgraph "ルーティング層"
        R53[Route 53<br/>Weighted Routing]
    end
    subgraph "クライアント層"
        NFS1[NFS Client AZ-a]
        NFS2[NFS Client AZ-c]
    end
    subgraph "サーバーレス処理層"
        S3AP1[S3 AP (Cache 1)]
        S3AP2[S3 AP (Cache 2)]
        LAMBDA[Lambda<br/>Processing]
    end
    ORIGIN --> CACHE1
    ORIGIN --> CACHE2
    R53 --> CACHE1
    R53 --> CACHE2
    NFS1 --> R53
    NFS2 --> R53
    CACHE1 --> S3AP1 --> LAMBDA
    CACHE2 --> S3AP2 --> LAMBDA
```

**特徴**:
- 同一 FSx ファイルシステム内で Origin + FlexCache を構成
- Route 53 Weighted Routing で AZ 間の負荷分散
- 各 FlexCache に S3 AP を attach（要検証）してサーバーレス処理

## 2. マルチ AZ / マルチ POD 読み取りキャッシュ

```mermaid
graph TB
    subgraph "Primary AZ (ap-northeast-1a)"
        ORIGIN[FSx ONTAP<br/>Origin Volume<br/>Multi-AZ HA]
    end
    subgraph "AZ-a Compute"
        EC2_A[EC2 / EKS Pod<br/>AZ-a]
        LAMBDA_A[Lambda AZ-a]
    end
    subgraph "AZ-c Compute"
        CACHE_C[FSx ONTAP<br/>FlexCache<br/>AZ-c 最適化]
        EC2_C[EC2 / EKS Pod<br/>AZ-c]
        LAMBDA_C[Lambda AZ-c]
        S3AP_C[S3 AP]
    end
    ORIGIN -->|Cross-AZ<br/>データフェッチ| CACHE_C
    EC2_A -->|同一 AZ<br/>低レイテンシ| ORIGIN
    EC2_C -->|同一 AZ<br/>低レイテンシ| CACHE_C
    CACHE_C --> S3AP_C --> LAMBDA_C
    LAMBDA_A -->|S3 AP (Origin)| ORIGIN
```

**特徴**:
- FSx ONTAP Multi-AZ HA で Origin を保護
- 別 AZ のコンピュートは FlexCache 経由でアクセス
- Cross-AZ データ転送を最小化

## 3. オンプレ ONTAP Origin + AWS FSx for ONTAP Cache

```mermaid
graph LR
    subgraph "オンプレミス DC"
        ONPREM[ONTAP Cluster<br/>Origin Volume<br/>VIP/BGP AnyCast]
        NFS_ONPREM[NFS Clients<br/>オンプレ]
    end
    subgraph "AWS (ap-northeast-1)"
        direction TB
        DX[Direct Connect /<br/>VPN]
        FSX_CACHE[FSx for ONTAP<br/>FlexCache Volume]
        S3AP[S3 Access Point]
        SFN[Step Functions]
        LAMBDA[Lambda<br/>AI/ML Processing]
        BEDROCK[Amazon Bedrock]
    end
    ONPREM -->|Cluster Peering<br/>via DX/VPN| DX
    DX --> FSX_CACHE
    NFS_ONPREM --> ONPREM
    FSX_CACHE --> S3AP
    S3AP --> LAMBDA
    LAMBDA --> SFN
    SFN --> BEDROCK
```

**特徴**:
- オンプレ ONTAP が Origin（VIP/BGP AnyCast 利用可能）
- AWS 側は FSx for ONTAP FlexCache でホットデータをキャッシュ
- S3 AP 経由でサーバーレス AI/ML 処理
- Direct Connect / VPN でクラスタピアリング

## 4. マルチリージョン EDA/Media クラウドバースト

```mermaid
graph TB
    subgraph "Origin（東京 or オンプレ）"
        ORIGIN[ONTAP Origin<br/>EDA Tools + Libraries<br/>Render Assets]
    end
    subgraph "ap-northeast-1（東京）"
        FSX_TKY[FSx ONTAP<br/>FlexCache]
        S3AP_TKY[S3 AP]
        LAMBDA_TKY[Lambda<br/>EDA/Render Job]
        BATCH_TKY[AWS Batch<br/>Spot Instances]
    end
    subgraph "us-west-2（オレゴン）"
        FSX_PDX[FSx ONTAP<br/>FlexCache]
        S3AP_PDX[S3 AP]
        LAMBDA_PDX[Lambda<br/>EDA/Render Job]
        BATCH_PDX[AWS Batch<br/>Spot Instances]
    end
    subgraph "eu-west-1（アイルランド）"
        FSX_DUB[FSx ONTAP<br/>FlexCache]
        S3AP_DUB[S3 AP]
        LAMBDA_DUB[Lambda<br/>EDA/Render Job]
        BATCH_DUB[AWS Batch<br/>Spot Instances]
    end
    subgraph "ジョブスケジューラ"
        SCHED[Step Functions<br/>Job Router]
        R53[Route 53<br/>Latency-based]
    end
    ORIGIN --> FSX_TKY
    ORIGIN --> FSX_PDX
    ORIGIN --> FSX_DUB
    FSX_TKY --> S3AP_TKY --> LAMBDA_TKY --> BATCH_TKY
    FSX_PDX --> S3AP_PDX --> LAMBDA_PDX --> BATCH_PDX
    FSX_DUB --> S3AP_DUB --> LAMBDA_DUB --> BATCH_DUB
    SCHED --> R53
    R53 --> LAMBDA_TKY
    R53 --> LAMBDA_PDX
    R53 --> LAMBDA_DUB
```

**特徴**:
- 複数リージョンに FlexCache を配置
- ジョブスケジューラが最適リージョンにルーティング
- Spot Instance の可用性に応じてリージョン選択
- EDA Tools/Libraries は各リージョンの FlexCache にキャッシュ

## 5. MetroCluster/SVM-DR + FlexCache AnyCast 概念パターン

```mermaid
graph TB
    subgraph "サイト A（Primary）"
        MC_A[MetroCluster Node A<br/>or SVM-DR Primary]
        ORIGIN_A[Origin Volume]
        CACHE_A1[FlexCache A1]
        VIP_A[VIP / AnyCast IP<br/>※オンプレのみ]
    end
    subgraph "サイト B（Secondary）"
        MC_B[MetroCluster Node B<br/>or SVM-DR Mirror]
        ORIGIN_B[Origin Mirror]
        CACHE_B1[FlexCache B1]
        VIP_B[VIP / AnyCast IP<br/>※オンプレのみ]
    end
    subgraph "AWS（FSx for ONTAP）"
        FSX[FSx ONTAP<br/>FlexCache]
        S3AP[S3 Access Point]
        SFN[Step Functions]
    end
    MC_A ---|MetroCluster<br/>Sync Mirror| MC_B
    ORIGIN_A --> CACHE_A1
    ORIGIN_B --> CACHE_B1
    VIP_A -.->|BGP withdraw<br/>on failure| VIP_B
    ORIGIN_A -->|Cluster Peering| FSX
    FSX --> S3AP --> SFN
```

**特徴**:
- MetroCluster / SVM-DR でサイト間冗長化
- AnyCast VIP で自動フェイルオーバー（オンプレのみ）
- FSx for ONTAP は AWS 側の FlexCache として機能
- **FSx for ONTAP では MetroCluster 不可**（マネージド Multi-AZ HA で代替）

## 6. 既存 Serverless パターンとの統合

```mermaid
graph TB
    subgraph "既存パターン（EventBridge → Step Functions → Lambda → S3 AP）"
        EBS[EventBridge Scheduler]
        SFN[Step Functions]
        DISC[Discovery Lambda]
        PROC[Processing Lambda]
        RPT[Report Lambda]
        S3AP[S3 Access Point<br/>Origin or Cache]
    end
    subgraph "FlexCache AnyCast 制御プレーン"
        HEALTH_SFN[Health Check<br/>Step Functions]
        HEALTH_L[Health Check Lambda]
        ROUTE_L[Route Decision Lambda]
        FAILOVER_L[Failover Lambda]
    end
    subgraph "ストレージ層"
        ORIGIN[Origin Volume]
        CACHE_1[FlexCache 1]
        CACHE_2[FlexCache 2]
        S3AP_1[S3 AP 1]
        S3AP_2[S3 AP 2]
    end
    EBS --> SFN
    SFN --> DISC
    DISC -->|"最寄り S3 AP 選択<br/>(Route Decision 結果参照)"| S3AP_1
    DISC --> S3AP_2
    SFN --> PROC
    SFN --> RPT
    HEALTH_SFN --> HEALTH_L
    HEALTH_L --> CACHE_1
    HEALTH_L --> CACHE_2
    HEALTH_SFN --> ROUTE_L
    ROUTE_L -->|"DynamoDB に<br/>ルーティングテーブル更新"| DISC
    ORIGIN --> CACHE_1 --> S3AP_1
    ORIGIN --> CACHE_2 --> S3AP_2
```

**統合ポイント**:
- 既存の EventBridge → Step Functions → Lambda パイプラインはそのまま
- Discovery Lambda が「どの S3 AP を使うか」を Route Decision の結果から判定
- Health Check は別の Step Functions で定期実行
- DynamoDB にルーティングテーブルを保持し、Discovery Lambda が参照

## 設計原則

1. **制御プレーンとデータプレーンの分離**: AnyCast/VIP 制御は独立した Step Functions で管理
2. **既存パターンの非破壊**: 既存 UC の Discovery/Processing/Report パイプラインは変更しない
3. **シミュレーション可能**: 実環境 BGP/VIP がなくても Lambda でルート判定をシミュレーション
4. **段階的導入**: まず Static FlexCache + S3 AP → 次に Dynamic → 最後に AnyCast/DR
