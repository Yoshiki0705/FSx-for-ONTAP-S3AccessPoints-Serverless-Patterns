# Portal probes

Scripts that check a **deployed** portal against a **live** FSx for ONTAP cluster.

They exist because the unit tests cannot answer the questions that actually broke: whether a Lambda can reach ONTAP, whether the shared modules are packaged, whether a confirmation gate survived a deployment, and whether a subnet has a route to the service a handler depends on.

Every containment defect found so far was found here rather than by the test suite.

| Script | Reads | Writes | What it answers |
|--------|:-----:|:------:|-----------------|
| `probe_containment.py gates` | ✅ | — | Do all four containment actions refuse without `confirm=true`, and does the protected-account guard hold? |
| `probe_containment.py blocks` | ✅ | — | What is blocked right now, when does it expire, and did the portal place it? |
| `probe_containment.py svms` | ✅ | — | Which SVMs can be targeted? |
| `probe_containment.py ttl` | ✅ | ⚠️ | Does a block expire and does the sweep actually lift it from ONTAP? |
| `probe_containment.py fanout` | ✅ | ⚠️ | Does a block across several SVMs report per-SVM results correctly? |
| `probe_containment.py lift` | ✅ | ⚠️ | Removes one named block. For clearing one left behind. |
| `diagnose_vpc_egress.py` | ✅ | — | Which AWS services can the VPC functions actually reach? |
| `verify_shared_layer.py` | ✅ | — | Does the attached layer really contain `shared/`, with its subpackages? |

## Safety

- **Nothing is hardcoded.** No account ID, VPC ID, subnet ID, route table ID or SVM name appears in these scripts. Everything is discovered at runtime, so a probe cannot silently target the wrong environment.
- **Account IDs are masked** in output. VPC, subnet and route table IDs are not, because you need them to act on what the probe tells you — check before pasting a transcript somewhere public.
- **The writing probes use `PROBEONLY\portalprobe01`**, a principal that should not exist in any directory, so a block on it denies nothing real. NFS probes use `203.0.113.99` from the RFC 5737 documentation range.
- **They clean up after themselves** and report what remains.
- **They ask first.** Any probe that changes state prompts unless `--yes` is passed.
- `lift` is the exception to "no real targets": it takes a `--domain` and `--username` you supply, because its whole purpose is to remove a real block.

### These probes trip the unattributed-action alarm

They invoke the ARP function directly, so their containment actions arrive with no Cognito identity and are recorded as `unattributed` / `direct-invoke`. That raises `<stack>-containment-unattributed-action` on the first one.

This is intended. The alarm exists to catch a state-changing containment action that nobody is accountable for, and a probe run is exactly that — the fact that you meant it is not something the function can see. Exempting the probes would leave a hole shaped like the thing being watched for.

If you run probes routinely, either expect the alarm and close it, or point `alarmEmail` at somewhere that will not be mistaken for production alerting. See [the authorization model](../../docs/en/portal-authorization-model.md#what-happens-when-the-lambda-is-invoked-directly).

## Usage

```bash
# Read-only, safe to run against anything
python3 scripts/portal-probes/probe_containment.py gates
python3 scripts/portal-probes/probe_containment.py blocks --all-svms
python3 scripts/portal-probes/diagnose_vpc_egress.py
python3 scripts/portal-probes/verify_shared_layer.py

# Writing probes, prompt before acting
python3 scripts/portal-probes/probe_containment.py ttl
python3 scripts/portal-probes/probe_containment.py fanout

# Clear a block someone left behind
python3 scripts/portal-probes/probe_containment.py lift --domain CORP --username someone
```

All scripts take `--region` (default `ap-northeast-1`) and exit non-zero on failure, so they can be chained in a shell or a runbook.

## When to reach for which

**A containment action fails and you do not know why.** Run `verify_shared_layer.py` first — a failed import is the most common cause and produces error text that looks like something else entirely. Then `diagnose_vpc_egress.py`, because a hang that ends in a timeout reads as a failure of whatever the caller asked for, not of the network.

**A block will not expire.** `probe_containment.py blocks` shows `managedByPortal`. If it is `false`, the sweep is correctly leaving it alone: it was not placed by the portal, and this component cannot know the intent behind it. Use `lift` to remove it deliberately.

**Expiry is not happening at all.** `diagnose_vpc_egress.py` will say whether DynamoDB is reachable. Without it, blocking still works and reports `expiryTracked: false`, which is visible only to someone reading the response of an individual action.

## Related

- [ARP/AI isolation demo guide](../../docs/en/arp-ai-isolation-demo-guide.md) — what the containment actions do and where the boundary sits
- [Authorization model](../../docs/en/portal-authorization-model.md) — who may run them
- [Portal getting started](../../solutions/amplify-portal/docs/GETTING-STARTED.md) — `vpcRouteTableIds` and why it is required
