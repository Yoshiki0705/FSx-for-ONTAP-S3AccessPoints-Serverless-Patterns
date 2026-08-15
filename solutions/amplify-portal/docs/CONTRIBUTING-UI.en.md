# Extending the portal UI — developer guide

🌐 **Language / 言語**: [日本語](CONTRIBUTING-UI.md) | English

> For developers **adding a feature to the portal or changing an existing screen**.
> It says what breaks when you touch what, and which gate catches what, in the order
> those things were actually broken.
>
> To use the portal, read the [User Guide](../../../docs/en/portal-user-guide.md) instead;
> to stand one up, [Getting Started](GETTING-STARTED.en.md).
>
> **New to Amplify? Read from "The shape of it" through "Hands on" in order.**
> Section 0 onward is about which gate catches what, and does not need to be read first.

---

## The shape of it — which file is which screen

The first step in extending anything is guessing which file holds the screen you want to
change. The portal is **one page whose section is switched from the sidebar on the left**, and
one sidebar entry corresponds to one component.

![The portal's sidebar and content area. On the left, sections grouped into Browse, AI and processing, Data protection, and Admin; the chosen section fills the wide area on the right](screenshots/portal-sidebar-layout.png)

Three places tell you the mapping.

| What you want to know | Where to look |
|---|---|
| Which entries the sidebar has | `NAV_ITEMS` in `src/App.tsx` (an array of `{ id, icon, labelKey, group }`) |
| What is drawn when one is chosen | `{activeSection === "..." && <XxxPanel />}` in the same `src/App.tsx` |
| The entry's label string | The key named by `labelKey` in `src/i18n/locales/ja.ts` |

Admin panels live in `src/components/admin/`, file operations in `src/components/`. The names
track the screen names (the SMB share screen is `admin/CifsShareManager.tsx`).

**The best file to read first** is `src/components/admin/EfficiencyPanel.tsx` (132 lines). It is
the minimal shape of a read-only panel and contains one of everything that follows:
`dispatch`, `useQuery`, `t()`, and error rendering.

---

## Starting the environment

Two commands. `sandbox` **once**, `npm start` from then on.

```bash
cd solutions/amplify-portal

npx ampx sandbox   # once; creates your own AWS environment and amplify_outputs.json
npm start          # sandbox + Vite. Opens http://localhost:5173
```

`npx ampx sandbox` is Amplify Gen2 creating **a backend of your own** on AWS (Cognito, AppSync,
Lambda, DynamoDB). The `amplify_outputs.json` it generates is gitignored, and **the screen will
not start without it**. The first run takes 3 to 15 minutes, depending on whether a VPC is
configured ([the measured breakdown](verification-results.en.md)).

You get a sign-in screen.

![The portal's sign-in screen, with email and password fields and a sign-in button in the centre](screenshots/portal-login.png)

After signing in, this. Getting here means you are set up.

![The portal after sign-in: the sidebar on the left and a file listing in the content area](screenshots/portal-main-view.png)

> **No FSx for ONTAP yet?** With `DemoMode=true` the portal starts without one and drives an
> ordinary S3 bucket, and the ONTAP admin panels say "ONTAP connection required". See
> [Getting Started](GETTING-STARTED.en.md).
>
> **Want it on a real phone?** `npm run phone`. Signing in over `http://<LAN-IP>` does not work,
> because `crypto.subtle` is restricted to a secure context.

---

## Hands on — three stages

**Do not start with a new feature.** The three stages below widen the blast radius and add
gates in this order. Stage 1 shows you the loop from edit to screen; stage 3 shows the loop for
adding a new ONTAP operation.

### Stage 1 (10 minutes) — change one string on screen

**Purpose**: experience the edit → screen → gate loop with a change that cannot break anything.

UI strings are **not written in components**. They live as keys in the eight language files and
are read with `t("key")`.

1. Search the locale file for the text you want to change. To change what an English reader
   sees, that is `en.ts`.

```bash
grep -n "Storage Efficiency" solutions/amplify-portal/src/i18n/locales/en.ts
```

This example returns **two** hits (`dashEfficiency` and `rmEfficiency`), because the same string
is used on two screens. **Confirm which key the screen uses before changing it** — searching the
component (`src/components/admin/EfficiencyPanel.tsx` here) for `t("...")` is the reliable way.
Change one and the other screen keeps the old text.

2. Change the value of the key you want.

```typescript
// src/i18n/locales/en.ts
rmEfficiency: "Storage Efficiency",   // the admin panel's heading
```

Editing an existing translation is per-locale like this. **Adding a new key is different**: it
goes into `ja.ts` first, because that file is the source of the type the other seven implement.

3. The browser reloads itself (Vite HMR). Open the same screen in English and you get the value
   from `en.ts`.

![The file listing in Japanese](screenshots/portal-ja-allfiles.png)
![The same screen in English, with the sidebar entries and headings in English](screenshots/portal-en-allfiles.png)

4. **If you added a new key**, add it to `ja.ts` first and then to the other seven languages. A
   missing key **does not compile**, because `ja.ts` is the source of the type and the others
   implement a `Record` of the same keys.

```bash
make drift   # eight-language coverage, and the hardcoded-string check
```

> **How not to write it**
>
> ```tsx
> <h2>Storage efficiency</h2>                      // ✗ reaches only one language
> <button aria-label="Delete">                     // ✗ aria-label, title and placeholder count too
> <h2>{t("rmEfficiency") || "Storage efficiency"}</h2>  // ✗ the right side is unreachable (below)
> <h2>{t("rmEfficiency")}</h2>                     // ✓
> ```
>
> Product names, technical terms (ONTAP, FlexCache, SnapLock, S3 AP) and SQL literals are **not
> translated**.

### Stage 2 (30 minutes) — add a read-only row to an existing panel

**Purpose**: surface a value the ONTAP response already carries but the screen does not show.
No handler change, so no backend redeploy.

Take the storage efficiency panel. This screen:

![The storage efficiency panel. Per volume, the dedupe and compression settings, logical used, physical used and savings ratio in a table, with the overall savings ratio above it](../../../docs/screenshots/storage-efficiency-panel.png)

The shape of the response is declared as an `interface` at the top of
`src/components/admin/EfficiencyPanel.tsx`.

```typescript
interface VolumeEfficiency {
  name: string;
  dedupe: string;          // ONTAP's enum string; anything but "none" means on
  compression: string;
  logicalUsedBytes: number;
  physicalUsedBytes: number;
  savingsRatio: number;
}
```

**That `interface` is a declaration of what the handler returns, not a contract.** There was a
defect where the `interface` and the response disagreed, and the panel rendered empty (the
comment at the top of the file has the history). **Look at the real response first.** Browser
devtools → Network → the `adminQuery` response is the quickest route.

Three steps:

1. Add the field to the `interface`, **under the name the handler actually returns**
2. Add a heading (`<th>`) with `t("...")`. Put the string in `ja.ts` as in stage 1
3. Add the value (`<td>`). For bytes, reuse the existing `toGiB()`

```bash
cd solutions/amplify-portal
npx tsc -b && npm run lint && npx vitest run
cd ../.. && make drift
```

> **Where this trips people up**: a value that stays `undefined` is usually a **name spelled
> differently from the handler's**, or an `interface` nested differently from the real response.
> An `interface` is only a declaration, so TypeScript cannot check that the handler returns that
> name.

### Stage 3 (1 hour) — add one ONTAP operation

**Purpose**: go around the whole loop, backend to UI. From here you cross **a boundary types do
not reach**, so the order matters. Skip a step and you get a button that renders and fails on
every click.

Section 0 explains why the boundary exists; the steps first.

**(1) Add it to the handler** (`functions/resource-management/handler.py`)

```python
elif action == "myNewAction":
    return _my_new_action(http, headers, event, user_id)
```

**(2) Regenerate the types** (never by hand)

```bash
python3 scripts/portal_action_types.py --emit > solutions/amplify-portal/src/lib/dispatchActions.ts
```

**(3) Call it from the screen**

```typescript
import { adminMutate } from "../../lib/dispatch";

await adminMutate<{ success?: boolean }>({
  action: "myNewAction",              // a literal, always. A computed name is unreadable to the checker
  params: { volumeUuid: vol.uuid },   // names must match the handler's exactly
});
```

**(4) Check the contract**

```bash
python3 scripts/check_portal_action_params.py
python3 scripts/check_portal_action_params.py --list-opaque   # calls that could not be read statically
python3 scripts/portal_action_types.py --check
```

If your call appears under `--list-opaque`, it is **a call that is not checked**. Remove a layer
of wrapping so that `action` is a literal.

**(5) Reuse the existing parts when a volume has to be chosen**

The hierarchy is file system → SVM → volume, and the selectors exist:

![The qtree panel's volume selector: dropdowns for choosing an SVM and then a volume](screenshots/qtree-volume-selector.png)

```tsx
<VolumeSelector label={t("rmSelectVolume")} onSelect={(vol) => setVolumeName(vol?.name ?? "")} />
```

`onSelect` **hands you `null`** (when the SVM changes and invalidates the pick, and when the
placeholder is selected). Writing `vol.name` is a compile error. The type is that way because
**a volume name is unique within an SVM, not within a file system**: resolving a leftover name
against a different SVM lands on a different volume.

**(6) If it cannot be undone, a confirmation is not enough**

SnapLock, snapshot locking, S3 Object Lock COMPLIANCE and starting a capacity rebalance **cannot
be undone**. "Are you sure?" leaves the person pressing it without the blast radius. The
existing dialog states the date and the range in words.

![The snapshot lock confirmation, giving the date until which deletion is impossible and stating that it cannot be undone](../../../docs/screenshots/snapshot-lock-confirm.png)

Use `SnaplockConfirmDialog` with `src/utils/snaplockConsequences.ts`, and require
`acknowledgeIrreversible` in the handler as well, so a call that bypasses the UI meets the same
gate. Section 5 has the detail.

### Changing a colour

Colours are read through `var(--color-*)`. Map them **by role, not by value**.

```tsx
<div style={{ color: "#fff" }}>              // ✗ unreadable in dark mode, and cannot be overridden
<div className="my-panel-title">             // ✓ use var(--color-text-inverse) in the CSS
```

The same screen, light and dark. A colour written inline breaks one of them.

![The file listing in the dark theme](screenshots/portal-files-dark.png)

A new token is defined in **both** `:root` and `[data-theme="dark"]`. One of the two fails
`make drift`.

---

## Replacing the AI processing jobs with your own

The AI processing tab sends the chosen use case to a Step Functions state machine.
**The six use cases listed by default are this repository's samples.** Using it in your own
organisation starts with removing the ones you do not want and adding your own workflow. Four
places are involved, so here they are in order.

### First, see the current state

```bash
cd solutions/amplify-portal
grep -n "ProcessingPattern" -A 10 amplify/data/resource.ts   # what the API accepts
grep -n "PATTERN_DESCRIPTIONS" -A 10 src/components/JobSubmitForm.tsx  # what the screen lists
grep -n "stateMachineArn" amplify/data/resolvers/start-processing.js   # what it actually calls
grep -n "processingEnabled" src/portal-settings.ts            # whether the tab appears
```

| Place | What it decides |
|---|---|
| `ProcessingPattern` in `amplify/data/resource.ts` | **The set of values the API accepts** (a GraphQL enum). AppSync rejects anything not listed |
| The `ProcessingPattern` type and `PATTERN_DESCRIPTIONS` in `src/components/JobSubmitForm.tsx` | **The dropdown and its descriptions** |
| `amplify/data/resolvers/start-processing.js` | **Which state machine is called**, and the input JSON it receives |
| `processingEnabled` in `src/portal-settings.ts` | Whether the tab appears at all |

> **These four do not stay in step by themselves.** Today the enum has seven values (including
> `FC7_FLEXCLONE_RESTORE`) while the screen lists six, so FC7 is accepted by the API and
> unreachable from the UI. Adding a value to the screen alone fails the other way, because
> AppSync rejects it. **The same value has to be in both.**

### Required before it can work at all

The ARN in `amplify/data/resolvers/start-processing.js` is **still a placeholder**.

```javascript
const stateMachineArn =
  "arn:aws:states:ap-northeast-1:123456789012:stateMachine:amplify-portal-test-workflow";
```

Neither the account ID nor the state machine name exists, so **pressing "start processing" in
this state fails**. Replace it with your own ARN. There is a `stateMachineArn` entry in
`portal-config.ts`, but **the resolver does not read it**: an AppSync JS resolver cannot import a
config file at runtime. You have to keep the config value and the ARN in step yourself.

IAM is scoped by a different value. `amplify/backend.ts` uses `config.stateMachineResourceScope`
as the `resources` of `states:StartExecution`. **Revisit that scope when you change the ARN.** If
it does not match, the resolver calls the right ARN and stops with AccessDenied.

### Removing a use case

Delete the same value from both places:

1. the `ProcessingPattern` array in `amplify/data/resource.ts`
2. the `ProcessingPattern` union and `PATTERN_DESCRIPTIONS` in `src/components/JobSubmitForm.tsx`

Changing the enum changes the GraphQL schema, so `npx ampx sandbox` has to redeploy. Removing
only the type and leaving the enum produces what FC7 is now: accepted by the API, absent from the
screen.

### Adding a use case

```typescript
// 1. amplify/data/resource.ts — what the API accepts
ProcessingPattern: a.enum([
  "UC1_LEGAL_COMPLIANCE",
  "MY_ORG_INVOICE_OCR",        // added
]),
```

```typescript
// 2. src/components/JobSubmitForm.tsx — what the screen shows
type ProcessingPattern =
  | "UC1_LEGAL_COMPLIANCE"
  | "MY_ORG_INVOICE_OCR";      // added

const PATTERN_DESCRIPTIONS: Record<ProcessingPattern, string> = {
  UC1_LEGAL_COMPLIANCE: "...",
  MY_ORG_INVOICE_OCR: "Invoice OCR and a draft journal entry",   // added
};
```

Because it is a `Record<ProcessingPattern, string>`, **forgetting the description does not
compile.** If a value you added does not appear on screen, check the enum first.

> **The descriptions do not go through `t()` today.** `PATTERN_DESCRIPTIONS` is English in the
> source and is outside the eight-language mechanism. For a multilingual deployment, add keys to
> `ja.ts` as in section 4, change it to `Record<ProcessingPattern, TranslationKeys>`, and read it
> with `t()`.

### What the state machine receives

This is the whole input the resolver sends:

```javascript
const input = JSON.stringify({
  inputPrefix: inputPrefix,
  parameters: parameters || {},
  triggeredBy: "amplify-portal",
  triggeredAt: util.time.nowISO8601(),
  userId: ctx.identity.username,
});
```

**The chosen use case is not in it.** It appears only in the execution name
(`portal-<pattern>-<epoch>`). So **one state machine cannot branch between use cases** as shipped.
Pick one of these:

- give each use case its own state machine and select the ARN from `pattern` in the resolver
- add `pattern` to the input and branch with a `Choice` state

For the second, add `pattern: pattern` to the resolver's `input`. That changes the state
machine's input schema, so check it stays compatible with existing executions.

### The history record

On success, `client.models.JobExecution.create` writes one row to DynamoDB (`executionArn`,
`pattern`, `inputPrefix`, `status`, `startDate`). **A failure to save is swallowed** with a
`console.warn`, so a job can run without appearing in the history. Fix that before treating the
history as an operational record. The model is owner-authorized, so only the submitter can read
their rows.

### After changing it

```bash
cd solutions/amplify-portal
npx tsc -b            # a missing PATTERN_DESCRIPTIONS entry surfaces here
npx ampx sandbox      # a changed enum needs a redeploy
```

Until you have a state machine, set `processingEnabled` in `src/portal-settings.ts` to `false` to
hide the tab. **It defaults to `true`**, so handing the portal over unconfigured leaves users a
button that fails.

---

## 0. Read this first

The portal has **two boundaries types do not cross**. Changes that cross them produced
most of the defects so far.

| Boundary | Why types stop there | What guards it |
|------|------------------|----------------|
| React → Lambda | The AppSync endpoints take an `action` (a string) and `params` (a JSON string). TypeScript cannot see the other side | Calls routed through `src/lib/dispatch.ts`, plus `dispatchActions.ts` generated from the handlers, plus `scripts/check_portal_action_params.py` |
| UI strings → 8 locales | A hardcoded string compiles, lints, and is noticed only by a reader of Japanese | `t()` over `ja.ts` as the source of the type, plus the i18n coverage rules in `make drift` |

The dispatch is generic because 73 operations as individual AppSync fields put the
CloudFormation template over the 1 MB limit (collapsed to 8 endpoints). That design is
fixed, but **the types can be recovered just before the boundary** — which is what
`dispatch.ts` and the generated map are for.

---

## 1. The path a request takes

```
React component
  └─ src/lib/dispatch.ts          … checks the action name and params, adds activeSvm
       └─ AppSync (amplify/data/resource.ts)   … 8 endpoints × query/mutation
            └─ amplify/data/resolvers/*-dispatch.js
                 └─ Lambda (functions/<name>/handler.py)
                      └─ ONTAP REST API / S3 AP / Bedrock / Athena
```

| File | Role |
|---------|------|
| `amplify/portal-config.ts` | Deployment-specific values: volume name, SVM name, S3 AP alias |
| `amplify/backend.ts` | CDK. Extra resources and policies |
| `amplify/data/resource.ts` | Endpoint definitions and authorization (`allow.groups(["storage-admin"])` and so on) |
| `functions/*/handler.py` | The Lambda that branches on `action`. The only layer that talks to ONTAP |
| `src/lib/dispatchActions.ts` | **Generated.** Do not edit by hand |

---

## 2. Adding one action

Four steps, and the order matters.

**① Add it to the handler**

```python
elif action == "myNewAction":
    return _my_new_action(http, headers, event, user_id)
```

Whether a parameter read from `event` carries a default changes its meaning. A required
parameter with no default should be refused explicitly when absent, rather than left to
land on some other resource silently.

**② Regenerate the types**

```bash
python3 scripts/portal_action_types.py --emit > solutions/amplify-portal/src/lib/dispatchActions.ts
```

The generated map comes from the parameter names the handlers read. An action that reads
`svm` joins `ACTIONS_ACCEPTING_SVM`, and `dispatch` then fills in the current scope.

**③ Call it**

```typescript
import { adminQuery, adminMutate } from "../lib/dispatch";

const data = await adminMutate<{ success?: boolean }>({
  action: "myNewAction",          // ← a literal. A computed name is one the checker cannot read
  params: { volumeUuid: vol.uuid },
});
```

Do not call `client.mutations.*` directly. A call that does not go through `dispatch.ts`
is outside the parameter check.

**④ Check the contract**

```bash
python3 scripts/check_portal_action_params.py
python3 scripts/check_portal_action_params.py --list-opaque   # calls the checker cannot read
python3 scripts/portal_action_types.py --check
```

If your call appears under `--list-opaque`, it is **a call that is not being guarded**.
Unwrap one layer and make `action` a literal.

> **Why this check exists**: code that sends `{snapshotName, retentionDays}` to an action
> reading `snapshotId` and `expiryTime` compiles, lints, renders a button, and fails every
> time it is pressed. It shipped that way.

---

## 3. Adding or changing a screen

### Put the scope in the query key

```typescript
const activeSvm = useActiveSvm();
useQuery({
  queryKey: ["protection", "getArpStatus", activeSvm || null, volumeInScope || null],
  ...
});
```

Without the scope in the key, switching SVM **serves the other SVM's cached list**.
Invalidation can hide that, but a value the response depends on belongs in the key.

### Do not return early on loading or error

```typescript
// ✗ unmounts the scope controls too, so picking a volume that does not exist is unrecoverable
if (error) return <div><h2>{title}</h2><OntapFailureNotice error={error} /></div>;

// ✓ keep the header and the scope row, replace only the body
{loading && !data && <p className="loading">{t("loading")}</p>}
{error && <OntapFailureNotice error={error} {...failureDiagnosis(queryError)} />}
```

`isPending` **goes true again for every new query key**, so judging on `loading` alone
blanks the screen on each scope change. `loading && !data` is the "nothing to show yet"
condition.

### Reuse the existing hierarchy

Three levels: file system (fixed by the connection) → SVM → volume. Aggregates are not
one of them: on FSx for ONTAP, AWS manages them and the operator does not choose one.

```tsx
{/* Beside the heading: the volume the response named, and whether that was a pick */}
<VolumeScopeBadge volumeName={volumeName} isDefault={!volumeInScope} />

{isStorageAdmin === true && (
  <div className="protection-scope">
    <SvmSelector />
    <span className="protection-scope-chain" aria-hidden="true">›</span>
    <VolumeSelector label={t("rmSelectVolume")} onSelect={(vol) => { ... }} />
  </div>
)}
```

The badge answers **why this volume**, not which one. Before a pick, the name on screen is
the volume the deployment is configured with, and a name alone does not say so.

### `VolumeSelector`'s `onSelect` hands you `null`

When an SVM change voids the pick, and when the placeholder is chosen. Writing `vol.name`
is a compile error, which is the reason for the type.

```typescript
onSelect={(vol) => setVolumeName(vol?.name ?? "")}
```

A volume name is unique within an SVM, not within a file system, and **same-named volumes
across SVMs are ordinary**. Actions that resolve a name — creating a qtree, a quota rule, a
SnapLock retention — would resolve a leftover name in the new SVM and **land on a different
volume**. Actions keyed by UUID are safe.

### Hiding a control in the UI is not the authorization

`adminQuery` and `adminMutation` are refused server-side by
`allow.groups(["storage-admin"])`. `useStorageAdmin()` decides only **whether to offer the
menu** (`null` means not known yet).

---

## 4. Strings and colours

| Subject | Rule | Detail |
|------|-------|------|
| UI strings | Add to `ja.ts` first, then the other seven. Use `t("key")`. Never hardcode in JSX text, `aria-label`, `title` or `placeholder` | [portal-i18n](../../../docs/agent/portal-i18n.md) |
| What not to translate | Product names and technical terms (ONTAP, FlexCache, SnapLock, S3 AP), SQL literals | as above |
| Colours | Use `var(--color-*)`. No colour literals in JSX `style={{ }}`. A new token is defined in both `:root` and `[data-theme="dark"]` | `src/index.css` |

Never write `t("key") || "fallback"`. `t()` ends in `?? key`, so it is always truthy and the
right-hand side is unreachable. A misspelled key renders as the key.

Map colours **by role, not by value**: `white` is `--color-text-inverse` as a text colour and
`--color-surface` as a background. An inline style cannot be overridden later, so it pins
that element to one theme.

---

## 5. Adding an irreversible operation

SnapLock, snapshot locking and S3 Object Lock COMPLIANCE **cannot be undone**. Files still
under retention block deletion of the volume, then the SVM, then the file system.

| Do this | Where |
|---------|------|
| Show a confirmation that states the consequence in words | `SnaplockConfirmDialog` + `src/utils/snaplockConsequences.ts` |
| Require `acknowledgeIrreversible` in the handler | `functions/*/handler.py` |
| Say in the UI what becomes undeletable, and until when | the panel itself |

A dialog that only collects a number of days does not convey irreversibility. Name the date,
and say it cannot be released. Background and measurements are in
[pitfalls-snaplock](../../../docs/agent/pitfalls-snaplock.md).

---

## 6. Tests

| Subject | Location | Run |
|------|---------|------|
| React components, hooks, lib | `tests/components/`, `tests/hooks/`, `tests/lib/` | `npx vitest run` |
| Lambda handlers | `functions/<name>/tests/` | `python3 -m pytest solutions/amplify-portal/functions/<name>/tests/ -q` |
| CDK and infrastructure | `tests/infrastructure/` | `npx vitest run` |

Component tests mock `src/lib/dispatch`; `tests/components/QtreeManager.test.tsx` and
`tests/components/VolumeSelector.test.tsx` are the smallest examples of the shape.

**Verify without breaking hardware**: a state that only appears when the real response
changes — a truncated listing, say — is pinned with a mocked response rather than by
lowering a limit in the Lambda. That avoids both leaving the limit deployed and leaving
nobody able to reproduce it later.

---

## 7. Before committing

```bash
cd solutions/amplify-portal
npx tsc -b        # types
npm run lint      # eslint (--max-warnings 0)
npx vitest run    # front-end tests

cd ../..
make drift        # the gates below
make lint         # ruff check + ruff format --check
python3 -m pytest solutions/amplify-portal/functions/<the function you changed>/tests/ -q
```

Of what `make drift` looks at, these concern the portal. Every one of them was added after
shipping without it.

| Gate | What it catches |
|-------|------------|
| `check_portal_action_params.py` | Calls sending parameter names no handler reads |
| `portal_action_types.py --check` | The generated action set drifting from the handlers |
| `check_portal_drift.py` (theme rules) | Colour literals, colours in inline styles, undefined tokens |
| `check_portal_drift.py` (i18n rules) | Untranslated UI strings, keys missing from any of the 8 locales |
| `check_portal_drift.py` (query rule) | Reading `isPending` on a query gated by `enabled: false` as loading (a spinner that never clears) |
| `test_iac_completeness_rules.py` | Authorization on a Cognito group nothing declares, environment variables no template sets |
| `check_doc_pairs.py` | Documents with only one of JA/EN, relative links that resolve to nothing |

CI runs the equivalents in `.github/workflows/`: `ci.yml`, `lint.yaml`,
`agent-output-audit.yml`, `iam-policy-validation.yml`.

---

## 8. Failures we actually hit

| Symptom | Cause | Lesson |
|------|------|------|
| A lock button that had never once worked | It sent a name and a duration to an action reading a UUID and an absolute expiry | Cover an untyped boundary with a check |
| Pressing a button did nothing | Placeholders were mistaken for values, leaving it `disabled` — and `.btn-danger` stayed red with an unchanged cursor while disabled | Say on screen why it cannot be pressed |
| Protection that was enabled read as "not configured" | The screen could only ever describe the one configured volume | Let the scope be chosen |
| Picking a volume that does not exist left the page unusable | The error path returned early, above the scope controls | Do not unmount the way back |
| The qtree panel spun forever | No volume meant `enabled: false`, that was read as loading through `isPending`, and the spinner hid the volume control needed to pick one | `isPending` means pending, not loading |
| A deleted resource was still there | ONTAP returned success and silently declined | Judge on the state a minute later, not on the response |

---

## 9. Related documents

| Document | When to read it |
|-------------|---------|
| [Implementation Guide](IMPLEMENTATION.en.md) | Following design intent and the change log |
| [Getting Started](GETTING-STARTED.en.md) | Standing up an environment |
| [ONTAP Connection Guide](ONTAP-CONNECTION-GUIDE.en.md) | An ONTAP panel shows no data |
| [Admin Capability Map](admin-capability-map.en.md) | Implementation status of the 20 panels and their ONTAP endpoints |
| [portal-cdk-quality-gates](../../../docs/agent/portal-cdk-quality-gates.md) | The CDK under `amplify/`, and cdk-nag |
| [portal-i18n](../../../docs/agent/portal-i18n.md) | The full 8-locale rules |
| [pitfalls-s3ap-ontap](../../../docs/agent/pitfalls-s3ap-ontap.md) | S3 AP and ONTAP API pitfalls |
| [CONTRIBUTING](../../../CONTRIBUTING.md) | How to open a PR |
