# Dual-Kiro Coordination Protocol

**Purpose**: this document captures the working rules that two (or more)
parallel Kiro AI sessions follow when operating on the same repository
simultaneously. It is the onboarding reference for any new parallel
session joining an in-progress sprint.

**Status**: active, maintained. Last updated 2026-05-11.

**Scope**: applies to any two or more Kiro sessions touching this repo
at the same wall-clock time. Does not apply to sequential sessions where
only one Kiro is ever live.

---

## 1. Why this exists

Two Kiro sessions running in parallel on the same local checkout can
destructively clobber each other via:

- `git checkout` switching branches while the other session has
  uncommitted edits (the other session may have its working-tree
  changes silently stashed or lost)
- Both sessions staging and committing on the same branch without
  coordination, producing interleaved commits that later sessions
  cannot reason about
- `git push --force` / `git reset --hard` by one session that drops
  commits the other session has authored
- Both sessions editing the same file with different intents,
  producing merge conflicts that either side may "resolve" without
  understanding the other intent

This protocol exists because in the 2026-05-10→2026-05-11 sprint
(mask redaction PR #2), one session reset away another session's
uncommitted v7 mask work twice. It was recovered via stash, but
the near-miss demonstrated a need for explicit coordination rules.

---

## 2. Roles & labels

Each Kiro session is labelled by a single uppercase letter (A, B, C, …)
at the start of the sprint. The label is fixed for the duration of
the sprint and is used in all chat notifications and branch names.

In the source sprint (PR #2 + Phase 7 unify):
- **A** = Screenshot Redaction (v7 OCR mask rewrite)
- **B** = OutputDestination API unification (Pattern B rollout + 8-lang
  translations + Phase 7 UC15-17 unify)

New sessions joining an ongoing sprint should claim the next letter (C,
D, …) and post a `[X] JOINING — claimed label X` notification.

---

## 3. Branch & file ownership (exclusive regions)

Each session declares an **exclusive region** — the set of paths and
files only that session edits for the duration of the sprint. Other
sessions must not write to those paths without explicit lock
acquisition (see §7).

### 3.1 Example region declarations (source sprint)

**A's exclusive region**:
- `scripts/mask_uc_demos.py` (v7 OCR mask script)
- `docs/screenshots/masked/**` (all PNG re-masks)
- `docs/screenshots/MASK_GUIDE.md`
- `scripts/_check_sensitive_leaks.py*`, `scripts/_inplace_ocr_mask.py*`,
  `scripts/_deep_scan.py`, other mask-related `scripts/_*.py*` helpers
- `docs/dual-kiro-coordination.md` (this file)
- `.kiro/specs/fsxn-s3ap-serverless-patterns-phase7/tasks.md`
- Cleanup helpers (`scripts/_preview_cleanup.sh`,
  `scripts/_check_cleanup_progress.sh`,
  `scripts/_empty_versioned_bucket.sh`)
- Future Phase 8 spec drafts

**B's exclusive region**:
- `shared/output_writer.py` + `shared/tests/test_output_writer.py`
- `retail-catalog/**`, `insurance-claims/**`,
  `autonomous-driving/**`, `construction-bim/**`, `logistics-ocr/**`
  (full per-UC trees: `functions/**/handler.py`, `template-deploy.yaml`,
  `tests/**`, `docs/demo-guide.md`)
- `legal-compliance/**`, `financial-idp/**`,
  `manufacturing-analytics/**`, `media-vfx/**`, `healthcare-dicom/**`
  (UC1-5 OutputDestination unify, same file set as above)
- `defense-satellite/**`, `government-archives/**`, `smart-city-geo/**`
  (UC15-17 OutputDestination unify, Phase 7)
- `docs/output-destination-patterns.md`
- `docs/verification-results-output-destination.md`
- `docs/aws-feature-requests/fsxn-s3ap-improvements.md`
- `README.md` "AWS 仕様上の制約と回避策" + "UI/UX スクリーンショット"
  sections (and 7 translated language variants)
- Per-UC `demo-guide.{en,ko,zh-CN,zh-TW,fr,de,es}.md` for UC1-5/9-14
- `docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`
- `docs/screenshots/uc-industry-mapping.md`
- B's own `scripts/_*` automation helpers (name-prefixed with a
  task-specific suffix, e.g. `_unify_outputdestination_uc1_5.py`,
  `_translate_output_dest_sections.py`)

### 3.2 Shared / safe region

Any path not in an exclusive region may be edited by either session,
BUT changes should still be announced in chat if they affect files
the other session's review depends on (e.g. shared config, root
`README.md` sections outside B's scope, `.gitignore`, `tsconfig.json`,
etc.).

