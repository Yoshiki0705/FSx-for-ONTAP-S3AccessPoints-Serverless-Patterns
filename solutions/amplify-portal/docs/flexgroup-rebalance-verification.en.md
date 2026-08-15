# FlexGroup capacity rebalancing, measured

🌐 **Language / 言語**: [日本語](flexgroup-rebalance-verification.md) | English

A record of running capacity rebalancing end to end against a FlexGroup on FSx for
ONTAP through the REST API. The centre of it is that **two constraints are not in the
API reference, and together they leave only half of each hour in which an operation can
be started at all**.

## The findings first

| Observation | Detail |
|---|---|
| The maximum runtime has a floor | **Under 30 minutes is refused** (`144182221`). Not in the API reference |
| It also has a ceiling | It must be **shorter than the time to the volume's next scheduled snapshot** (`13107433`). Also not in the reference |
| The default always fails | ONTAP's own `max_runtime` default is 6 hours. On a volume using the default snapshot policy (hourly at :05) that **always hits the ceiling** |
| When a start is possible | Following from the two above, with the default policy: **only between :05 and :35 of each hour** |
| Two volume states are undocumented | `idle` (running with nothing to move) and `scheduled` (a future start), neither listed among the volume-level values |
| Irreversibility confirmed | Starting sets `granular_data` to `true` / `basic`, and **stopping does not undo it** |
| A refused start has no side effect | `granular_data` stayed `false` after every refusal |

## Environment

| Item | Value |
|---|---|
| Region | ap-northeast-1 |
| ONTAP version | 9.17.1P6 |
| Volume | `zz_fg_probe`, created for this and deleted afterwards |
| Geometry | FlexGroup 400 GiB, 4 constituents of 100 GiB |
| Snapshot policy | `default` (hourly, at :05) |
| Date | 2026-08-15 |
| Path | Portal `resource-management` Lambda to ONTAP REST `PATCH /storage/volumes/{uuid}` |

> **Note**: the volume was **nearly empty**. With no file over 100 MB, no file movement
> took place. "Watching an imbalance clear" is not part of this record; what was
> observed is **the conditions a start is accepted under, the state transitions, the
> diagnostic counters and the irreversibility**. The two should not be conflated.

## 1. Before starting

```
state=not_running  granular=False/disabled  imbalance=0%  worst=0%  runtime=''
```

Freshly created, with granular data off. Every setting ONTAP holds on the volume was at
its default and matched the documentation.

| Field | Measured |
|---|---|
| `max_runtime` | `PT6H` |
| `min_file_size` | 104857600 (100 MB) |
| `max_threshold` / `min_threshold` | 20 / 5 |
| `max_file_moves` | 25 |
| `exclude_snapshots` | `true` |

## 2. Four ways a start was refused

### 2-1. Collision with a scheduled snapshot (`13107433` / HTTP 409)

`maxRuntime=PT1H` requested at 15:59:47, with the next snapshot due at 16:05:00:

```
The next scheduled snapshot for volume "zz_fg_probe" in SVM "fsxsvm01" is scheduled for
Sat Aug 15 16:05:00 2026, in 0h5m12s. This is within the specified 1h0m0s maximum runtime
for the volume capacity rebalancing operation, which started at Sat Aug 15 15:59:48 2026.
To run the operation, either reduce the "-max-runtime" or disable the snapshot policy for
the volume.
```

