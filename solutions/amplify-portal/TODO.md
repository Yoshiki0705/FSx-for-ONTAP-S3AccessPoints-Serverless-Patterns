# Amplify Portal — Future Improvements

Identified during 30-persona extended review. Code changes required.

## ✅ Completed (PR #130, #131)

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

## Priority: Low (Future)

### Job History Persistence (Product Manager)
- [ ] Store execution ARN → userId mapping in DynamoDB
- [ ] Add "History" tab showing past job executions per user
- [ ] Implement owner-based authorization (users can only see their own jobs)

### Snapshot/DR Integration (DR Specialist)
- [ ] Show FlexClone status in Results tab when processing uses cloned volumes
- [ ] Add "Restore from Snapshot" action in Files tab (triggers FlexClone → S3 AP attach)

### Frontend Polish (Frontend Developer)
- [ ] Add loading skeleton during initial auth check (prevent blank screen flash)
- [ ] Implement file preview (Range GET for first bytes → thumbnail)
- [ ] Add breadcrumb click-to-navigate in Results tab (link to processed folder)

### CI Integration
- [ ] Add amplify-portal vitest to GitHub Actions CI workflow
- [ ] Add `npx tsc --noEmit` check for amplify-portal in CI

---

*Last updated: 2026-07-18*
