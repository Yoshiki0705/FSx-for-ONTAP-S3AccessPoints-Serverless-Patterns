# Amplify Portal — Future Improvements

Identified during 30-persona extended review. Code changes required.

## ✅ Completed (PR #130, #131, #139-#145)

### Accessibility
- [x] Add `aria-label` to navigation buttons (Files / Process / Results)
- [x] Announce active tab state to screen readers (`aria-selected` + `role="tab"`)
- [x] Add `aria-live="polite"` to status badge in ResultsViewer for dynamic updates

### UX Guard Rails
- [x] Disable "Process this folder" and "Start Processing" when `stateMachineArn` is placeholder
- [x] Show user-friendly message: "Processing not configured. See README for setup."
- [x] Default `processingEnabled: false` (safe-by-default)

### Architecture Clarity
- [x] Add Mermaid sequence diagram showing full request flow

### Test Coverage
- [x] Add vitest test files for React components (14 tests)
- [x] Add amplify-portal vitest + tsc to GitHub Actions CI workflow

### Job History Persistence
- [x] Store execution ARN → userId mapping in DynamoDB
- [x] Add "History" tab showing past job executions per user
- [x] Implement owner-based authorization (users can only see their own jobs)

### Frontend Polish
- [x] Add loading skeleton during initial auth check (prevent blank screen flash)
- [x] Implement file preview (image detection + hover tooltip)
- [x] Add breadcrumb click-to-navigate in Results tab (link to processed folder)

### Snapshot/DR Integration
- [x] Show FlexClone status in Results tab when processing uses cloned volumes
- [x] Add "Restore from Snapshot" action in Files tab (triggers FlexClone creation dialog)

## Priority: Low (Future)

### Presigned URL Integration
- [ ] Connect FilePreview to actual presigned URL for real image thumbnails
- [ ] Add `getPresignedUrl` AppSync query backed by Lambda

### Production Deployment
- [ ] Amplify Hosting deployment guide (branch-based CI/CD)
- [ ] SAML/OIDC Cognito integration guide for enterprise SSO
- [ ] Mobile-responsive CSS refinements

---

*Last updated: 2026-07-18*
