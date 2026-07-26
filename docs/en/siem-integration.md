# SIEM Integration — ARP/AI Threat Events

## Overview

When ARP/AI detects ransomware activity or the portal executes containment actions, these events can be forwarded to external SIEM systems (Splunk, Datadog, Sentinel, QRadar) for centralized incident management.

## Architecture

```
ARP/AI Threat Detection (ONTAP)
  → Portal containment action (Lambda)
    → SNS Topic (notification)
      → EventBridge Rule (transform)
        → SIEM destination (Splunk HEC / Datadog API / CloudWatch Logs)
```

## Implementation Pattern

### 1. SNS Topic for Security Events

```yaml
# Add to backend.ts or separate CloudFormation
SecurityEventsTopic:
  Type: AWS::SNS::Topic
  Properties:
    TopicName: fsxn-portal-security-events
```

### 2. Publish from Containment Lambda

In `functions/data-protection/handler.py`, after successful containment:

```python
sns = boto3.client("sns")
sns.publish(
    TopicArn=os.environ["SECURITY_EVENTS_TOPIC_ARN"],
    Subject="ARP/AI Threat Contained",
    Message=json.dumps({
        "eventType": "THREAT_CONTAINED",
        "timestamp": datetime.utcnow().isoformat(),
        "volumeName": volume_name,
        "blockedUser": username,
        "blockedIp": client_ip,
        "snapshotCreated": snapshot_name,
        "severity": "HIGH",
    }),
    MessageAttributes={
        "eventType": {"DataType": "String", "StringValue": "THREAT_CONTAINED"},
    },
)
```

### 3. EventBridge Rule → SIEM

```yaml
SecurityEventsRule:
  Type: AWS::Events::Rule
  Properties:
    EventPattern:
      source: ["custom.fsxn-portal"]
      detail-type: ["Security Event"]
    Targets:
      # Option A: Splunk HEC
      - Arn: !GetAtt SplunkConnection.Arn
        Id: splunk-hec
      # Option B: Datadog
      - Arn: !Sub "arn:aws:events:${AWS::Region}:${AWS::AccountId}:api-destination/datadog"
        Id: datadog-api
      # Option C: CloudWatch Logs (simplest)
      - Arn: !Sub "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/security/fsxn-portal"
        Id: cloudwatch-logs
```

### 4. Splunk HEC Configuration

```bash
# EventBridge API Destination for Splunk
aws events create-connection \
  --name splunk-hec \
  --authorization-type API_KEY \
  --auth-parameters '{"ApiKeyAuthParameters":{"ApiKeyName":"Authorization","ApiKeyValue":"Splunk <HEC-TOKEN>"}}'

aws events create-api-destination \
  --name splunk-hec-dest \
  --connection-arn <connection-arn> \
  --invocation-endpoint "https://<splunk-host>:8088/services/collector/event" \
  --http-method POST
```

## Event Schema

```json
{
  "eventType": "THREAT_CONTAINED | THREAT_DETECTED | USER_BLOCKED | IP_BLOCKED",
  "timestamp": "2026-07-26T10:30:00Z",
  "source": "fsxn-portal",
  "severity": "HIGH | MEDIUM | LOW",
  "details": {
    "volumeName": "vol1",
    "blockedUser": "DOMAIN\\username",
    "blockedIp": "10.0.1.50",
    "snapshotCreated": "arp_contain_20260726_103000",
    "reason": "ARP/AI detected high-probability ransomware"
  }
}
```

## References

- [EventBridge API Destinations](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations.html)
- [Splunk HEC with EventBridge](https://docs.splunk.com/Documentation/AddOns/released/AWS/EventBridge)
