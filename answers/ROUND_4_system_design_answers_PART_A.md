# Round 4 — System Design: Answers, Part A (focused questions)

Companion to `questions/ROUND_4_system_design.txt`. **Original question numbers are kept.**

Round 4 is split into two files:
- **Part A (this file)**: the focused questions. Ops/strategy questions with a sequenced answer (30, 31, 32, 34, 36, 38, 39, 40, 42) and the rapid deep-dive probes (43–54). Each one is answerable in 3–8 minutes.
- **Part B** (`ROUND_4_system_design_answers_PART_B.md`): the full 35–40 minute designs (1–29, 33, 35, 37, 41).

The probes in Part 5 (43–54) are always asked **about the design you just drew**. So for each one I give the general framework plus a worked example using the **rating & quoting engine (Q21)**, since that's your strongest domain design. Swap in whichever design you actually presented.

Notes marked **Your story:** need your real experience. Don't memorise my wording for those.

---

## PART 4 — CLOUD & DEVOPS (focused questions)

### 30. Design a zero-downtime deployment strategy for a service that holds long-lived connections and has a stateful in-memory cache.
Two separate problems: **draining long-lived connections** (WebSockets/SSE/gRPC streams) and **not losing or cold-starting the cache**.
**Connections**:
- Rolling update with `maxUnavailable: 0`, `maxSurge: 25%`, so capacity never drops.
- On termination: a `preStop` sleep so the pod leaves the load balancer first, then the app **stops accepting new connections** and tells existing clients to **reconnect elsewhere**. Send a WebSocket close frame with a "going away / reconnect" code, end SSE streams (the client reconnects with `Last-Event-ID`), or send a gRPC `GOAWAY`. Don't wait for hours-long connections to end naturally.
- **Stagger the disconnects** (jitter over 30–60s) so all clients don't reconnect at once and stampede the new pods. Clients reconnect with exponential backoff + jitter.
- Raise `terminationGracePeriodSeconds` to cover the drain window (e.g. 120s).
- Design clients to tolerate reconnects: resume state from a server-side store or an event offset, not from the connection.
**Stateful in-memory cache**:
- Best answer: **make the cache rebuildable and non-critical**. It's an optimisation; the source of truth is elsewhere. Then the problem is only *warm-up*.
- **Warm up before receiving traffic**: the new pod preloads the hot keys at startup (from the DB, a snapshot in blob/Redis, or the list of hot keys published by old pods), and the **readiness probe only passes once the cache is warm**. Rolling slowly means only a fraction of capacity is cold at any time.
- If the cache must survive pod restarts, move it out of process (**Redis**) or keep a **two-tier cache** (local L1 + shared L2), so a new pod's L1 fills from L2 instead of from the DB.
- If the cache holds state that **can't** be rebuilt (sessions, in-flight aggregates), that's the real design bug: externalise it.
**Validate**: watch the cache hit ratio and DB load during the rollout; deploy at low traffic; use a canary first.

### 31. We are on AKS, our cloud bill doubled in 3 months, and nobody knows why. Walk me through your investigation and the levers you'd pull, in order of effort vs saving.
**Investigate (find out what actually grew)**:
1. **Azure Cost Management → cost analysis grouped by service, resource group, meter, and tag**, over 6 months by day. The bill doubling is rarely "AKS" itself. It's usually one line: compute (node pools), managed disks, **egress/bandwidth**, **Log Analytics ingestion** (very common!), load balancers/public IPs, NAT gateway, storage transactions, or a forgotten GPU VM.
2. Find the inflection point (a date) and correlate it with changes: new service, node pool, autoscaler config, a new logging level, a new region, data migration.
3. **Inside the cluster**: which namespaces/workloads consume the nodes. Tools: **Kubecost / OpenCost** (or the AKS cost analysis add-on) to allocate node cost to namespaces/labels. Compare **requested vs actually used** CPU/memory per workload (requests are what you pay for, since they determine how many nodes you need).
4. Look for orphans: unattached disks, old snapshots, idle public IPs, forgotten dev/test clusters or node pools, PVCs from deleted apps, old images in ACR.
**Levers, from low effort/high saving to high effort**:
1. **Delete waste**: orphaned disks/IPs/snapshots, idle environments, unused node pools. Shut down dev/test clusters at night/weekends (`az aks stop` or scale to zero).
2. **Logging costs**: drop debug logs in prod, filter noisy namespaces (kube-system, health checks) from Container Insights, use Basic logs tier / shorter retention, sample traces.
3. **Rightsize requests** based on real usage (VPA recommendations / Kubecost), since overstated requests mean half-empty nodes. Then **cluster autoscaler** with sensible min counts.
4. **Rightsize node pools / VM SKUs**: better bin-packing with bigger nodes or the right family, newer generations (better price/performance), ARM (Ampere/Cobalt) nodes where images support it.
5. **Spot node pools** for fault-tolerant workloads (batch, CI runners, stateless workers): ~60–90% cheaper.
6. **Commitments**: Reserved Instances / Savings Plans for the stable baseline (once rightsized, not before!).
7. **Egress / architecture**: keep traffic in-region and in-zone, private endpoints, cache, compress, CDN.
8. **Governance so it doesn't happen again**: mandatory cost tags (team/service/env), budgets and anomaly alerts per subscription/team, showback dashboards, Azure Policy to block expensive SKUs.

