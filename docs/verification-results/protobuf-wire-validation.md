# Protobuf Wire Validation Results

## Objective

ONTAP FPolicy protobuf モードの TCP ワイヤフォーマットを実機で検証し、AUTO_DETECT モードの正確性を確認する。

## Test Environment

| Item | Value |
|------|-------|
| ONTAP Version | NetApp Release 9.17.1P6 (Wed Mar 25 15:38:10 UTC 2026) |
| FPolicy Engine Format | protobuf (switched from xml via REST API) |
| FPolicy Server | Fargate (disconnected at time of format switch) |
| Management IP | <FS_MGMT_IP> (filesystem level) |
| SVM | FSxN_OnPre (UUID: <SVM_UUID>) |

## Format Switch Verification

| Step | Method | Result |
|------|--------|--------|
| Disable FPolicy | ONTAP CLI `fpolicy disable` | ✅ Success |
| Switch to protobuf | REST API `PATCH /api/protocols/fpolicy/{svm}/engines/{name}` | ✅ Success |
| Re-enable FPolicy | ONTAP CLI `fpolicy enable` | ✅ Success |
| Verify format | REST API `GET ...?fields=format` | ✅ `"format": "protobuf"` |

### Key Finding: CLI vs REST API

The `-format` parameter is **NOT available** in ONTAP 9.17.1 CLI for `fpolicy policy external-engine modify`. Format changes must be performed via REST API only.

```bash
# ❌ CLI (fails with "invalid argument")
fpolicy policy external-engine modify -vserver <SVM_NAME> -engine-name <ENGINE_NAME> -format protobuf

# ✅ REST API (works)
curl -sk -X PATCH \
  -H "Authorization: Basic <base64>" \
  -H "Content-Type: application/json" \
  -d '{"format": "protobuf"}' \
  "https://<FS_MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines/<ENGINE_NAME>"
```

## Engine Configuration in Protobuf Mode

```json
{
  "name": "fpolicy_aws_engine",
  "primary_servers": ["<FPOLICY_SERVER_IP>"],
  "port": 9898,
  "type": "asynchronous",
  "format": "protobuf",
  "ssl_option": "no_auth",
  "buffer_size": {
    "recv_buffer": 262144,
    "send_buffer": 1048576
  },
  "keep_alive_interval": "PT2M",
  "max_server_requests": 500,
  "session_timeout": "PT10S",
  "max_connection_retries": 5
}
```

## Observations

| Parameter | XML Mode | Protobuf Mode | Notes |
|-----------|----------|---------------|-------|
| keep_alive_interval | PT2M | PT2M | Same in both modes |
| recv_buffer | 262144 | 262144 | Same |
| send_buffer | 1048576 | 1048576 | Same |
| max_server_requests | 500 | 500 | Same |
| session_timeout | PT10S | PT10S | Same |

## Framing Format Documentation

### Observed Wire Format

[Pending — requires active FPolicy server connection to capture TCP frames]

## AUTO_DETECT Verification

| Test | Input | Expected Detection | Actual Detection | Status |
|------|-------|-------------------|-----------------|--------|
| Protobuf frame | Real ONTAP protobuf | FRAMELESS or LENGTH_PREFIXED | Pending | ⏳ |
| XML frame | Real ONTAP XML | LENGTH_PREFIXED | Confirmed (Phase 12) | ✅ |

## Backward Compatibility

| Test | Result |
|------|--------|
| Switch XML → Protobuf | ✅ Successful (REST API PATCH) |
| Switch Protobuf → XML | Pending (will test after wire capture) |
| Pipeline resumes after switch | Pending (requires FPolicy server) |

## Migration Path Recommendation

Based on Phase 13 validation:

1. **Disable FPolicy policy** (`fpolicy disable`)
2. **Switch format via REST API** (CLI does not support `-format` in 9.17.1)
3. **Re-enable FPolicy** (`fpolicy enable`)
4. **Verify FPolicy server reconnects** in protobuf mode
5. **Monitor for 24 hours** before declaring migration complete
6. **Rollback**: Repeat steps 1-3 with `"format": "xml"` if issues arise

## Max Message Size Guidance

- `recv_buffer`: 262144 bytes (256 KB)
- `send_buffer`: 1048576 bytes (1 MB)
- ProtobufFrameReader `max_message_size` should be set to at least 1 MB to match send_buffer