**The same refusal came back for `PT6H`, and for omitting `maxRuntime` entirely** (which
applies ONTAP's 6 hour default). So **the value the portal offered first could never
start**. Fixing that is the direct result of this exercise.

### 2-2. Pinning the boundary (A/B)

After waiting for the 16:05 snapshot to be taken, two requests one second apart:

| Time | `maxRuntime` | Time to next snapshot | Result |
|---|---|---|---|
| 16:06:12 | `PT1H` (60 min) | 58m47s | **Refused** (`13107433`) |
| 16:06:13 | `PT30M` (30 min) | 58m46s | **Accepted** |

The test is `max_runtime` < time remaining to the next snapshot: 60 > 58m47s refused,
30 < 58m46s accepted. One second between the two requests, so the deciding factor is
the value of `max_runtime` and not the passage of time.

### 2-3. The floor (`144182221` / HTTP 400)

Trying `PT3M` to get under the ceiling from 2-1:

```
The "-max-runtime" value specified must be 30 minutes or longer.
```

**A floor of 30 minutes.** Combined with the ceiling above, a start is accepted only
when:

```
30 minutes <= max_runtime < (time from the start to the next scheduled snapshot)
```

With the default policy (hourly at :05) the right-hand side starts at 60 minutes and
counts down, so **only :05 to :35 leaves room for 30 minutes**. With a frequent schedule
such as `5min` the right-hand side never reaches 30 minutes, and **no start is possible
without lifting the policy**. This is why ONTAP's own message offers both remedies:
"reduce the -max-runtime **or disable the snapshot policy**".

### 2-4. A start time in the past (`144182233`)

```
The specified rebalancing start time is not valid. The start time must be set to the
current time or a later time.
```

## 3. While it runs

Polling `/storage/volumes/{uuid}?fields=rebalancing` about every 10 seconds after
starting with `PT30M`:

```
16:06:15  start requested -> success
16:06:18  state=idle    granular=True/basic  runtime=PT3S    moved=0
16:06:30  state=idle                         runtime=PT15S   moved=0
16:07:22  state=idle                         runtime=PT1M7S  moved=0
16:08:26  state=idle                         runtime=PT2M11S moved=0
```

A second run showed `rebalancing` briefly before settling into `idle`:

```
16:17:37  state=rebalancing  runtime=PT6S
16:17:46  state=idle         runtime=PT15S
```

What was observed:

- **`granular_data` flips to `true` / `basic` as the operation starts**, within seconds.
- **`idle` is returned as a volume state.** The REST reference describes `idle` as a
  *constituent* state and does not list it among the volume-level values. A client that
  implements only the documented volume list therefore **renders a running rebalance as
  "unknown"** — which is what happened, and was fixed.
- **A run with nothing to move emits no notice at all.** `notices` stays empty,
  `imbalance_percent` and `data_moved` stay at zero, and only `runtime` moves. "Working"
  and "found nothing to work on" are **indistinguishable from the state alone**.
- What does distinguish them is `rebalancing.engine`, which must be requested explicitly:

```json
{ "scanner": { "files_scanned": 0, "blocks_scanned": 0,
    "files_skipped": { "too_small": 0, "too_large": 0, "fast_truncate": 0,
      "in_snapshot": 0, "efficiency_blocks": 0, "efficiency_percent": 0,
      "incompatible": 0, "metadata": 0, "remote_cache": 0, "write_fenced": 0,
      "on_demand_destination": 0, "footprint_invalid": 0, "other": 0 } },
  "movement": { "file_moves_started": 0 } }
```

The names in `files_skipped` map directly onto the two default exclusions the guidance
warns about: `too_small` (under 100 MB) and `in_snapshot`. **Nothing else answers "it
says it is running and nothing is changing".**

### Usage per constituent

`constituents.space` gives each member's own figures.

| Constituent | Size | Used |
|---|---|---|
| `zz_fg_probe__0001` | 100 GiB | 537,300,992 B (512.4 MiB, 0.5%) |
| `zz_fg_probe__0002` | 100 GiB | 537,313,280 B |
| `zz_fg_probe__0003` | 100 GiB | 537,309,184 B |
| `zz_fg_probe__0004` | 100 GiB | 537,305,088 B |

**A freshly created FlexGroup is not empty.** Each constituent holds about 537 MB of
metadata, roughly 2.1 GB across the volume (`space.metadata` is 56 MB each,
`total_metadata_footprint` 60 MB each). Each member also held about 795 KB of snapshot
data.

The volume reported 0% imbalance with an `imbalance_size` of 12,288 B — the members
differ by at most about 12 KB, so the even distribution is visible as a number.

## 4. Starting a second operation

Requesting a start while one is running (in `idle`) is refused by ONTAP
(`144182216` / HTTP 409):

```
The volume capacity rebalancing configuration cannot be updated for volume "zz_fg_probe"
in SVM "fsxsvm01" because a volume capacity rebalancing operation is running on the
FlexGroup. Wait for the operation to complete or stop the running operation before
attempting to update the configuration.
```

**The portal's own guard missed this.** It tested
`state in ("starting", "rebalancing")`, so the states a real volume actually returns —
`idle` and `scheduled` — passed straight through. ONTAP stopped it, so nothing was
harmed, but the condition is now inverted: anything other than `not_running` or
`unknown` counts as an operation in progress. **A guard that enumerates the states it
knows keeps missing the ones it does not.**

## 5. Stopping

```
16:10:02  stop requested -> success
16:10:08  state=not_running  granular=True/basic  runtime=PT3M49S  stop=16:10:04
16:10:24  (unchanged; runtime frozen at PT3M49S)
```

- `runtime` freezes at its final value and `stop_time` is filled in.
- **`granular_data` remains `true` / `basic`.** This is the measured confirmation of the
  irreversibility. The documentation states that once enabled it cannot be disabled and
  that restoring a snapshot taken beforehand is the way back; the behaviour matched.
- Stopping when nothing is running is refused with
  `Volume capacity rebalancing is not running.`

## 6. Scheduling

```
16:10:39  startTime=16:18:39, maxRuntime=PT30M -> success (scheduled=true)
16:10:45  state=scheduled  start=2026-08-15T16:18:39+09:00
16:10:47  stop requested -> success (cancels the schedule)
16:10:51  state=not_running  start=16:18:39 (retained)  stop=16:10:47
```

- **`scheduled` is also returned as a volume state** and is not in the reference.
- Cancelling is a PATCH with `state: stopping` — the same operation as stopping.
- **`start_time` keeps the cancelled timestamp afterwards.** A `stop_time` beside it
  makes the two distinguishable, but showing `start_time` unconditionally **announces a
  run that is not going to happen**; the panel now shows it only while `scheduled`.
- The snapshot check happens at request time for a schedule too, **measured from the
  scheduled start**: 16:50 with `PT30M`, requested at 16:11, was refused comparing
  `in 0h15m0s` (16:50 to 17:05) against `0h30m0s`. A schedule does not silently fail to
  run.

## 7. What this changed in the UI and the code

| Change | Because |
|---|---|
| Runtime options start at 30 minutes | 2-1 / 2-3. Leading with 6 hours meant the button failed every time on a volume with a snapshot policy |
| Both bounds and the ":05 to :35" window stated in the guidance | 2-1 / 2-3. Neither is in the API reference |
| `idle` and `scheduled` given labels | 3 / 6. A running rebalance read as "unknown" |
| The double-start guard inverted | 4. Stop enumerating state names; treat anything but `not_running` / `unknown` as in progress |
| Usage shown per constituent | 3. The imbalance is this list, not the summarised percentage |
| Scanner counters and skip reasons shown | 3. They are the only answer to "running but nothing is moving" |
| `start_time` shown only while scheduled | 6. It outlives a cancelled schedule |
| Elapsed time rendered as a clock | 3. ONTAP returns `PT1M32S` and it was displayed verbatim |
| ONTAP's messages passed through unaltered | 2-1. They name the exact snapshot time the operator needs |

## 8. Still not verified

- **An imbalance actually clearing.** That needs files over 100 MB placed unevenly, which
  this volume could not provide. `files_scanned`, `file_moves_started` and `data_moved`
  moving, and the `rebalancing_source` / `rebalancing_dest` constituent states, were not
  observed.
- **What happens when `max_runtime` is reached.** The 30 minute run was stopped after
  about 3 minutes rather than allowed to expire.
- **Contention with a SnapMirror transfer** (the documented 24 minute retry).
- **Total usage increasing when a deduplicated file is moved.**
- **A long run with the snapshot policy lifted.**

## References

- [Rebalance FlexGroup volumes by moving files](https://docs.netapp.com/us-en/ontap/flexgroup/manage-flexgroup-rebalance-task.html)
- [Balance FlexGroup volumes by redistributing file data](https://docs.netapp.com/us-en/ontap/flexgroup/enable-adv-capacity-flexgroup-task.html) (cannot be disabled once enabled)
- [Update volume attributes (every `rebalancing` field)](https://docs.netapp.com/us-en/ontap-restapi/ontap/patch-storage-volumes-.html)
- [Is it necessary to manually balance constituents of an S3 bucket hosting flexgroup?](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Is_it_necessary_to_manually_balance_constituents_of_an_S3_bucket_hosting_flexgroup%3F)
- Related pitfalls: [FlexGroup pitfalls](../../../docs/agent/pitfalls-flexgroup.md)
