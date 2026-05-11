# VPC Endpoint Security Group Automation Design

**Status**: APPROVED (Option A selected)  
**Created**: 2026-05-12  
**Theme**: Phase 8 Theme B

## Problem Statement

When multiple UC demo stacks share a single VPC Endpoint Security Group (e.g., in a shared VPC), each stack's Lambda Security Group needs an ingress rule added to the VPC Endpoint SG on deploy and removed on undeploy. Currently this is done manually or via the cleanup script, leading to:

1. **Deploy friction**: Users must manually add SG rules after stack creation
2. **Cleanup failures**: Forgetting to revoke rules before stack deletion causes dependent-object errors
3. **Inconsistency**: Some stacks create their own VPC Endpoint SG (isolated), others share one

## Options Considered

### Option A: Custom Resource + Lambda (SELECTED)

A CloudFormation Custom Resource backed by a Lambda function that automatically manages VPC Endpoint SG ingress rules during stack lifecycle events.

**Pros**:
- Pure CloudFormation — no CDK dependency
- Automatic lifecycle management (Create/Update/Delete)
- Works with existing UC template patterns
- Minimal IAM permissions (ec2:AuthorizeSecurityGroupIngress, ec2:RevokeSecurityGroupIngress)
- Opt-in via parameter (backward compatible)

**Cons**:
- Additional Lambda function to maintain
- Custom Resource error handling complexity
- Lambda cold start on stack operations (acceptable — infrequent)

### Option B: CDK Construct

A CDK L3 construct that manages VPC Endpoint SG rules.

**Pros**:
- Type-safe, testable
- Reusable across CDK projects

**Cons**:
- **Incompatible with project convention** — this project uses CloudFormation, not CDK
- Would require CDK bootstrap in target accounts
- Breaks the "deploy with `aws cloudformation deploy`" simplicity
- Not applicable to this project

### Decision: Option A

Option A is selected because:
1. Project uses CloudFormation exclusively
2. Custom Resources are already a known pattern in the project
3. Opt-in parameter preserves backward compatibility
4. Cleanup is automatic — no manual SG rule management needed

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  UC Stack (e.g., fsxn-legal-compliance-demo)            │
│                                                         │
│  ┌─────────────────────┐    ┌────────────────────────┐  │
│  │ LambdaSecurityGroup │    │ VpcEndpointSgManager   │  │
│  │ (existing)          │    │ (Custom Resource)      │  │
│  └─────────────────────┘    └────────────────────────┘  │
│           │                          │                   │
└───────────┼──────────────────────────┼───────────────────┘
            │                          │
            │    ┌─────────────────┐   │
            └───►│ VPC Endpoint SG │◄──┘
                 │ (shared/external)│
                 └─────────────────┘
```

### Lifecycle Events

| Event | Action |
|-------|--------|
| Create | Authorize ingress rule (Lambda SG → VPC Endpoint SG, TCP 443) |
| Update | Revoke old rule, authorize new rule (if Lambda SG changed) |
| Delete | Revoke ingress rule |

### Parameters (added to UC templates)

```yaml
VpcEndpointSecurityGroupId:
  Type: String
  Default: ""
  Description: >-
    Shared VPC Endpoint Security Group ID. If provided, the stack
    automatically adds/removes an ingress rule for the Lambda SG.
    Leave empty to skip (e.g., when using stack-local VPC Endpoints).

Conditions:
  HasVpcEndpointSg: !Not [!Equals [!Ref VpcEndpointSecurityGroupId, ""]]
```

### Lambda Handler Design

```python
# shared/vpc_endpoint_sg_manager/handler.py
def handler(event, context):
    """CloudFormation Custom Resource handler for VPC Endpoint SG management."""
    request_type = event["RequestType"]  # Create | Update | Delete
    props = event["ResourceProperties"]
    
    vpc_endpoint_sg_id = props["VpcEndpointSecurityGroupId"]
    lambda_sg_id = props["LambdaSecurityGroupId"]
    
    if request_type == "Create":
        authorize_ingress(vpc_endpoint_sg_id, lambda_sg_id)
    elif request_type == "Update":
        old_props = event.get("OldResourceProperties", {})
        old_lambda_sg = old_props.get("LambdaSecurityGroupId")
        if old_lambda_sg and old_lambda_sg != lambda_sg_id:
            revoke_ingress(vpc_endpoint_sg_id, old_lambda_sg)
        authorize_ingress(vpc_endpoint_sg_id, lambda_sg_id)
    elif request_type == "Delete":
        revoke_ingress(vpc_endpoint_sg_id, lambda_sg_id)
```

### IAM Policy (Least Privilege)

```yaml
- Effect: Allow
  Action:
    - ec2:AuthorizeSecurityGroupIngress
    - ec2:RevokeSecurityGroupIngress
    - ec2:DescribeSecurityGroups
  Resource: "*"
  Condition:
    StringEquals:
      ec2:ResourceTag/ManagedBy: "fsxn-s3ap-patterns"
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Rule already exists (Create) | Idempotent — catch `InvalidPermission.Duplicate`, return SUCCESS |
| Rule not found (Delete) | Idempotent — catch `InvalidPermission.NotFound`, return SUCCESS |
| SG not found | Return FAILED with descriptive message |
| Lambda timeout | cfn-response sends FAILED automatically |

## Implementation Plan

1. `shared/vpc_endpoint_sg_manager/handler.py` — Lambda handler
2. `shared/cfn/vpc-endpoint-sg-manager.yaml` — Shared infra stack (Lambda + IAM)
3. UC1 template integration (opt-in parameter + Custom Resource)
4. Unit tests with moto EC2 mock

## Testing Strategy

- Unit tests: moto EC2 for authorize/revoke operations
- Integration: Deploy to dev VPC, verify SG rules appear/disappear
- Edge cases: duplicate rules, missing SG, concurrent operations
