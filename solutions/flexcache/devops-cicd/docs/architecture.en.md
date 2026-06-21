# FC7 Architecture: DevOps FlexClone + S3AP

## Data Flow

```mermaid
sequenceDiagram
    participant CI as CI/CD Pipeline
    participant SF as Step Functions
    participant CM as Clone Manager
    participant ONTAP as FSx for ONTAP
    participant SP as S3AP Provisioner
    participant TO as Test Orchestrator
    participant S3 as S3 Access Point
    participant CL as Cleanup

    CI->>SF: StartExecution (source_volume, ttl_hours)
    SF->>CM: CREATE FlexClone
    CM->>ONTAP: POST /api/storage/volumes (clone)
    ONTAP-->>CM: job_uuid, clone_name
    CM-->>SF: clone_name, junction_path

    SF->>SP: Provision S3AP
    SP-->>SF: s3ap_alias

    SF->>TO: Run tests (s3ap_alias)
    TO->>S3: ListObjectsV2 (data verification)
    S3->>ONTAP: Read via S3AP data plane
    ONTAP-->>S3: File data
    S3-->>TO: Objects
    TO-->>SF: test_results, ready_for_cleanup=true

    SF->>CL: Immediate cleanup
    CL->>ONTAP: PATCH (offline) + DELETE volume
    CL-->>SF: deleted
```

## Component Overview

| Lambda | Role | ONTAP API | VPC Requirement |
|--------|------|-----------|-----------------|
| Clone Manager | FlexClone lifecycle management | POST/GET/PATCH/DELETE volumes | In-VPC (management IP access) |
| S3AP Provisioner | S3AP config, alias return | — | VPC-external OK |
| Test Orchestrator | Test execution, result collection | — | Depends on NetworkOrigin |
| Cleanup | TTL sweep + immediate deletion | GET/PATCH/DELETE volumes | In-VPC (management IP access) |

## Step Functions State Machine

```json
{
  "StartAt": "CreateClone",
  "States": {
    "CreateClone": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:clone-manager",
      "Parameters": {
        "action": "CREATE",
        "source_volume.$": "$.source_volume",
        "ttl_hours.$": "$.ttl_hours",
        "requester.$": "$.requester"
      },
      "Next": "ProvisionS3AP"
    },
    "ProvisionS3AP": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:s3ap-provisioner",
      "Next": "RunTests"
    },
    "RunTests": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:test-orchestrator",
      "Next": "Cleanup"
    },
    "Cleanup": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:cleanup",
      "Parameters": {
        "mode": "immediate",
        "clone_name.$": "$.clone_name"
      },
      "End": true
    }
  }
}
```

## Technical Comparison with EBS Volume Clones

| Aspect | EBS Volume Clones | FlexClone + S3AP |
|--------|-------------------|------------------|
| **Copy mechanism** | CoW (Copy-on-Write) block-level | CoW block-level (WAFL) |
| **Instant availability** | ✅ Available within seconds | ✅ Metadata-only, instant |
| **Data independence** | Fully independent (accessible during init) | Shares with parent (until split) |
| **Storage consumption** | Full clone size (after init) | Differential blocks only |
| **Access method** | Attach to EC2 | S3 API / NFS / SMB |
| **Scope** | Same-AZ only | S3AP: accessible from outside VPC |
| **IOPS** | Independent IOPS per clone | Shared with parent aggregate |
| **Max size** | 64 TiB (EBS limit) | ONTAP volume limit |
| **Automation** | CreateVolume API | ONTAP REST API |
| **Cleanup** | DeleteVolume API | ONTAP REST API + TTL automation |