### 3.3 Declaration workflow

At session start, each session declares their exclusive region in a
single chat message:

```
[A] REGION CLAIM
- scripts/mask_uc_demos.py
- docs/screenshots/masked/**
- ...
```

Changes to region (adding / removing paths) must be renegotiated in
chat before applying.

---

## 4. Branch strategy

### 4.1 Feature branches

Each session works on its own feature branch, named
`feat/<session-label>-<brief-description>`. Examples:

- `feat/uc1-13-verification-screenshots-and-redaction` (A)
- UC9 / UC10 / UC12 OutputDestination work (B, branched per scope)

### 4.2 Main branch

Both sessions merge to `main`. `main` is the single source of truth.
Neither session force-pushes `main`. Normal merge commits via PR.

### 4.3 Force-push policy

- **Force-push to main**: strictly forbidden (either session)
- **Force-push to own feature branch**: allowed using
  `git push --force-with-lease` when rebasing onto main
- **Force-push to another session's feature branch**: strictly
  forbidden without prior explicit chat permission

After rebasing a feature branch with force-with-lease, post a PR
comment:

```
⚠️ Rebased onto origin/main (<sha>) for conflict resolution.
No content change in this rebase itself.
```

This keeps reviewers oriented when GitHub's "Force-pushed" marker
appears.

### 4.4 Merge order

When both sessions have PRs open simultaneously, coordinate merge
order in chat. Usually:

1. Session whose work is smaller / reviewed first merges
2. Other session rebases onto main, pushes with `--force-with-lease`,
   comments on PR, re-requests review if needed

---

## 5. Commit & push discipline

### 5.1 Logical-unit commits

Each commit = one logical unit. Examples:

