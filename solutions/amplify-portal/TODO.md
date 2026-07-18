# Amplify Portal — Future Improvements

Identified during 30-persona extended review. These require code changes (not documentation fixes).

## Priority: Medium

### Accessibility (Accessibility Specialist)
- [ ] Add `aria-label` to navigation buttons (Files / Process / Results)
- [ ] Announce active tab state to screen readers (`aria-selected` + `role="tab"`)
- [ ] Add `aria-live="polite"` to status badge in ResultsViewer for dynamic updates

### UX Guard Rails (End User)
- [ ] Disable "Process this folder" and "Start Processing" when `stateMachineArn` is placeholder
- [ ] Show user-friendly message: "Processing not configured. See README for setup."
- [ ] Disable "Files" tab browsing when `s3ApAlias` is empty (currently shows "No files" which is confusing vs. "Not configured")

### Architecture Clarity (Cloud Architect)
- [ ] Expand architecture diagram in README to show Discovery Lambda (VPC-internal) context
- [ ] Add sequence diagram (Mermaid) showing full request flow: User → AppSync → SFn → Discovery → ONTAP → S3 AP → Processing → Result

## Priority: Low

### Job History Persistence (Product Manager)
- [ ] Store execution ARN → userId mapping in DynamoDB
- [ ] Add "History" tab showing past job executions per user
- [ ] Implement owner-based authorization (users can only see their own jobs)

### Test Coverage (Test Engineer)
- [ ] Add vitest test files for React components (FileExplorer, JobSubmitForm, ResultsViewer)
- [ ] Add AppSync resolver unit tests (mock ctx object)
- [ ] Add integration test: Cognito signup → login → GraphQL query flow

### Snapshot/DR Integration (DR Specialist)
- [ ] Show FlexClone status in Results tab when processing uses cloned volumes
- [ ] Add "Restore from Snapshot" action in Files tab (triggers FlexClone → S3 AP attach)

### Frontend Polish (Frontend Developer)
- [ ] Add loading skeleton during initial auth check (prevent blank screen flash)
- [ ] Implement file preview (Range GET for first bytes → thumbnail)
- [ ] Add breadcrumb click-to-navigate in Results tab (link to processed folder)

---

*Last updated: 2026-07-18*
