# Extending the portal UI — developer guide

🌐 **Language / 言語**: [日本語](CONTRIBUTING-UI.md) | English

> For developers **adding a feature to the portal or changing an existing screen**.
> It says what breaks when you touch what, and which gate catches what, in the order
> those things were actually broken.
>
> To use the portal, read the [User Guide](../../../docs/en/portal-user-guide.md) instead;
> to stand one up, [Getting Started](GETTING-STARTED.en.md).

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