- `feat(mask): v7 OCR rewrite` (one rewrite, not multiple incremental)
- `feat(screenshots): v7 re-mask phase1` (one directory's PNGs)
- `feat(UC15): unify OutputDestination API` (one UC's unify)

### 5.2 Push granularity

Push after each logical-unit commit or a small group of them.
Do NOT batch 20+ commits into a single push — it makes conflict
recovery harder for the other session.

### 5.3 Push notifications

After every push, send a chat notification:

```
[X] PUSHED
branch: <branch-name>
commits: <sha1> [<sha2> ...]
scope: <one-line description>
touched files: <glob or brief list>
next: <what the session does next, or "done">
```

Example:

```
[A] PUSHED
branch: feat/uc1-13-verification-screenshots-and-redaction
commits: b41b82c e5f905d ccd487e cd82fd2 c07e2e0 dce52d2 a0a0028 \
         f15e137 8d15298 20b4152 b54e095
scope: v7 OCR re-mask across 11 logical groups
touched files: scripts/mask_uc_demos.py, .gitignore, \
               docs/screenshots/masked/**
next: PR body update + rebase onto origin/main
```

### 5.4 Commit messages

- Use Conventional Commits (`feat(scope):`, `fix(scope):`,
  `docs(scope):`, `chore(scope):`, `refactor(scope):`)
- Short imperative subject line (≤72 chars)
- Full body explaining what changed, why, and any migration notes
- Reference PR # or issue # if relevant

---

## 6. Checkout & working-tree safety (the hard rules)

These rules exist because the most destructive events in a dual-Kiro
sprint are caused by careless `git checkout`.

### 6.1 Rule C-1: Check current branch before committing

Before every `git commit`, run `git branch --show-current` (or equivalent)
and verify you are on the branch you intend to commit to.

### 6.2 Rule C-2: Never checkout with dirty working tree unless you own it

If `git status --short` shows modifications that are not yours:
- **Do NOT** run `git checkout`, `git switch`, `git stash`,
  `git reset --hard`, or any command that rewrites the working tree
- Send a chat notification first:

```
[X] I need to checkout <target>. Your working tree has N dirty files.
Is your working tree safe to stash? (reply "yes" to proceed, "no" to hold)
```

Wait for the other session's "yes" before proceeding. If they say
"no", find a different way (e.g. `git stash push -m` **your own**
modifications only using path filters, or wait for them to commit).

### 6.3 Rule C-3: Stash is a safety net, not a workflow

`git stash` can preserve uncommitted changes across an accidental
checkout, and it DID save us in the source sprint. But **do not rely
on it as a normal workflow**:

- Stashes are trivially lost to `git stash drop` typos
- Stashes don't show up in `git log` or PR diffs
- Stashes are local-only (not pushed to origin)

Normal flow is: commit → push → checkout. Only stash as an emergency
recovery measure when a checkout has already happened.

### 6.4 Rule C-4: Recognize when you've checked out the wrong thing

If after checkout you see:
- `git status` reports "branch is clean" but you had uncommitted work
- Files you expected to see are missing from the working tree
- `git log` doesn't show commits you remember making

**Immediately**:
1. Stop. Do not commit, push, or checkout again
2. Run `git reflog` to find the lost state
3. Send a `[X] OOPS detected reflog anomaly, investigating` message
4. Recover using `git stash list` + `git stash pop stash@{N}` or
   `git checkout <reflog-sha>` to navigate back
5. Only then continue

### 6.5 Rule C-5: Force-push requires lease

Use `git push --force-with-lease` never bare `--force`. This prevents
overwriting commits the other session may have pushed to your branch.
If lease fails, investigate before overriding.

---

## 7. File-level locks (for shared-region edits)

When you need to edit a file in the other session's exclusive region,
acquire an explicit lock first:

```
[A] LOCK REQUEST: README.md "AWS 仕様" section
reason: update reference to new FR-5 after main merge
duration: ~15 min
```

B replies:

```
[B] LOCK GRANTED: README.md "AWS 仕様" section
release when you ack [A] LOCK RELEASED
```

A completes the edit, commits, pushes:

```
[A] LOCK RELEASED: README.md
commit: abc1234
diff: added FR-5 cross-reference in line 245
```

B may now resume editing that section.

Locks should be short (15-30 min max). If a longer edit is needed,
break into smaller logical units.

---

## 8. Conflict resolution

### 8.1 During rebase

If rebase produces conflicts, resolve per the following precedence:

| File type | Preference |
|---|---|
| PNG screenshots under `docs/screenshots/masked/**` | `--theirs` (prefer the rebasing session's version, since OCR re-masks are deterministic outputs) |
| Source code (Python, TypeScript, YAML) | Manual resolution; understand both intents |
| Translated READMEs / demo-guides | Prefer whichever session owns the language in their exclusive region |
| `.gitignore`, config files | Merge both sets of additions |

If you are unsure which side's change is correct, abort the rebase
and ask in chat before proceeding.

### 8.2 Merge conflict on feature branch

Same as rebase resolution. Never pick sides unilaterally on a file
in the other session's exclusive region — always ask.

---

## 9. AWS resource lifecycle coordination

Some sprints also touch live AWS resources. Rules:

### 9.1 Deployment ownership

Each session owns deployment of stacks in their exclusive region.
Example (source sprint):

- **A owned deployments**: UC1/2/3/5/7/8/10/12/13 demo stacks
- **B owned deployments**: UC11/14/9 Pattern B stacks

### 9.2 Cleanup coordination

Before deleting stacks, confirm the other session doesn't depend on
the output:

```
[A] CLEANUP REQUEST: UC1-13 stacks
reason: all screenshots captured, Phase 7 N-1
dependencies: none B-side (confirmed #9)
proceed? (Y/N)
```

B replies `Y/N` with reason if N.

### 9.3 Shared S3AP / prefix coordination

If both sessions read/write to the same S3 Access Point, partition
the prefix namespace:

- A uses `ai-outputs/uc{1,2,3,5,7,8,10,12,13}/`
- B uses `ai-outputs/uc{11,14,9}/` and Pattern-A UC `ai-outputs/uc{15-17}/`

Cleanup of shared prefixes (e.g. B's `ai-outputs/uc{11,14}/` before
UC9 deploy) must be coordinated to avoid race conditions.

---

## 10. Screenshot masking coordination (Rule E)

**Any session** adding new screenshots must follow Rule E:

1. Place originals (if any) under `docs/screenshots/originals/<dir>/`
2. Run `python3 scripts/mask_uc_demos.py <dir>` to generate masks
3. Run `python3 scripts/_check_sensitive_leaks.py` — must report
   **0 leaks**
4. If leaks are detected, add missing sensitive strings to
   `scripts/_sensitive_strings.py` (gitignored), re-mask, re-verify
5. Commit PNG + any scripts / demo-guide updates in one logical unit

The mask script (`scripts/mask_uc_demos.py`) itself is in A's
exclusive region. B (and later sessions) may use it but must not
modify it without prior chat agreement, since algorithm changes
affect every existing screenshot.

Reference: `docs/screenshots/MASK_GUIDE.md` (v7 workflow).

---

## 11. Industry-mapping coordination (Rule F)

`docs/screenshots/uc-industry-mapping.md` is maintained in B's
exclusive region. It maps each UC number to an industry label in 8
languages (JP/EN/KO/zh-CN/zh-TW/FR/DE/ES).

When a new UC is added by any session:
1. Propose the industry label in chat
2. B (as owner of the mapping file) adds the row in 8 languages
3. Rest of the session proceeds as usual

Industry label changes (e.g. renaming "Legal Compliance" to "Legal &
Compliance") require prior agreement between all active sessions.

---

## 12. Emergency pause

If either session detects:
- Main CI in a broken state
- Unmergeable conflict after 2 rebase attempts
- A session's commit appears to have destroyed the other's work
- AWS live resources in unexpected state (e.g. someone else's stack
  was deleted by mistake)

…send an emergency pause:

```
[X] EMERGENCY PAUSE
issue: <one-line summary>
state: <what you see in git / AWS>
next: awaiting user decision
```

Both sessions halt non-trivial operations (read-only investigation
is fine) until the user (the human driver) decides the recovery plan.

---

## 13. Session handoff

At session end (sprint complete or session running out of context /
budget), the outgoing session writes a handoff message:

```
[X] SESSION HANDOFF
completed: <list of completed PRs / commits / tasks>
in-flight: <list of started-but-incomplete items>
next-session-advice: <what the next session should tackle first>
gotchas: <any non-obvious state the next session should know>
```

This message is the contract between the outgoing and incoming session.

---

## 14. Amendments

This document is versioned in git. Proposing an amendment:

1. Session proposes the change in chat
2. All active sessions review
3. Whoever authored the PR-review cycle commits the change to
   `docs/dual-kiro-coordination.md`
4. Post-merge, announce in chat:
   `[X] COORDINATION RULE UPDATED: <rule number> — <brief summary>`

Do not embed environment-specific examples (account IDs, alias
strings) in this file. Use placeholder tokens (`<ACCOUNT_ID>`,
`my-env-s3ap-xxxx-ext-s3alias`) instead.

---

## Appendix A: Source sprint reference

This document was created after the 2026-05-10 → 2026-05-11 sprint
that produced PR #2 (screenshot v7 OCR redaction) and the UC1-5 + UC15
OutputDestination unification.

Notable coordination incidents resolved during that sprint:

1. **Checkout clobber 1** (2026-05-10 pre-dawn): B's session switched
   to main while A had uncommitted v7 mask work. Recovered via stash
   `parallel-kiro-working-tree`. Prompted Rule C-2 and C-3.

2. **Checkout clobber 2** (2026-05-11 02:30): Same pattern, different
   context. Recovered via stash `parallel-kiro-working-tree-preserve`.
   Prompted Rule C-4.

3. **Accidental commit on other's feature branch** (2026-05-11 dawn):
   B committed twice to A's `feat/uc1-13-...` branch before resetting.
   Reset was clean (no origin push), but if pushed could have required
   force-push recovery. Prompted Rule C-1.

4. **Script redaction leftover** (2026-05-11 04:30): `<ACCOUNT_ID>`
   placeholder in `cleanup_generic_ucs.sh` from an earlier global
   redact pass silently caused bucket-empty operations to no-op.
   Fixed in commit 770f713. No lasting impact.

5. **OCR language gap** (2026-05-11 04:00): `lang="eng"` only missed
   Japanese-adjacent sensitive tokens in AWS console screenshots.
   Fixed by switching to `lang="eng+jpn"` in v7 mask script and leak
   checker. Covered in MASK_GUIDE.md §8-1.

All incidents recovered without data loss. This protocol codifies the
lessons so future sprints avoid the same classes of error.

---

## Appendix B: v1.1 improvements (2026-05-11 extended session)

The following patterns emerged during the continued Phase 7 Extended
Work session (Theme R localization, Theme Q UC fixes, article writing,
and full-UC screenshot campaign). They supplement the core rules above.

### B-1. Article writing as a non-competing parallel track

When one session writes documentation (articles, runbooks, guides) that
is **gitignored** (e.g., `docs/article-*.md`), it operates in a
zero-conflict mode:

- No git commits are produced by the article work
- No `git pull` / `push` coordination is needed
- The other session can freely commit to main without worrying about
  merge conflicts with the article

**Pattern**: assign article writing to the session that has finished
its implementation tasks, while the other session continues with
AWS deploy / fix / screenshot work. This maximizes parallelism.

### B-2. "Publish blocker" communication pattern

When a deliverable (e.g., a blog article) depends on work from both
sessions, use the following pattern:

```
[A] PUBLISH BLOCKER: <deliverable>
blocked by: <list of missing items>
owner per item:
  - <item 1>: B
  - <item 2>: A
  - <item 3>: B
unblock ETA: <estimate>
```

The other session responds with:

```
[B] ACK PUBLISH BLOCKER
ETA for my items: <estimate>
proceeding with: <item list>
```

This prevents the "I thought you were doing it" ambiguity that can
delay publish by hours.

### B-3. Full-UC verification sweep protocol

When a deliverable requires **all UCs** to pass a check (e.g., "all 17
UC screenshots present", "all Step Functions SUCCEEDED"), use a sweep:

1. One session runs the sweep and produces a matrix:
   ```
   UC1  ✅ SUCCEEDED
   UC2  ✅ SUCCEEDED
   ...
   UC9  ❌ FAILED (template bug)
   UC4  ❌ NOT DEPLOYED (Deadline Cloud dependency)
   ```

2. Failed items are assigned to sessions based on exclusive regions

3. Each session fixes their items and reports:
   ```
   [X] SWEEP FIX: UC9 — template bug resolved, SFN SUCCEEDED
   ```

4. When all items are ✅, the sweep owner declares:
   ```
   [X] SWEEP COMPLETE: all 17 UCs SUCCEEDED
   ```

This pattern was used for the screenshot campaign (UC4/9/15/16/17 were
missing → assigned → fixed → completed).

### B-4. Template bug discovery during verification

When a session discovers a template bug during AWS deploy verification:

1. **Do not silently fix and move on**. Document the bug in chat:
   ```
   [X] BUG FOUND: <UC> template-deploy.yaml
   symptom: <what failed>
   root cause: <analysis>
   fix: <proposed approach>
   ```

2. If the fix touches the other session's exclusive region, request
   a lock (§7). If it's in your own region, proceed and report.

3. After fixing, include the bug in the article's "Lessons learned"
   section — these are high-value content for readers.

UC9's three bugs (DefinitionSubstitutions, NumericGreaterThanEqualsPath
typo, Discovery handler missing fields) were discovered this way and
became Lessons #10-12 in the Phase 7 article.

### B-5. Localization batch as a parallel track

Large-scale translation batches (97 files in Theme R) can run as a
background process while the other session works on implementation:

- The batch script runs for 30-75 minutes unattended
- Progress is monitored via a helper script (e.g., `_r1_progress.sh`)
- The implementing session can commit/push freely during the batch
  (the batch only writes to `<uc>/docs/*.{lang}.md` files)
- After the batch completes, the translating session commits in
  logical units (per-UC or per-language-group)

**Caution**: Do NOT pipe batch output through `| tail -N` — this
buffers all output until completion, making progress invisible. Use
`| tee /tmp/batch.log` or run as a background process with periodic
`get_process_output` checks.

### B-6. Gitignored article files and the "preview escape" problem

Article files (`docs/article-*.md`) are gitignored and live only
locally. When sharing article content for review:

- **Do NOT paste through chat UI** — many chat tools HTML-escape
  `<`, `>`, `&` characters, breaking Mermaid diagrams and code blocks
- **Use terminal-to-editor direct copy**: `cat docs/article-*.md | pbcopy`
  (macOS) then paste into dev.to editor
- **For review**: share the file via a temporary gist, or read it
  directly from the local filesystem

This was discovered when Mermaid `-->` appeared as `--&gt;` in review
feedback — the file was correct, but the review tool had escaped it.

### B-7. Phase-separation policy for blog articles

Each Phase gets its own blog article. The boundary between phases is:

- **Same Phase**: completing existing UCs, fixing bugs in existing
  templates, adding screenshots for existing UCs, translating existing
  docs, cleanup of existing stacks
- **New Phase**: new architectural patterns (event-driven trigger),
  new shared infrastructure (VPC Endpoint SG automation), new API
  additions (OutputWriter.put_stream), new UC patterns (Pattern C→B
  hybrid migration)

UC4/UC9 residual completion is Phase 7 (existing UC, existing pattern).
Pattern C→B hybrid for UC6/7/8/13 is Phase 8 (new pattern application).

This policy ensures each article has a clear thesis and doesn't become
a grab-bag of unrelated changes.

---

## Appendix C: Coordination checklist (quick reference)

For sessions joining an ongoing sprint, verify the following before
starting work:

```
□ Read this document in full
□ Claim a session label ([X] JOINING — claimed label X)
□ Declare exclusive region ([X] REGION CLAIM: ...)
□ Verify git branch (git branch --show-current)
□ Verify working tree is clean (git status --short)
□ Pull latest main (git pull --ff-only origin main)
□ Check for active publish blockers in chat history
□ Check for active file locks in chat history
□ Confirm _sensitive_strings.py is present locally
□ Run _check_sensitive_leaks.py to verify baseline (0 leaks)
□ Confirm tesseract + tesseract-lang installed (for screenshot work)
□ Confirm AWS credentials valid (aws sts get-caller-identity)
```

If any check fails, resolve before starting implementation work.
Post `[X] READY — all checks passed` when complete.

---

## Appendix D: v2 improvements (Phase 8 sprint, 2026-05-12)

### Context

Phase 8 ran a sustained dual-session sprint over 2026-05-11 → 2026-05-12
with the following division:
- **A**: Demo-guide documentation, screenshot embedding, article drafting,
  multi-language translation sync
- **B**: AWS deployment/verification, screenshot capture, code implementation
  (Theme A-N), CI/CD pipeline, observability

### Lessons learned

1. **VPC Endpoint conflict**: When B deployed UC1 with `EnableVpcEndpoints=true`,
   it failed because A's UC6 stack already had the same endpoints. Rule: always
   deploy with `EnableVpcEndpoints=false` in shared VPC environments. Added to
   `deployment-troubleshooting.md` as Failure Mode 7.

2. **Long-running executions**: UC1 took 2:38 with 549 files. During this time,
   B continued other work (UC7/UC8 screenshots, test fixes, Theme M/N). Rule:
   never block on a single UC execution — parallelize with other tasks.

3. **Screenshot file naming**: Phase 7 used `uc*-stepfunctions-graph.png`, Phase 8
   standardized on `step-functions-graph-{succeeded,zoomed}.png`. Old files became
   redundant but couldn't be deleted without A confirming demo-guide references.
   Rule: coordinate file renames via `[X] FILE RENAME PROPOSAL` notification.

4. **Theme L autoflake fallout**: Removing unused imports broke tests that patched
   the removed module paths. Discovered in UC9, UC10, UC12. Rule: after bulk
   import removal, run ALL UC tests (not just the modified UC's tests).

5. **S3AP IAM dual-format**: The alias-only IAM bug affected UC7/8/10/12/13 but
   was only discovered during AWS deployment. The `check_s3ap_iam_patterns.py`
   validator now catches this statically. Rule: run all validators before
   deploying any UC to AWS.

### v2 protocol additions

#### D-1: Pre-deployment validator gate

Before any `deploy_generic_ucs.sh` invocation, run:
```bash
python3 scripts/check_s3ap_iam_patterns.py
python3 scripts/check_handler_names.py
python3 scripts/check_conditional_refs.py
```
If any validator fails, fix before deploying. This prevents wasting
15-30 minutes on a deployment that will fail at runtime.

#### D-2: Shared VPC deployment rules

- Always set `EnableVpcEndpoints=false` and `EnableS3GatewayEndpoint=false`
  when deploying to a VPC that has existing Interface/Gateway Endpoints.
- Document which stack "owns" the VPC Endpoints in the sprint chat.
- Only one stack at a time should have `EnableVpcEndpoints=true`.

#### D-3: Screenshot lifecycle

- New screenshots use `step-functions-graph-{succeeded,zoomed}.png` naming.
- Old `uc*-stepfunctions-graph.png` files are deprecated.
- Before deleting old files, post `[X] FILE DELETE PROPOSAL: <path>` and
  wait for the other session to confirm no demo-guide references remain.

#### D-4: Test regression after bulk changes

After any bulk operation (autoflake, template parameter addition, etc.):
```bash
for uc in */; do
  [ -d "$uc/tests" ] && python3 -m pytest "$uc/tests/" -q --tb=line 2>&1 | tail -1
done
```
This catches cross-UC test breakage that single-UC testing misses.

#### D-5: Context transfer format

When a session's context window is compacted, the transfer summary MUST include:
- Current git branch + HEAD commit SHA
- List of uncommitted files (if any)
- Active AWS resources (running stacks, executing Step Functions)
- Next immediate action
- Any pending notifications to the other session
