# Handing the portal over, and answering the questions — File Portal

🌐 **Language / 言語**: [日本語](portal-handover-guide.md) | English

> For the person who prepared the infrastructure: **what to hand to users**, and **what to answer when
> they ask**. Every item says where the value comes from, where it is managed, and how to share it.

---

## How the three documents relate

The portal has three kinds of document with three different readers. **Handing the wrong one over means
giving a deployment runbook to somebody holding a phone.**

| Document | Reader | Contents | Hand over? |
|----------|--------|----------|-----------|
| [Getting Started](GETTING-STARTED.en.md) | Infrastructure owner | VPC endpoints, Secrets Manager, `portal-config.ts`, deployment | **No** (yours) |
| **This document** | Infrastructure owner | What to hand over, where things live, how to answer | **No** (yours) |
| [Phone walkthrough](../../../docs/en/portal-mobile-guide.md) | User (phone) | Sign-in through every action, with screenshots | **Yes** |
| [User guide](../../../docs/en/portal-user-guide.md) | User (desktop) | Every feature | **Yes** |

Once the deployment is done, continue at the [handover checklist](#handover-checklist) below.

---

## The three things a user needs

> **Before handing over the AI processing tab**: the Step Functions ARN in the resolver is still
> a placeholder. Handed over unconfigured, a user can press a button that fails. Either configure
> it or hide the tab by setting `processingEnabled` to `false` in `src/portal-settings.ts`. The
> steps are in [Extending the portal UI](CONTRIBUTING-UI.en.md#replacing-the-ai-processing-jobs-with-your-own).


That is all. **Anything more brings your infrastructure concerns into their hands.**

| What | Where it comes from | How to share it |
|------|--------------------|-----------------|
| **The portal URL** | See [what the URL actually is](#what-the-url-actually-is) | Team wiki, or a pinned message. Somewhere permanent |
| **An account** (email + initial password) | See [creating an account](#creating-an-account) | **Do not paste the password into chat.** Use a credential manager, or send it individually on the understanding that it will be changed |
| **The URL of the guide** | [Phone walkthrough](../../../docs/en/portal-mobile-guide.md) / [User guide](../../../docs/en/portal-user-guide.md) | Alongside the portal URL. **Send the URL alone and you will get usage questions** |

> **What not to hand over**: the `fsxadmin` password, the file system ID, the management LIF address, the
> Secrets Manager secret name, VPC or subnet IDs. None of it is needed to use the portal, and none of it
> needs to appear in an answer.

---

## Behind "what you need"

The user guide's [what you need](../../../docs/en/portal-mobile-guide.md#what-you-need) lists three
items. Here is **what each one actually is, where it is managed, how to obtain it, and what changing it
affects** — the answers to "what is this?".

### What the URL actually is

| How it is served | Shape of the URL | How to obtain it | Permanence |
|------------------|------------------|------------------|-----------|
| Amplify Hosting | `https://demo.<app-id>.amplifyapp.com`, or a custom domain | `make portal-hosting` to create it, `make portal-hosting-url` to read it back | **Fixed. This is the one to hand over** |
| Local plus a tunnel | `https://<random>.trycloudflare.com` and similar | The output of `npm run phone` ([steps](GETTING-STARTED.en.md)) | **Changes every run. Do not hand it over** — it is for checking on your own handset |
| Local | `http://localhost:5173` | The output of `npm start` | Your machine only. **Not reachable from anyone else's** |

**It has to be `https://`.** Sign-in (SRP) uses `crypto.subtle` and copying a share link uses
`navigator.clipboard`; browsers restrict both to a secure context. `http://localhost` is exempt, a LAN
address such as `http://192.168.x.x` is not. **Serving the LAN IP with `npm run dev -- --host` cannot
complete sign-in.** See
[Getting Started, "Checking it on a real phone"](GETTING-STARTED.en.md#checking-it-on-a-real-phone).

Run `make portal-hosting` from the repository root. It uploads the bundle built locally as a zip,
so it needs no git connection and consumes no build minutes.

**The URL is only as fixed as the backend behind it.** `main.tsx` imports `amplify_outputs.json`
statically, so **the user pool and the GraphQL endpoint are compiled into the bundle**. Delete and
recreate the sandbox and the page still loads, still renders the sign-in form, and **rejects every
credential**. `make portal-hosting-url` reports what the published bundle was built against
(sandbox name and pool ID) and warns when that disagrees with the current `amplify_outputs.json`.
The repair is to run `make portal-hosting` again.

### Creating an account

Accounts live in the **Cognito user pool**. Its ID is in `amplify_outputs.json`.

Normally one command from the repository root does it: creation, a password that satisfies the
pool's policy, and the role and scope grant. It states what the role unlocks before granting it.

```bash
make portal-demo-user ARGS='--username demo@example.com \
  --groups storage-admin,internal --expected-sandbox demo'
```

The password is shown once and never written to disk.

Authorization has two axes, and one value of each is required. The **role** decides which
operations AppSync accepts: `viewer` reads, `contributor` adds file and folder writes,
`storage-admin` covers everything group-gated, and `auditor` reads the audit trail without being
able to write. The **scope** decides which data is reachable: `external` confines a caller even
when the role is `storage-admin`, and denies the AI endpoints, so a full-access demo account wants
`internal`. What `storage-admin` unlocks that cannot be undone is set out below.

**Pass `--expected-sandbox`.** It stops before creating anything when the outputs file points at a
different sandbox's pool. Creating an account in the wrong pool is not an error at creation time —
it surfaces later as a portal that renders correctly and refuses every sign-in.

The rest of this section is the manual route, doing what the script does.

```bash
cd solutions/amplify-portal
POOL=$(python3 -c "import json;print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

# 1. Create (SUPPRESS if you do not want an invitation email)
aws cognito-idp admin-create-user --user-pool-id "$POOL" \
  --username <user@example.com> --message-action SUPPRESS \
  --user-attributes Name=email,Value=<user@example.com> Name=email_verified,Value=true

# 2. Set the initial password (without --permanent the user is asked to change it at first sign-in)
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
  --username <user@example.com> --password '<initial-password>' --permanent
```

**The password has to satisfy the pool's policy**, or it fails with
`InvalidPasswordException: Password does not conform to policy`. The default requires 8
characters with upper case, lower case, a digit and **a symbol**; the symbol is the one people
forget. Check the current policy:

```bash
aws cognito-idp describe-user-pool --user-pool-id "$POOL" \
  --query 'UserPool.Policies.PasswordPolicy' --output json
```

One way to generate a conforming value:

```bash
python3 -c "import secrets,string;a=string.ascii_letters+string.digits;print(''.join(secrets.choice(a) for _ in range(14))+'-Aa1')"
```

**Decide where the value will live before you create it.** "Do not paste it into chat" implies
somewhere else has to hold it. Without a credential manager, put it in a gitignored directory
(`.private/` in this repository) and hand over the file path rather than the value.

**Only if they need the administration sections** (resource management, analytics), add them to the
group. For an account that already exists, `make portal-grant-roles` does this and is a dry run
until `--apply`. The raw CLI is:

```bash
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" \
  --username <user@example.com> --group-name storage-admin
```

> **They must sign out and in again afterwards.** Group membership travels in the ID token, so an
> existing token does not carry it. That is the answer to "I was given access but the menu is not there".
>
> The group itself is created by `amplify/auth/resource.ts`; only the membership is manual.

> **`storage-admin` reaches operations that cannot be undone**: creating a SnapLock volume,
> enabling snapshot locking, and extending a retention period are all reachable from the
> administration screens. The handler-side `acknowledgeIrreversible` flag **does not gate a person
> clicking** — the frontend sends it as a literal.
>
> The membership is removable, so remove it once the demo is over.
>
> ```bash
> aws cognito-idp admin-remove-user-from-group --user-pool-id "$POOL" \
>   --username <user@example.com> --group-name storage-admin
> ```
>
> When the administration screens are not part of the demo, `contributor` instead of
> `storage-admin` still covers browsing, upload, rename and move.

### The browser

Current Safari on iOS or Chrome on Android. Nothing to configure.
**Private browsing works, but the language and theme choices are not retained** — they use `localStorage`.

---

## What the user said → what to check

This maps one to one onto the user guide's
[when something goes wrong](../../../docs/en/portal-mobile-guide.md#when-something-goes-wrong).

**Decide first whether there is anything to investigate.** Half of these end with an explanation.

### Nothing to investigate — just answer

| What the user says | What is actually happening | The answer |
|--------------------|---------------------------|-----------|
| There is no menu | On a phone the drawer starts closed | Tap **☰** at the top left |
| The list looks empty | The buttons above it stack, so the list is below them | Scroll down |
| It downloaded instead of previewing | That type has no preview | Images, PDFs and text open in place; the rest download |
| I cannot find share, rename or delete | Row actions live behind **⋮** | Tap **⋮** on the row; a sheet appears at the bottom |
| The text is small | By design | Pinch to zoom. Fields are at least 16px, so tapping does not zoom |
| It says "PHI — AI blocked" | AI processing in a protected folder is deliberately refused | Run it from a folder outside those paths |
| I was given access but the admin menu is missing | The ID token predates the group | **Sign out and back in** |

### Worth investigating

| What the user says | Check first | Usual cause |
|--------------------|-------------|-------------|
| Cannot sign in; the button does nothing | Whether the URL is `https://` | A LAN `http://` address was handed out → [what the URL actually is](#what-the-url-actually-is) |
| Cannot sign in; it says the password is wrong | `UserStatus` from `aws cognito-idp admin-get-user --user-pool-id "$POOL" --username <user>` | Still `FORCE_CHANGE_PASSWORD` → set it again with `--permanent` |
| A message about ONTAP | `make ontap-preflight FS_ID=<fs-id> LAMBDA=<function-name>` | One of six stages → [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md#start-with-make-ontap-preflight) |
| The screen is cut off and I cannot reach a button | Ask which screen and which button | **A defect.** Nothing should scroll sideways at phone widths → [verification steps](../../../docs/en/portal-mobile-guide.md#what-has-been-verified) |
| I cannot see files, or only some of them | Permissions, or the S3 Access Point's scope | [Authorization model](../../../docs/en/portal-authorization-model.md) |

> **For anything about ONTAP, the fastest move is to ask for the heading and the error detail verbatim.**
> The portal classifies the cause into one of five classes and prints ONTAP's own message, the HTTP
> status and the error code unchanged. That wording decides which layer to look at. The network is only
> worth suspecting for `UNREACHABLE`.

---

## Replies you can copy

**Handing over the URL and the account**

```
The file portal is ready for you.

URL: https://<portal-url>
Account: <user@example.com>
Password: sent separately

How to use it (phone): <mobile-guide-url>
How to use it (desktop): <user-guide-url>

There is no app to install — just open the URL in your browser.
If something does not work, send me the wording that is on the screen.
```

**When someone reports a message about ONTAP**

```
Thanks for reporting it. This is a storage-side problem, not something you did wrong.
Could you send me the heading and the contents of "Error details" exactly as they appear?
(Browsing, uploading and AI processing are unaffected in the meantime.)
```

**Answering a question that is really about behaviour, e.g. the missing menu**

```
On a phone the menu is hidden by default, because the screen is narrow.
Tap the ☰ at the top left to open it; choosing an item closes it again.

The step-by-step version with screenshots is here: <mobile-guide-url>
```

---

## Where everything lives

**So you are not hunting for a value a second time.**

| Item | Where it is managed | How to check it |
|------|--------------------|-----------------|
| The portal URL | Amplify Hosting (app / branch) | `aws amplify list-apps` |
| User accounts | Cognito user pool | `aws cognito-idp list-users --user-pool-id "$POOL"` |
| Admin membership | Cognito group `storage-admin` | `aws cognito-idp list-users-in-group --user-pool-id "$POOL" --group-name storage-admin` |
| Pool ID, API endpoint | `amplify_outputs.json` (generated by the deployment; **do not hand-edit**) | `cat amplify_outputs.json` |
| ONTAP target (management IP, SVM, volume) | `amplify/portal-config.ts` | `grep ontap amplify/portal-config.ts` |
| The `fsxadmin` credentials | Secrets Manager | `aws secretsmanager get-secret-value --secret-id <secret-name>` |
| The file system, SVM and volume themselves | FSx for ONTAP | `make ontap-preflight FS_ID=<fs-id>` |
| Regions and accounts searched | `discoveryRegions` / `discoveryAccounts` in `amplify/portal-config.ts` | `aws lambda get-function-configuration --function-name <PlatformDiscoveryFunction> --query "Environment.Variables"` |
| Who did what | The portal's "Audit trail" tab | The portal UI |

> **`amplify_outputs.json` is a build artifact.** Editing it by hand is undone by the next deployment.
> Change `amplify/` instead.

---

## When a data platform is not in the list

The "Data platform scope" control at the top of the admin panels lists FSx for ONTAP
file systems read from the AWS control plane. It uses no ONTAP credential and needs
no route to the management LIF, so **this list answers even when ONTAP does not**.
There are three reasons something is absent, and they are fixed in different places.

| Symptom | Cause | What to do |
|---------|-------|-----------|
| Absent, with no reason given | That region **was not searched** | See "widening the search" below |
| Absent, with a reason given | That account and region **could not be read** | The role or the permission named in the reason |
| Absent although it exists | The file system is not `AVAILABLE` | Check the state with `aws fsx describe-file-systems` |

Only the first cannot be explained from the response. Something that could not be
read is reported with its reason, but **a region nobody named is simply never looked
for**, so there is nothing to report.

The third happens in practice. A file system that is `CREATING` or `DELETING` is left
out: offering something that is not answering as a scope produces an empty list,
which reads as an empty system rather than as a transition.

The control itself renders **only when there are two or more platforms**. With one
there is nothing to choose, so it stays out of the way.

### What gets searched

By default, **every region this account has enabled**. The region names are not
written into the configuration: a list goes stale the next time AWS adds a region,
and by the first reason above nobody would notice. The enabled regions are asked for
at runtime instead.

The time it takes scales with the search. **Measured 2026-08-29 from the Lambda, 25
enabled regions with two of them not answering: 17.5 s cold, 14.9 s warm.** The
browser caches the answer for five minutes, so this is not paid per action, but the
first paint after opening the page takes a few seconds.

### Narrowing the search

Limiting the search makes it faster, and is the better choice when it is known which
regions hold anything.

```bash
AMPLIFY_PORTAL_DISCOVERY_REGIONS="ap-northeast-1,ap-northeast-3" npx ampx sandbox --identifier <name>
```

With this set, the enabled regions are not asked for and only the listed ones are
searched. **A region left off the list is not searched**, so it has to be extended as
the estate grows.

### Adding another account

Create a read-only role in the other account under a name shared by all of them; the
ARN is built as `arn:aws:iam::<account>:role/<name>`.

1. In the other account, create a role allowing only these three actions:
   `fsx:DescribeFileSystems`, `fsx:DescribeStorageVirtualMachines`,
   `ec2:DescribeRegions`
2. In that role's trust policy, allow `sts:AssumeRole` from the portal's discovery
   function role
3. Configure the portal and redeploy

```bash
AMPLIFY_PORTAL_DISCOVERY_ACCOUNTS="111122223333,444455556666" \
AMPLIFY_PORTAL_DISCOVERY_ROLE_NAME="PortalDiscoveryReader" \
  npx ampx sandbox --identifier <name>
```

Without `AMPLIFY_PORTAL_DISCOVERY_ROLE_NAME` the listed accounts are **skipped rather
than attempted**. An attempt with no role fails as an authorization error against
this account, which makes unfinished configuration look like a permissions problem
here.

The `sts:AssumeRole` grant covers only that role name in the accounts listed.

### Listed but not selectable

An entry marked `not connected` cannot be selected. This deployment's ONTAP actions
address one management address, so no request can be routed to another platform.
**Making it selectable would offer a scope that every action then fails against.**

Listing it is still worth doing for a different reason: one screen shows the whole
estate, so which file systems exist and which SVMs they hold can be seen without
opening each one's own console.

## Handover checklist

After deploying, before handing anything to a user:

- [ ] `make ontap-preflight FS_ID=<fs-id> LAMBDA=<function-name>` reports **all six stages PASS** (a SKIP from omitting `LAMBDA=` is not a PASS)
- [ ] There is a permanent `https://` URL, and you are not about to hand out a tunnel URL
- [ ] The user's account exists and its `UserStatus` is `CONFIRMED`
- [ ] Only the people who need it are in `storage-admin`
- [ ] You signed in from that URL in a browser on your own machine
- [ ] The file list opened at phone width, or on a real handset
- [ ] You sent **the URL, the account, and the guide's URL** — all three
- [ ] The password is not in a chat message
- [ ] They know who to ask

---

## Related documents

| Document | When to use it |
|----------|----------------|
| [Getting Started](GETTING-STARTED.en.md) | While building it |
| [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md) | While investigating a message about ONTAP |
| [Phone walkthrough](../../../docs/en/portal-mobile-guide.md) | Handing it over, or checking what the behaviour is |
| [User guide](../../../docs/en/portal-user-guide.md) | Handing it to a desktop user |
| [Authorization model](../../../docs/en/portal-authorization-model.md) | Working out why something is not visible |
| [Amplify Hosting production guide](../../../docs/en/amplify-hosting-production-guide.md) | Getting a permanent URL |
| [Cleanup guide](cleanup-guide.en.md) | Taking the environment down |