### 32. Design a secrets management + rotation strategy across dev/stage/prod and 3 clouds. Include: what happens the day a prod DB credential leaks publicly.
**Principles**: (1) the best secret is no secret: use **workload identity / managed identity** (AKS workload identity, AWS IRSA/Pod Identity, GCP Workload Identity) for cloud resources and DBs that support it (Azure AD auth for Postgres, IAM auth for RDS); (2) one **source of truth** per environment; (3) everything short-lived and automatically rotated; (4) strict environment isolation: prod secrets are inaccessible from dev/stage, by different identities and different vaults.
**Design**:
- **Central secrets manager**: either one cross-cloud system (**HashiCorp Vault**/OpenBao, with dynamic DB credentials per pod that expire in hours), or each cloud's native manager (Key Vault / Secrets Manager / Secret Manager) with a consistent structure and naming, synced into Kubernetes by the **External Secrets Operator** or the CSI Secrets Store driver. Vault is better when you truly run on 3 clouds; native is simpler when one cloud dominates.
- **Separate vault/namespace per environment** and per team/service, with access policies by workload identity. Humans don't read prod secrets day-to-day; break-glass access is audited and alerted.
- **Rotation**: dynamic credentials (Vault database engine) or scheduled rotation (Secrets Manager rotation Lambdas, Key Vault rotation policies with Event Grid) with **two valid credentials overlapping** (rotate B while A is still valid, switch apps, then revoke A), so rotation causes no downtime. Apps must re-read secrets without a redeploy (watch for file changes, or short caching).
- **Prevention/detection**: secret scanning in pre-commit and CI (gitleaks, GitHub/ADO secret scanning with push protection), no secrets in env files, images, logs or Terraform state (state stored encrypted with restricted access), audit logs on every secret read.
**The day a prod DB credential leaks publicly (runbook)**:
1. **Rotate immediately**: create a new credential, roll it out to the apps (this is where tested, automated rotation pays off), **revoke the leaked one**. Revoke first if the exposure is severe and you accept some downtime.
2. **Contain**: check whether the DB is reachable from the internet at all (it shouldn't be: private endpoints, firewall allowlist). Tighten network rules.
3. **Investigate**: DB audit logs / `pg_stat_activity` / connection logs for logins with that user from unknown IPs since the leak time; check for data exfiltration or modification.
4. **Remove the leak**: delete the public post / rewrite git history, but assume it's already been copied (bots scrape GitHub within minutes).
5. **Incident process**: declare an incident, inform security/legal; if customer data may have been accessed, breach notification obligations (GDPR 72h) apply.
6. **Postmortem**: how did it leak, and why was a static long-lived credential needed at all? Move toward identity-based or dynamic credentials.

### 34. Design a disaster recovery plan for your most critical service. Define RTO/RPO, then tell me how you'd actually prove it works.
**Definitions**: **RTO** (Recovery Time Objective) = how long the service may be down. **RPO** (Recovery Point Objective) = how much data (in time) you may lose. They come from the **business impact** (Q52), not from engineering preference, and each nine costs money.
Example, for the quoting/rating service: RTO **1 hour**, RPO **5 minutes** for quotes/policies (regulated data, brokers can't quote while it's down, but an hour is survivable); the rater artifacts themselves RPO 0 (immutable, replicated).
**Plan by scenario** (DR isn't only "region down"):
- **Bad deploy / bug**: rollback (minutes).
- **Data corruption / accidental delete** (the most likely disaster!): **point-in-time restore** (Postgres PITR) to a new instance + selective repair (Q94 in Round 3). Backups must be **immutable** and in a separate account/subscription (ransomware, compromised admin).
- **Zone failure**: zone-redundant DB (HA standby in another AZ, automatic failover, RPO ≈ 0), pods spread across zones.
- **Region failure**: warm standby in a second region: **async read replica** of the DB in the paired region (RPO = replication lag, seconds to minutes), infra defined in IaC so the app stack can be created/scaled there, container images replicated (geo-replicated ACR), blob storage GRS, DNS/Front Door failover. Promote the replica, scale up the app, switch traffic.
- **Dependency failure** (identity provider, carrier API): graceful degradation.
**Prove it works**:
- **Regular restore tests**: automatically restore last night's backup into an isolated environment weekly and run data checks; a backup you haven't restored isn't a backup.
- **Game days / DR drills** (quarterly): actually fail over to the DR region (in prod during a quiet window, or in a full-scale staging), measure the real time to recovery and data lost, compare with RTO/RPO. Follow the runbook as written: anyone on call should be able to do it.
- **Chaos testing** for smaller failures (kill pods, a zone, a DB failover) with tools like Azure Chaos Studio / AWS FIS.
- **Monitor RPO continuously**: alert on replication lag and on backup job failures or age.
- After each drill: update the runbook, fix what slowed you down, record the measured RTO/RPO.

### 36. Design blue/green + canary for a service whose deploy includes a backward-incompatible DB migration. Sequence it precisely.
The key insight: **you can't blue/green a database**. Both versions of the app run against the same DB during the rollout (and after a rollback), so **no single deploy may contain a backward-incompatible schema change**. You split it into compatible steps: the **expand → migrate → contract** pattern (a.k.a. parallel change).
Example: rename `premium` to `gross_premium` (or split a column, change a type).
1. **Release 1: expand (schema only, additive)**: add the new column `gross_premium` (nullable, no default rewrite; `ADD COLUMN` without a volatile default is instant in modern Postgres). Old app ignores it. Fully compatible. Deploy.
2. **Release 2: dual write (app v2)**: app writes **both** columns, still reads the old one. Canary it: 5% → 25% → 100%, compare error rates. Rollback is safe: v1 doesn't know the new column exists.
3. **Backfill**: a batched, throttled job copies old → new for existing rows (`UPDATE ... WHERE id BETWEEN ... AND gross_premium IS NULL`, small batches, to avoid long locks and replication lag). Verify counts/checksums.
4. **Release 3: read from new (app v3)**: reads the new column, still writes both (so rolling back to v2 stays safe). Canary → 100%. Add the `NOT NULL` constraint the safe way: `ADD CONSTRAINT ... CHECK (...) NOT VALID`, then `VALIDATE CONSTRAINT` (no long lock).
5. **Release 4: stop writing old (app v4)**: once you're confident you won't roll back past v3.
6. **Release 5: contract (schema)**: drop the old column. Only now is the change irreversible.
Blue/green and canary sit on top: for each app release, deploy green alongside blue, route canary traffic (weighted ingress / Argo Rollouts / Flagger with automated analysis of error rate and latency), then switch. Every step is independently rollbackable because **every adjacent pair of app versions works with the current schema**.
Also: migrations run as a separate pipeline step (a K8s Job) before the app deploy, never on app startup from N pods; set `lock_timeout` on migrations so a migration that waits for a lock fails instead of blocking all traffic behind it.

### 38. Design an autoscaling strategy for a workload with a 20x spike every day at 9am that lasts 20 minutes. Compare HPA, KEDA, scheduled scaling, and overprovisioning on cost.
The spike is **predictable** and **short**, and that decides the answer: reactive autoscaling is too slow for a 20× jump (metrics lag ~1 min, HPA reacts, pods start, and if new **nodes** are needed the cluster autoscaler adds 3–5 min; by then a big part of the 20-minute spike is over and you've dropped requests).
- **HPA (CPU/memory/custom metrics)**: reactive, lags, and CPU is a lagging indicator. Cheap (pay only for what you use) but bad at sudden spikes on its own. Good for the unpredictable variations around the baseline.
- **KEDA**: scales on **leading indicators**: queue depth, Kafka lag, request rate from Prometheus. Reacts faster than CPU-based HPA, and can scale to zero. Also has a **cron scaler**. For queue-based workloads it's the best reactive option. Still limited by node provisioning time.
- **Scheduled scaling**: pre-scale at **8:50** to the expected peak (KEDA cron scaler, a CronJob that patches the HPA `minReplicas`, or a scheduled node pool scale-up), and scale back down at 9:30. Cost: you pay for peak capacity for ~40 minutes a day. Cheap and reliable because the spike is predictable. Risk: if the spike shifts (holiday, timezone, campaign) you're unprepared, so combine with reactive.
- **Overprovisioning 24/7**: provision for peak all day. Simplest and most reliable, and the most expensive (paying 20× for 23.5 hours to cover 20 minutes). Only acceptable if the workload is tiny. A variant that *is* worth it: a small amount of **"pause pod" overprovisioning** (low-priority placeholder pods that reserve spare node capacity and get evicted instantly when real pods need room), which hides node startup time for the reactive part.
**Recommended**: **scheduled pre-scaling for the known spike (pods and nodes), plus HPA/KEDA on top for variance, plus a little pause-pod headroom**, and make startup fast (small images, preloaded caches, readiness probes tuned). Also challenge the workload: can part of the 9am work be pre-computed at 8:30, or queued and smoothed? Load-test the 9am pattern and alert when capacity at 9:00 is below plan.

### 39. Design the incident response process end to end - detection, paging, triage, comms, mitigation, postmortem. What is your definition of a blameless postmortem?
1. **Detection**: alerts on **user-facing symptoms** (SLO burn rate on error rate/latency, synthetic checks of critical journeys), not on every cause (CPU high). Plus customer reports via support. Every alert links a runbook.
2. **Paging**: on-call rotation (PagerDuty/Opsgenie), clear escalation policy (primary → secondary → engineering manager), severity definitions agreed beforehand (SEV1 = customer-facing outage / data loss, SEV2 = degraded, SEV3 = minor). Only page for things that need a human now.
3. **Triage and roles**: the first responder acknowledges, assesses impact, sets the severity. For SEV1/2 declare an incident and assign roles: **Incident Commander** (coordinates and decides, doesn't debug), **Ops/tech lead(s)** (investigate and fix), **Comms lead** (updates), scribe. One incident channel and a bridge call; timeline written as you go.
4. **Comms**: internal status updates at a fixed cadence (every 30 min for SEV1), status page for customers, account managers for key clients, regulators/legal when data is involved. Say what's known, what's not, and when the next update will be.
5. **Mitigation before root cause**: restore service first: rollback, failover, feature flag off, scale up, shed load, block a bad client. Root cause analysis can wait until users are no longer affected.
6. **Resolution and follow-up**: confirm recovery with metrics, close the incident, hold a **postmortem** within a few days for SEV1/2.
7. **Postmortem**: timeline, impact (users, duration, money), root cause(s) and contributing factors, what went well, what went badly, where we got lucky, and **action items with owners and due dates** (tracked to completion, otherwise the postmortem is theatre). Share widely.
**Blameless postmortem**: the review assumes everyone acted reasonably given the information, tools and pressure they had at the time. It asks **"how did the system allow this to happen?"**, not "who did it", because people make mistakes and the fix is to change the system (guard rails, automation, better alerts, safer defaults), not to punish someone. If people fear blame, they hide information, and you lose the truth you need to prevent the next incident. Blameless doesn't mean no accountability: owners still deliver the action items.

### 40. You inherit infrastructure with no IaC, 200 hand-built resources, and no one who remembers why. How do you get to Terraform without an outage?
Principle: **import, don't recreate.** Bring existing resources under Terraform management as they are, prove there's no diff, and only then start changing things.
1. **Inventory**: list everything (Azure Resource Graph / AWS Config / `az resource list`), with tags, dependencies, costs, and activity (who calls it, metrics, last modified). Figure out the owner and purpose of each. Flag likely-unused resources (but **don't delete yet**).
2. **Back up and freeze**: snapshots/backups of stateful resources; a change freeze on manual console edits (or at least logging them) during the migration. Enable activity logs.
3. **Set up the Terraform foundations**: remote state with locking (Azure Storage / S3 + DynamoDB), module structure, separate state per environment and per layer (network, data, compute), CI pipeline with `plan` on PR and `apply` with approval.
4. **Generate code from reality**: tools like **Azure aztfexport** (formerly aztfy), **Terraformer**, or Terraform's native **`import` blocks with `terraform plan -generate-config-out`** produce HCL from existing resources. Then clean it up into readable modules.
5. **Import resource by resource, lowest risk first** (e.g. monitoring, DNS records, storage), stateful/critical last (databases, networking). After each import, `terraform plan` must show **no changes**. If the plan wants to change or **replace** something, fix the code to match reality (or add `lifecycle { ignore_changes }` for drifting attributes), never apply a destroy/recreate. Protect critical resources with `prevent_destroy`.
6. **Lock down manual changes**: once a resource is managed, remove console write access for humans (read-only + break-glass), and run scheduled drift detection (a nightly `plan` that alerts on diffs).
7. **Only then improve**: rename, restructure, add tags, remove unused resources (deprecate first: stop them, wait, then delete), each change through a reviewed PR.
**Your story:** you added multi-region infra via Terraform at StatusNeo, so use that to show real familiarity with state, modules and plans.

### 42. Design the migration of a stateful Postgres workload from on-prem to cloud with under 5 minutes of downtime.
The trick: **replicate continuously while the old DB stays live, so cutover is just "stop writes, let the replica catch up, switch"**: seconds to minutes of downtime instead of hours of dump/restore.
1. **Choose the target**: managed Postgres (Azure Database for PostgreSQL Flexible Server / RDS / Cloud SQL), same or newer major version. Check extensions and settings are supported.
2. **Network**: VPN/ExpressRoute/Direct Connect between on-prem and the cloud network, enough bandwidth for the initial copy.
3. **Initial sync + continuous replication**: either **logical replication** (`CREATE PUBLICATION` on-prem, `CREATE SUBSCRIPTION` on the target; works across versions, but doesn't replicate DDL or sequences, and tables need primary keys), or a managed tool (**Azure Database Migration Service** online mode, **AWS DMS**, which use logical decoding underneath). Physical replication works only when you control both sides (rarely possible with managed targets).
4. **Validate while it runs**: row counts and checksums per table, replication lag ≈ 0, run the app's read traffic / test suite against the target, performance tests (cloud disks have different latency/IOPS than local SSDs, so check query plans and the connection latency from wherever the app will run).
5. **Rehearse the cutover** on a staging copy end to end, with timings.
6. **Cutover** (in a low-traffic window):
   - Lower DNS TTLs days in advance (or switch via app config / PgBouncer, which is faster than DNS).
   - Put the app in maintenance/read-only mode (stop writes) → wait for replication lag = 0 → **sync sequences** (logical replication doesn't do this: set each sequence on the target to the source's current value + margin) → run final checksums on critical tables → repoint the app to the cloud DB → re-enable writes. Typical total: 1–5 minutes.
7. **Rollback plan**: set up **reverse replication** (cloud → on-prem) right after cutover so you can switch back without losing new writes, and keep the old DB for a few days.
8. Moving the app to the cloud at the same time? Move the DB and app together or the app first, since an on-prem app talking to a cloud DB adds latency on every query.

---

## PART 5 — RAPID DEEP-DIVE PROBES (asked about the design you just presented)

### 43. In your design, exactly where can data be lost? Name every point.
Framework: follow one piece of data from the client to durable storage and ask at **every hop**: "if this component crashes right now, what's lost?". Typical points:
1. **Client → API**: request sent, response lost (timeout). Did it happen or not? → client retries, so the API must be **idempotent** (idempotency keys).
2. **In-memory buffers**: anything accepted but held in RAM (in-process queues, batching, write-behind cache, async logging) is lost if the pod dies. Ack to the client only after the data is durable.
3. **Fire-and-forget background tasks** (`create_task`, FastAPI `BackgroundTasks`): lost on restart/deploy.
4. **Queue/broker**: messages acked before processing (auto-ack) are lost if the worker crashes; non-persistent queues, Redis as a broker without persistence; retention expiring before consumers catch up; messages discarded after max retries without a DLQ.
5. **Dual writes** (DB + queue/cache/blob): one succeeds, the other fails (outbox fixes it).
6. **Database**: async replication → a failover loses the last few seconds of commits (RPO > 0); `synchronous_commit=off`; un-backed-up data; a bad migration or bug overwriting data (logical loss, the most common!).
7. **Cache-only data** (Redis as primary store without AOF/replication).
8. **Third-party calls**: the carrier/partner API accepted a request but we failed to record the response.
9. **Deletion/retention policies** and human error (a wrong `DELETE`).
Worked example, **rating engine (Q21)**: the quote request is persisted (inputs, rater version, outputs) **in the same transaction** before returning the quote ID, so the only loss window is a region-level async replication failover (RPO ≈ seconds), which is accepted and documented. The quote-created event goes through an outbox. Rater artifacts are immutable and geo-replicated, so they can't be lost.

### 44. Where is the single point of failure you've accepted, and why is it acceptable?
Every real design has some. The good answer **names it explicitly** and justifies it with cost vs probability vs impact vs mitigation. Typical accepted SPOFs:
- **The primary database / single write region**: everything writes to one Postgres primary (with a zone-redundant standby). True multi-primary is much more complex (conflicts) and the business tolerates a few minutes of failover.
- **The cloud region** (single region, with backups + IaC to rebuild elsewhere): multi-region active-active costs 2× and adds a lot of complexity; acceptable when the RTO allows hours.
- **The identity provider** (Entra ID / Auth0): if it's down, nobody can log in. Accepted because it's a managed service with a better SLA than we could build; mitigated by long-ish token lifetimes for existing sessions.
- **A third-party dependency** like the carrier API (can't fix it; you degrade gracefully: queue binds and retry later).
- **The CI/CD system** or a single DNS provider.
Worked example, **rating engine**: "The single write region is our SPOF. Zone failures are covered by zone-redundant Postgres and pods across 3 zones. A full regional outage means read-only mode and a manual failover to a warm standby within the 1h RTO. That's acceptable because brokers can tolerate an hour without quoting a few times a decade, and active-active would double cost and introduce write-conflict risk on financial records."

### 45. Traffic goes 10x tomorrow with no warning. What breaks first, second, third?
Framework: find the **component that doesn't scale horizontally** or has a fixed limit, in order of how soon it hits the wall. Usual order:
1. **Database connections** (pods autoscale ×10 → connection pools ×10 → `max_connections` exhausted, Round 3 Q92). Often the first thing to break, sooner than the DB's CPU.
2. **The database itself**: CPU/IOPS on the primary for write-heavy paths, lock contention on hot rows, queries that were fine at 1× now do seq scans that hurt. Reads can be offloaded to replicas/cache; writes can't easily.
3. **Third-party rate limits and quotas**: LLM API tokens/minute, carrier API limits, Graph API throttling, email provider limits, cloud quotas (vCPU quota in the subscription, so the cluster autoscaler can't add nodes!).
4. **Autoscaling speed**: HPA + node provisioning take minutes; until then pods are saturated, latency rises, and retries amplify the load (retry storm, Round 3 Q27).
5. **Caches**: cache size or Redis memory/CPU (single-threaded); a cache stampede if hot keys expire under load.
6. **Queues/workers**: backlog grows, SLA misses, and the age of the oldest message exceeds visibility timeouts → duplicates.
7. **Cost** (doesn't "break", but the bill does).
Then say what you'd do: rate limit/load shed to protect the core, pooler (PgBouncer), raise quotas, scale reads via cache/replicas, queue and smooth writes, degrade non-essential features.
Worked example, **rating engine**: rating itself is a pure stateless function and scales horizontally fine; what breaks first is **Postgres writes of quote records** + connection count, then any **external enrichment API** (address/credit lookups) rate limits.

### 46. Cut the cost of this design by 60%. What do you sacrifice?
Framework: find where the money goes (usually compute, the DB, data storage/egress, logging, third-party/LLM APIs) and trade **availability, latency, freshness, or retention**:
- **Availability**: drop multi-region / hot standby → single region with backups (sacrifice RTO/RPO); fewer replicas; zone-redundant only for the DB.
- **Compute model**: spot/preemptible nodes for workers and batch; scale to zero for low-traffic services (serverless / KEDA); commitments (reserved instances/savings plans) for the baseline; rightsize requests (often 30–50% alone).
- **Freshness/latency**: precompute in batch instead of real-time; longer cache TTLs; async instead of sync processing.
- **Data**: shorter retention in hot storage, tier old data to cool/archive blob, drop indexes nobody uses, downsize the DB tier and add read caching.
- **Observability**: sample traces (1–10%), shorter log retention, drop debug logs, metrics with fewer labels.
- **Third-party/LLM**: smaller models for simple steps, caching of responses, batch APIs (often 50% cheaper), fewer calls via deterministic pre-filters.
- **Managed vs self-hosted**: sometimes self-hosting is cheaper in cash but costs engineering time; say that trade-off.
The key is to say **what the business loses** with each cut (e.g. "RTO goes from 1h to 8h; dashboards are 1 hour stale instead of live") and let the business choose.

### 47. Now build the same thing with a 2-person team in 6 weeks. What do you throw away?
Framework: keep the **core value and correctness**, throw away **scale, flexibility and operational sophistication** you don't need yet. Use **managed services and boring tech** everywhere.
Throw away / defer:
- Microservices → **one modular monolith**, one repo, one deploy.
- Kubernetes → **a PaaS** (App Service / Container Apps / Cloud Run / Railway) or serverless functions.
- Kafka/event streaming → a DB-backed job queue or a simple managed queue (Service Bus / SQS).
- Multi-region, active-active, DR drills → single region, managed backups.
- Custom auth → managed identity provider.
- Custom admin UI → a generic admin (e.g. SQLAdmin / Django admin / Retool).
- Feature flag service, service mesh, custom observability → managed APM (App Insights / Sentry) defaults.
- Self-service authoring UIs → configuration files + a manual process for the few users.
- Perfect automation of rare operations → runbooks.
**Never throw away**: data correctness (transactions, idempotency on money/quotes), security basics (auth, secrets, encryption, tenant isolation), backups, audit trail if regulated, and CI with tests on the core logic. Those are the things that are expensive or impossible to add later.
Worked example, **rating engine**: v1 = one FastAPI app on Container Apps + managed Postgres + blob storage for versioned rater artifacts; the transpiler runs as a CLI/pipeline step; no A/B testing, no self-service upload UI (a pull request uploads a new workbook), but quotes are still stored with exact inputs and rater version from day 1.

### 48. Which component here would you buy instead of build, and what's the lock-in risk?
Framework: buy what's **commodity and not differentiating**, build what **is** the product. For each bought component, state the lock-in and the **exit strategy**.
Typical buys: identity/SSO (Entra ID, Auth0, Cognito), managed DB, queues, observability (Datadog/App Insights/Grafana Cloud), document OCR/extraction (Azure Document Intelligence, Textract), email/SMS delivery (SendGrid/Twilio/ACS), feature flags (LaunchDarkly), PDF rendering, search (Azure AI Search/Elastic Cloud), LLM APIs.
Lock-in risks: proprietary APIs/data formats (migration requires rewriting integrations), data gravity (petabytes stored there; egress costs to leave), price increases at scale, vendor outage = your outage, compliance/data-residency changes, the vendor discontinuing a feature.
Mitigations: put each vendor behind **your own interface/adapter** (a `DocumentExtractor` Protocol with an Azure implementation) so switching means one new adapter, not a rewrite; prefer open standards (OIDC, OpenTelemetry, SQL/Postgres-compatible, S3-compatible APIs); keep your data exportable in open formats; contractual SLAs and exit clauses.
Worked example, **rating engine**: **don't buy the rating engine itself** (it's the core differentiator and regulator-facing), but buy identity, managed Postgres, observability and maybe the Excel calculation oracle (Excel via Graph API) used in testing. Lock-in on Azure-managed Postgres is low (it's still Postgres); on Document Intelligence it's medium (proprietary output schema → wrap it).

### 49. How do you migrate this design from v1 to v2 with live traffic and no downtime?
Framework, the standard toolkit:
- **Strangler fig**: put a routing layer (API gateway / ingress / a facade in the app) in front; route endpoints/tenants/traffic percentages to v2 one at a time while v1 keeps serving the rest. v1 shrinks until it can be deleted.
- **Data migration via expand/contract** (Q36): new schema/store added alongside; **dual write** or **CDC replication** from old to new store; backfill historical data; verify; switch reads; stop writing old; remove old.
- **Shadow traffic / dark launch**: send a copy of real requests to v2, compare its responses with v1's (diffing), discard v2's output. Find behaviour differences before users see them. Excellent for things like a new rating engine version: run old and new rater side by side and compare premiums.
- **Gradual rollout with feature flags/canary**: 1% → 10% → 50% → 100% by tenant or user, with automated rollback on error/latency regression.
- **Backward-compatible contracts**: API versioning or additive changes, so clients don't need a synchronized deploy; events versioned with schema compatibility rules.
- **Rollback at every step**: until the final contract step, you can always go back to v1 without data loss (keep v1's data in sync during the transition).
Worked example, **rating engine**: v2 rater runtime runs in **shadow mode** next to v1 for every live quote, with discrepancies logged per rater version; once the mismatch rate is 0 for a week per product, flip that product to v2 via a flag; quotes keep a record of which engine version produced them.

### 50. What would you monitor to know this system is healthy - give me the 5 dashboards and 5 alerts, no more.
Framework: dashboards for **understanding**; alerts only for **user-facing symptoms that need a human now**. Use **RED** (Rate, Errors, Duration) for services, **USE** (Utilization, Saturation, Errors) for resources, and business KPIs.
**5 dashboards**:
1. **Service overview / SLOs**: request rate, error rate, p50/p95/p99 latency per key endpoint, SLO error-budget burn.
2. **Business health**: quotes per minute, quote success rate, bind/issue counts, premium volume, by product/tenant. Catches problems technical metrics miss (e.g. 200 OK but every premium is 0).
3. **Dependencies**: latency/errors of DB, cache, queues, external APIs (carrier, LLM), with circuit-breaker state.
4. **Async pipeline**: queue depth, age of oldest message, consumer lag, throughput, DLQ size, job durations.
5. **Infrastructure / saturation and cost**: CPU/memory vs requests/limits, pod restarts/OOMKills, node count, DB CPU/IOPS/connections/replication lag, daily cost trend.
**5 alerts that page**:
1. **SLO burn rate** on availability (error rate) for critical endpoints (multi-window, e.g. 2% budget burned in 1 hour).
2. **SLO burn rate on latency** (p99 above target).
3. **Business KPI anomaly**: quote volume drops to near zero during business hours, or quote failure rate spikes (the "silent failure" alert).
4. **Async backlog**: age of oldest message > SLA (e.g. submissions not processed within 15 min) or DLQ growing.
5. **Data safety**: DB replication lag / backup failure / storage near full / connections > 85% (things that become unrecoverable if ignored).
Everything else (high CPU, a pod restart) is a ticket or a dashboard, not a 3am page.

### 51. Where in this design does eventual consistency become visible to a user, and is that acceptable?
Framework: list every **asynchronous hop** between a write and a later read, and look at it **from the user's point of view**: when would they notice the delay or the stale state? Typical places:
- **Read replicas / caches**: the user saves something and the next page (served from a replica/cache) shows the old value. **Usually not acceptable for the user's own writes** → read-your-writes (route to primary for that user, Round 3 Q47).
- **Search indexes / dashboards / analytics** updated via CDC/ETL: new records don't appear in search or reports for seconds or minutes. **Usually acceptable** if the UI says "data as of 10:42".
- **Async workflows**: "submission received" shows before extraction is done; document generation happens after issue. Acceptable if the UI shows **explicit states** (processing / ready) instead of pretending it's finished.
- **Cross-service state**: the policy shows as bound in one service but the billing service hasn't caught up; notifications arrive before or after the UI updates.
- **Multi-region**: writes in one region appear later in another.
Acceptable when the delay is short, the UI is honest about it, and no **decision** (money, legal commitment) is made on stale data. Not acceptable for balances, limits, uniqueness checks, permissions changes (a revoked user must lose access immediately), and anything regulatory.
Worked example, **rating engine**: quote creation is strongly consistent (same DB transaction, returned immediately); the **broker's quote list/dashboard** may lag a few seconds (served from a replica/aggregates), which is fine; publishing a **new rater version** propagates to all pods within ~1 minute (config/cache refresh), which is acceptable because versions are activated by **effective date**, not "instantly".

### 52. If this system is down for 1 hour, what is the business impact, and does your design match that impact?
Framework: quantify the impact, then check your RTO/RPO, redundancy and cost against it, both ways (under-engineered **and** over-engineered).
Impact dimensions: **revenue** lost or delayed (quotes not issued, brokers going to a competitor), **contractual SLAs** with clients (penalties), **regulatory** (inability to issue legally required documents, reporting obligations), **reputation/trust**, **operational cost** (staff idle, backlog to catch up afterwards), and **knock-on effects** (downstream systems, partners).
Then match: if 1 hour down costs, say, £50k + broker trust, then spending on zone redundancy, a warm standby and practiced failover (RTO < 1h) is justified, while active-active multi-region (much more cost and complexity, for a gain from ~1h to ~minutes) probably isn't. Conversely, an internal reporting tool down for an hour costs little, so single-zone and backups are enough. Say explicitly: "**my design has RTO X / RPO Y, the business needs Z, so it matches / here's the gap**."
Worked example, **rating engine**: 1 hour down at 9–11am on a weekday = brokers can't quote, so lost submissions to competing insurers (who are a click away on a broker platform) and SLA breaches with distribution partners; at 3am Sunday it's negligible. Design: zone-redundant and warm standby with 1h RTO fits; queued bind requests mean no data loss for submissions made just before the outage.

### 53. What part of your own design are you least confident about?
This is a **judgement and honesty** question. Bad answers: "nothing" or something trivial. Good answer: pick the **genuinely riskiest assumption**, explain *why* you're unsure, and say **how you'd de-risk it** (prototype, load test, spike, data analysis, ask an expert).
Common honest candidates: a capacity estimate you couldn't verify (e.g. "I assumed 80% cache hit ratio; if it's 40%, the DB tier is undersized"); a component you've never run at this scale; the consistency/ordering behaviour under failure; the cost model; a third-party dependency's real limits; the ML/LLM accuracy assumption.
Worked example, **rating engine**: "I'm least confident about **exact numerical parity with Excel for the long tail of functions and edge cases**: dynamic arrays, iterative calculations, `YEARFRAC`-style date functions. The architecture is fine; the risk is correctness on unusual workbooks. I'd de-risk it with a differential-testing harness on the full corpus of real workbooks before committing to a launch date, and by having a fallback: unsupported workbooks fail the build loudly instead of generating something subtly wrong."

### 54. What did you deliberately leave out, and when would you add it?
Shows you **scoped consciously** (v1 vs later) and know the **triggers** that justify adding complexity. Structure: "I left out X because Y; I'd add it when metric/event Z happens."
Typical examples:
- **Multi-region**: added when an enterprise client contractually requires it, or the business impact of a regional outage (Q52) exceeds its cost.
- **Sharding / partitioning**: when the largest table approaches the limits of one primary (e.g. write CPU > 60% sustained, or the table passes N hundred million rows and vacuum/indexes struggle).
- **Event streaming (Kafka)**: when several consumers need the same events or replay becomes a requirement; until then a queue/outbox is enough.
- **Caching layer**: when p99 latency or DB load shows a need; caches add invalidation bugs.
- **Microservice split**: when team size or scaling profiles diverge (Round 3 Q81).
- **Self-service UIs / A/B testing / advanced analytics**: when manual operation becomes a bottleneck or the business asks for it.
- **Fine-grained permissions, SSO for each customer IdP, data residency per region**: when sales requires it.
Worked example, **rating engine**: left out A/B testing of rules (Q22), self-service workbook upload UI, multi-region active-active, and the explanation-trace UI for actuaries; would add A/B testing when the pricing team wants to run experiments, the upload UI when rater updates exceed ~1/week per product, and the trace UI as soon as there's a regulatory audit request.
