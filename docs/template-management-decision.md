# Template Management Decision

**Status**: APPROVED (Option A — template-deploy.yaml is source of truth)  
**Created**: 2026-05-12  
**Theme**: Phase 8 Theme K

## Problem Statement

Each UC has two CloudFormation templates:
- `template.yaml` — SAM Transform version (for `sam local invoke` testing)
- `template-deploy.yaml` — Raw CloudFormation version (for actual deployment)

These diverge over time because:
1. New features (OutputDestination, S3AccessPointName) are added to `template-deploy.yaml` first
2. `create_deploy_template.py` is a simple regex-based converter that doesn't handle all patterns
3. Lint/test infrastructure only validates `template-deploy.yaml`
4. Actual deployments use `template-deploy.yaml` exclusively

## Options Considered

### Option A: template-deploy.yaml is source of truth (SELECTED)

Keep `template-deploy.yaml` as the authoritative template. Deprecate `template.yaml` by:
1. Adding a header comment noting it's for local SAM testing only
2. Documenting that `template-deploy.yaml` is the canonical version
3. Not requiring `template.yaml` to be in sync

**Pros**:
- Matches current reality (deploy scripts, lint, tests all use template-deploy.yaml)
- No migration needed — already the de facto standard
- Eliminates confusion about which file to edit
- `create_deploy_template.py` becomes unnecessary for new features

**Cons**:
- `sam local invoke` users need to manually sync template.yaml (rare use case)
- Two files still exist (but roles are clearly documented)

### Option B: Remove template.yaml entirely

Delete all `template.yaml` files, keep only `template-deploy.yaml`.

**Pros**:
- Single source of truth, zero ambiguity
- Fewer files to maintain

**Cons**:
- Breaks `sam local invoke` workflow entirely
- Some users may reference template.yaml in their scripts
- Larger diff, more disruptive

### Decision: Option A

Option A is selected because:
1. It's the least disruptive change
2. `template.yaml` still has value for local SAM testing (even if rarely used)
3. The key issue (confusion about which to edit) is solved by documentation
4. No files need to be deleted

## Implementation

1. Add deprecation header to each `template.yaml`:
   ```yaml
   # ⚠️ NOTE: This file is for SAM local testing only.
   # The authoritative deployment template is template-deploy.yaml.
   # Edit template-deploy.yaml for production changes.
   ```

2. Update project README to clarify template roles

3. Mark `create_deploy_template.py` as legacy (still functional but not required for new features)

## Future Consideration

If `sam local invoke` is never used in practice, Option B (full removal) can be revisited in a future phase.
