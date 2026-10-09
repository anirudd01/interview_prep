# Round 6 — Gap Fill & Staff Readiness: Answers, Section I (Performance, Capacity & Estimation Drills)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept.

These are drills: practise saying the arithmetic out loud, step by step, with units, and state your assumptions before you compute. Interviewers grade the reasoning and the sanity checks more than the final number. Where a question asks about your own experience there is a **Your story:** note to fill in from what you actually did.

---

## I. PERFORMANCE, CAPACITY & ESTIMATION DRILLS

### 75. State Little's Law and use it: a service handles 500 RPS at 200ms average latency. How many requests are in flight? How many uvicorn workers or threads do you need?
**Little's Law:** in any stable system, `L = λ × W`. L is the average number of items in the system, λ the average arrival (= throughput) rate, W the average time each item spends in the system. It holds regardless of the arrival distribution or scheduling, as long as the system is stable (arrivals are not outrunning completions) and you measure over a long enough window.

**The number:** `L = 500 req/s × 0.2 s = 100 requests in flight`, on average.

That 100 is the concurrency your fleet must hold at once. How you turn it into workers depends entirely on what those 200ms are spent doing.

**Case 1: sync workers (gunicorn sync, or a thread per request).** Each slot holds exactly one request for its whole lifetime, waiting included. So you need at least 100 slots. Little's Law gives the average, but arrivals are bursty, so add headroom: at a 70% target, `100 / 0.7 ≈ 143`, call it ~150 slots. As processes that is expensive (150 × ~100-150MB ≈ 15-22GB RAM), so you would use threads (e.g. gunicorn `gthread`, 4 workers × 32-40 threads) or move to async.

**Case 2: async (uvicorn workers, async DB/HTTP clients).** While a request awaits I/O, the event loop serves others, so one process can hold hundreds of in-flight I/O-bound requests. Concurrency is no longer the constraint, CPU is. Split the 200ms into CPU time and wait time. Say profiling shows 20ms of CPU per request and 180ms awaiting DB/HTTP:
- CPU demand = `500 req/s × 0.020 s = 10 cores` fully busy.
- At a 60-70% CPU target: `10 / 0.65 ≈ 15-16 cores`.
- Uvicorn runs one event loop per process, so that is ~16 worker processes, e.g. 4 pods × 4 workers (or 8 pods × 2, one worker per vCPU is the usual rule). Each loop is holding `100 / 16 ≈ 6` requests on average, trivially fine.

**Case 3: CPU-bound (e.g. a Cellular rater calculation that is 200ms of pure Python).** Then CPU demand is `500 × 0.2 = 100 cores`. Async buys nothing; you need ~100 cores' worth of processes plus headroom (~140-150), or you make the calculation cheaper, cache results, or move it to a worker pool behind a queue.

**Apply it downstream too.** If 150ms of the 200ms is Postgres time, the DB sees `500 × 0.15 = 75` concurrent queries on average. Your connection pools across all pods must cover that with headroom, and the DB must actually be able to run ~75 concurrent queries without degrading. Little's Law is how you size pools, semaphores and queue consumers, not just web workers.

**Interviewer push:** "What happens if latency doubles because the DB slows?" At the same 500 RPS, in-flight doubles to 200. Sync workers saturate, requests queue, latency rises further, a feedback loop. That is why you cap concurrency (bounded pools, load shedding) and set timeouts.

**Sanity check with your resume numbers.** Jio recommender, 100M requests/day: `100,000,000 / 86,400 s ≈ 1,157 RPS` average. Consumer traffic has a peak-to-average of roughly 3-5x, so peak ≈ 3,500-6,000 RPS. If p50 latency was ~50ms, in-flight at peak is `5,000 × 0.05 = 250`. Jio ATS, 100k resumes/day: `100,000 / 86,400 ≈ 1.16/s` average, but if it arrived during an 8-hour business day it is `100,000 / 28,800 ≈ 3.5/s`; at ~5s per parse that is `3.5 × 5 ≈ 17` concurrent Celery tasks. Be ready to quote numbers like these when someone asks you to defend the claims.

**Your story:** how many uvicorn/gunicorn workers per pod did Aurora/Pulse or the ATS run, and how was that chosen? If it was a default you never revisited, say so and walk through how you would size it now.

### 76. Estimation drill: storage and monthly growth for 10 years of policy documents. 2M policies, 3 documents each at issue (avg 400KB), plus 2 endorsement documents per policy per year. Then: cost in hot vs cool vs archive storage.
**State assumptions first.** Decimal units (1 TB = 1,000 GB = 10^12 bytes). The book stays at 2M policies (base case), endorsements start in year 1. PDFs are already compressed, so no compression gain. Prices are per logical GB; redundancy (LRS/ZRS/GRS) changes the price, not the GB count.

**At issue:**
- Docs: `2M × 3 = 6M documents`
- Bytes: `6M × 400KB = 2,400,000,000 KB = 2.4 × 10^12 B = 2.4 TB`

**Endorsements per year:**
- Docs: `2M × 2 = 4M documents/year`
- Bytes: `4M × 400KB = 1.6 TB/year`
- Monthly growth: `1.6 TB / 12 ≈ 133 GB/month` (~333k new blobs/month)

**10-year total (base case):** `2.4 + 10 × 1.6 = 2.4 + 16 = 18.4 TB`, and `6M + 40M = 46M blobs`.

**Scenarios to call out, because the base case is optimistic:**
- **Annual renewals reissue the 3-document pack.** Each year adds `2.4 TB` renewal docs plus `1.6 TB` endorsements = `4.0 TB/year` (≈333 GB/month). 10 years: `2.4 + 10 × 4.0 = 42.4 TB`, ~106M blobs. This is closer to how a real insurer behaves.
- **Book growth of 10%/year (base case behaviour otherwise).** Endorsement volume grows with the book: `1.6 TB × (1.1^0 + ... + 1.1^9) = 1.6 × 15.94 ≈ 25.5 TB`. New policies: book goes from 2M to `2M × 1.1^10 ≈ 5.19M`, so 3.19M new × 1.2MB ≈ 3.8 TB. Total ≈ `2.4 + 3.8 + 25.5 ≈ 31.7 TB`.
- **Hidden multipliers:** blob versioning and soft delete keep old copies, regenerated documents (a template fix that re-renders everything) can double the footprint, and a backup copy in another account doubles it again. Mention them; don't silently ignore them.

**Pricing.** Approximate Azure Blob pay-as-you-go, LRS, a major region, first-50TB tier, late 2026. Check the pricing calculator before quoting real numbers; they vary by region and redundancy (ZRS/GRS cost more).

| Tier | ~$/GB-month | Online? | Min. retention (early deletion) |
|---|---|---|---|
| Hot | ~0.018-0.021 (use 0.02) | Yes, ms latency | none |
| Cool | ~0.010 | Yes | 30 days |
| Cold | ~0.0036-0.0045 (use 0.0045) | Yes | 90 days |
| Archive | ~0.001-0.002 (use 0.002) | No, offline | 180 days |

**Monthly bill at the 10-year size (base case, 18.4 TB = 18,400 GB):**
- Hot: `18,400 × 0.02 = $368/month`
- Cool: `18,400 × 0.01 = $184/month`
- Cold: `18,400 × 0.0045 ≈ $83/month`
- Archive: `18,400 × 0.002 ≈ $37/month`

Year 1 for comparison (2.4 + 1.6 = 4.0 TB): Hot ≈ $80/month.

**Cumulative 10-year storage spend.** Size grows roughly linearly from 2.4 TB to 18.4 TB, so the average is about `(2.4 + 18.4) / 2 ≈ 10.4 TB`. `10.4 TB × 120 months ≈ 1,250 TB-months = 1.25M GB-months`.
- All Hot: `1.25M × 0.02 ≈ $25k` over 10 years
- All Cool: `≈ $12.5k`
- All Archive: `≈ $2.5k`
For the renewal scenario (42.4 TB end state, average ≈ 22.4 TB) multiply by roughly 2.2: about $54k all-hot.

**The staff-level point: storage is not the expensive part.** Even the worst case is tens of thousands of dollars over a decade. The real costs and risks are elsewhere:
- **Access pattern.** Brokers and underwriters read recent policies, claims handlers read old ones occasionally, auditors read rarely. Archive is offline: a read needs rehydration, which takes up to ~15 hours at standard priority (high priority is typically under an hour for small blobs and costs much more). A broker clicking "download policy schedule" cannot wait 15 hours, so archive only suits documents you are sure nobody needs on demand. Cold tier is online with normal latency at a few times the archive price, which is often the better choice for "rarely but unpredictably read."
- **Transaction and retrieval costs.** Cooler tiers charge more per write/read operation and per GB retrieved. Archive retrieval (rehydration) is charged per GB plus per operation. With 46-106M blobs, per-10k-operation pricing adds up: tier changes done by lifecycle policies are billed as operations on every blob. Setting the tier at upload time avoids paying for a later move.
- **Early deletion.** Moving a blob out of Cool before 30 days, Cold before 90, or Archive before 180 is charged as if it stayed the full period. Don't archive something you might delete or re-tier soon.
- **Compliance.** Insurance documents usually have regulatory retention (often years after policy expiry). Use immutable (WORM) time-based retention policies and legal holds on the container, and define deletion at end of retention, otherwise you store forever.

**Recommended design:** write new documents to Hot (or Cool directly if they are rarely reread after issue), lifecycle policy moves them to Cool after ~90 days without access, Cold after ~1-2 years, and Archive only for closed/expired policies past any realistic retrieval need. Keep metadata (policy ID, doc type, tier, blob path) in Postgres/Cosmos so you can search without listing blobs, and so the UI can tell a user "this document is archived, it will be ready in a few hours" instead of failing.

**Your story:** Aurora/Pulse generates policy documents into Azure Blob. Do you know the real volume and which tier and lifecycle rules were set? If you don't, say "I'd pull the container metrics" rather than guessing.

### 77. Latency numbers every engineer should know: L1/L2 cache, RAM, SSD read, same-zone network round trip, cross-region round trip. Rough orders of magnitude, and why they matter in design.
Know the orders of magnitude, not exact values. These are modern hardware / cloud figures, rounded.

| Operation | Rough latency | Relative to L1 |
|---|---|---|
| L1 cache reference | ~1 ns | 1x |
| Branch mispredict | ~3-5 ns | |
| L2 cache reference | ~4 ns | 4x |
| L3 cache reference | ~10-40 ns | |
| Uncontended mutex lock/unlock | ~20 ns | |
| Main memory (RAM) reference | ~100 ns | 100x |
| A single CPython function call | ~50-100 ns | |
| Compress 1KB with zstd/snappy | ~1-2 µs | |
| Read 1MB sequentially from RAM | ~10-50 µs | |
| Local NVMe SSD random 4KB read | ~20-100 µs | |
| Read 1MB sequentially from NVMe | ~150-300 µs | |
| Same-zone network round trip (cloud VMs) | ~0.1-0.5 ms | ~100,000x+ |
| Cross-zone, same region | ~0.5-2 ms | |
| Cloud network-attached disk read (Azure Premium SSD) | ~1-2 ms (Ultra/Premium v2 sub-ms) | |
| Redis GET / simple indexed Postgres query in-region | ~0.3-2 ms | |
| HDD seek | ~5-10 ms | |
| Cross-region same continent (UK South to West Europe) | ~10-20 ms | |
| Transatlantic round trip | ~70-90 ms | |
| India to UK / US round trip | ~120-250 ms | |
| TLS 1.3 handshake on a new connection | +1 RTT (1.2 needed 2) | |
| LLM API call | ~0.3 s to tens of seconds | |

**Why they matter in design:**
- **Network dominates in-process work.** One same-region DB round trip (~1ms) costs as much as roughly ten thousand RAM references. An N+1 query pattern with 100 rows is 100 round trips, ~100ms, before any query cost. Batch, join, or prefetch.
- **Chatty microservices.** A request that fans out to 6 services sequentially at ~2ms each plus serialization is 15-20ms of pure overhead. Parallelise calls, colocate in the same zone, or merge services that always talk to each other.
- **Caching tiers follow the table.** In-process cache (ns-µs) vs Redis (sub-ms to ms, one network hop) vs DB (ms). A Redis cache in front of a 1ms query buys little; in front of a 50ms query it buys a lot.
- **Cross-region physics.** You can't make synchronous replication or a consensus write across regions faster than the RTT. That's why multi-region writes are async (eventual consistency) or pay ~tens of ms per write. It also matters for you personally: a developer in Bengaluru hitting a UK South API sees ~150ms+ per round trip, so chatty UIs feel slow there even when the server is fast.
- **Connection reuse.** A fresh TCP + TLS connection costs extra round trips; cross-region that is hundreds of ms. Keep-alive and connection pools (httpx client reuse, pgbouncer) matter.
- **Disk is not "free fast storage" in the cloud.** Managed disks are network-attached; random I/O at 1-2ms per op caps a single-threaded Postgres workload. Know your IOPS and throughput limits per disk SKU.

### 78. Amdahl's Law and the Universal Scalability Law: why doesn't adding replicas scale throughput linearly?
**Amdahl's Law** (speedup of a fixed workload): if a fraction `p` of the work parallelises and `1 - p` is serial,
`S(N) = 1 / ((1 - p) + p / N)`, with a ceiling of `1 / (1 - p)` as N goes to infinity.
Example, p = 0.95: ceiling = `1 / 0.05 = 20x`. With 16 workers: `1 / (0.05 + 0.95/16) = 1 / (0.05 + 0.059) = 1 / 0.109 ≈ 9.1x`. Half of the 16 machines are effectively wasted on the 5% serial part.

**Universal Scalability Law** (Neil Gunther) adds the cost of coordination, which Amdahl ignores:
`X(N) = N / (1 + σ(N - 1) + κN(N - 1))` (relative to one node)
- `σ` = **contention**: waiting for a shared resource (a DB primary, a lock, a single queue partition, a rate-limited API). This alone is Amdahl-like: throughput flattens.
- `κ` = **coherency/crosstalk**: nodes must keep each other consistent (cache invalidation, distributed locks, gossip, cross-node chatter). This term grows with N², so throughput eventually goes *down* as you add nodes.
- Peak is at `N* = sqrt((1 - σ) / κ)`.

Worked example, σ = 0.05, κ = 0.001:
- N = 10: `10 / (1 + 0.45 + 0.09) = 10 / 1.54 ≈ 6.5x`
- N* = `sqrt(0.95 / 0.001) = sqrt(950) ≈ 31`: `31 / (1 + 1.5 + 0.93) = 31 / 3.43 ≈ 9.0x`
- N = 60: `60 / (1 + 2.95 + 3.54) = 60 / 7.49 ≈ 8.0x`. Twice the replicas, less throughput.

**Why replicas don't scale linearly in a real web service:**
- Stateless app pods scale well until they hit a **shared bottleneck**: one Postgres primary, its connection limit (100 pods × 20-connection pools = 2,000 connections), a single Redis instance, a hot Kafka partition, a third-party API quota.
- **Coordination:** distributed locks (Redis lock for task claim, like your RLHF dashboard), cache invalidation fan-out, leader election, consensus writes.
- **Load imbalance:** hot keys / hot tenants mean one shard is saturated while others idle.
- Each new replica also adds warm-up, cold caches, and more connections to the shared tier.

**What you do about it:** measure throughput at N = 1, 2, 4, 8 and fit σ and κ, which tells you where the ceiling is before production finds it. Then reduce σ (partition/shard, read replicas, pgbouncer, queue instead of lock, batch writes) and reduce κ (avoid cross-node chatter, make nodes share-nothing, accept eventual consistency, local caches with TTL instead of invalidation broadcasts).

### 79. How do you design a load test that reflects production? Open vs closed workload models, coordinated omission, ramp-up, realistic data and think time.
**Start from a question and an SLO.** "Can Pulse handle 3x the January renewal peak with p99 < 800ms and error rate < 0.1%?" A load test without pass/fail criteria is a demo.

**Open vs closed workload models:**
- **Closed model:** a fixed number of virtual users, each sends a request, waits for the response, thinks, repeats. Throughput is bounded by `users / (response time + think time)`. When the system slows down, the generator automatically sends less, so it hides overload. Locust users with `wait_time`, JMeter thread groups and k6 VU-based executors are closed.
- **Open model:** requests arrive at a target rate regardless of how fast the system responds, like real internet traffic from many independent clients. When the system slows, queues build and latency explodes, which is exactly what happens in production. k6 `constant-arrival-rate`/`ramping-arrival-rate` executors and wrk2 are open. Locust's `constant_throughput` wait time approximates it per user, but total rate is still capped by user count, so give it plenty of users.
- Rule of thumb: public APIs and webhooks behave open; a fixed pool of internal users (underwriters on a desktop app) or a batch client with N workers behaves closed. Model what you actually have.

**Coordinated omission (Gil Tene).** In a closed loop, if the server stalls for 2 seconds, the generator also stalls and doesn't send the requests it would have sent. Those would have been the slowest requests, so they never get measured, and your p99 looks great while real users suffered. Fixes: use an open-model tool, measure latency from the *intended* send time rather than the actual send time (wrk2, k6 arrival-rate executors), and use HdrHistogram-style recording. Also watch the generator itself: if the load generator's CPU is pegged, your latencies are fiction. Run distributed workers.

**Test shapes:** smoke (tiny load, does the script work), ramp/load (step up to expected peak, hold 15-30 min), stress (keep stepping until something breaks, find the knee), spike (jump to 5x in seconds, tests autoscaling and cold starts), soak (expected load for hours, finds leaks, pool exhaustion, log disk filling). Ramp up gradually so autoscalers and caches react as they would, and exclude the warm-up window from results.

**Realistic data and behaviour:**
- **Traffic mix** from production logs/App Insights: endpoint proportions (e.g. 70% quote reads, 20% rater calculations, 10% policy issue), not one endpoint hammered.
- **Data distribution:** don't reuse one policy ID (100% cache hit, unrealistic). Sample IDs from a realistic distribution, including the long tail and the hot tenants. Payload sizes should match production (a 40-sheet rater workbook vs a 2-sheet one).
- **Database volume:** run against a prod-sized dataset. Queries that are fast on 10k rows fall over on 10M.
- **Think time:** randomised (exponential or measured from session data), not a fixed 1s, or you get synchronised waves.
- **Environment:** same SKUs, pod limits, autoscaling settings and network path (APIM, ingress, private endpoints) as production. Decide whether downstream dependencies are real or stubbed, and say which in the report.

```python
# locustfile.py - weighted, realistic-ish mix
import random
from locust import HttpUser, task, between

POLICY_IDS = [line.strip() for line in open("sampled_policy_ids.txt")]

class Broker(HttpUser):
    wait_time = between(1, 5)  # closed model with randomised think time

    @task(7)
    def get_quote(self):
        pid = random.choice(POLICY_IDS)
        self.client.get(f"/quotes/{pid}", name="/quotes/[id]")

    @task(2)
    def rate(self):
        self.client.post("/rater/calculate", json={"product": "property", "tiv": random.randint(100_000, 50_000_000)})

    @task(1)
    def issue_policy(self):
        self.client.post("/policies", json={"quote_id": random.choice(POLICY_IDS)})
```
```bash
locust -f locustfile.py --headless -u 500 -r 20 -t 30m --host https://pulse-staging.example.com --csv results
```
Azure Load Testing can run JMeter or Locust scripts at scale and compare runs, with server-side metrics from Azure Monitor alongside, which is handy for regression baselines.

**Your story:** locust is on your resume. What did you load test, what model was it (almost certainly closed), and what did you find? If the honest answer is "we ran it once before launch", say that and explain how you'd make it a repeatable gate.

### 80. Queueing intuition: why does latency explode as utilisation approaches 100%? What utilisation do you target for a latency-sensitive service, and why?
**Intuition:** arrivals are random. Even if average arrival rate is below capacity, bursts arrive faster than you can serve them, and a queue forms. The idle time you "wasted" at low utilisation is exactly what absorbs those bursts. As utilisation ρ approaches 1, there is almost no idle time left to drain a queue once it forms, so queues get long and stay long.

**M/M/1 model** (random arrivals, random service times, one server). With service time S and utilisation ρ = λ × S:
- Mean response time `W = S / (1 - ρ)`
- Mean number waiting `Lq = ρ² / (1 - ρ)`

With S = 10ms:

| Utilisation ρ | 1 / (1 - ρ) | Mean latency W | Queue length Lq |
|---|---|---|---|
| 50% | 2x | 20 ms | 0.5 |
| 70% | 3.3x | 33 ms | 1.6 |
| 80% | 5x | 50 ms | 3.2 |
| 90% | 10x | 100 ms | 8.1 |
| 95% | 20x | 200 ms | 18 |
| 99% | 100x | 1,000 ms | 98 |

Going from 50% to 90% utilisation (1.8x more load) makes latency 5x worse. Going from 90% to 99% (10% more load) makes it 10x worse again. The curve is a hockey stick, not a line.

**Tails are worse than the mean.** In M/M/1 the response time is exponentially distributed, so `p99 = ln(100) × mean ≈ 4.6 × mean`. At 90% utilisation that is `4.6 × 100ms = 460ms` p99 for a 10ms service.

**Variability matters as much as utilisation.** Kingman's approximation for a single queue: `Wq ≈ (ρ / (1 - ρ)) × ((Ca² + Cs²) / 2) × S`, where Ca and Cs are the coefficients of variation of inter-arrival and service times. Bursty traffic or a mix of 5ms and 2s requests on the same pool (Cs high) makes queues far worse at the same utilisation. That's an argument for separating slow endpoints (a heavy rater calculation, PDF generation) onto their own pool or queue.

**Many servers help.** With c servers sharing one queue (M/M/c), you can run hotter for the same latency because a burst is spread across servers. A single-threaded resource (one event loop, one DB primary lock, one Kafka partition consumer) is the M/M/1 worst case.

**What to target:**
- Latency-sensitive online service: roughly **50-70% CPU** at peak per pod, measured at the bottleneck resource (CPU, DB connections, worker slots), not just "CPU".
- **Account for failure headroom.** With 3 availability zones, losing one leaves 2/3 of capacity. If you never want to exceed ~80% after a zone loss, normal peak must be at most `80% × 2/3 ≈ 53%`.
- Batch/async workers (Celery, ATS resume parsing) can run at 85-90%, because nobody waits on individual job latency, only on throughput and queue drain time.
- Pair the target with **load shedding and bounded queues** so that if you do hit 100%, you fail fast (429/503) instead of building an unbounded queue where every request times out.

### 81. Capacity planning for next year: what data do you collect, how do you forecast, and how much headroom do you keep?
**Data to collect:**
- **Business drivers:** policies in force, new business and renewal forecasts, number of brokers/users, new products or markets launching, migrations onto the platform. Get these from the business plan, not from guessing. For an insurer, renewal peaks (big renewal dates) matter more than average growth.
- **Demand metrics:** RPS per endpoint, peak-to-average ratio, seasonality by hour/day/month, background job volumes, storage growth per month (see Q76), egress.
- **Unit costs:** requests per business event (one quote = N rater calls + M DB queries), CPU-seconds and memory per request, DB IOPS per quote. This is the bridge from "20% more policies" to "X more cores."
- **Supply metrics:** max sustainable throughput per pod at SLO, measured by load test (Q79), not assumed. Saturation of every shared resource: DB CPU/IOPS/connections, Redis memory, Service Bus/Kafka throughput units/partitions, Azure subscription quotas (vCPU per region, private endpoints, IPs per subnet for AKS).
- **Cost** per environment and per unit (cost per quote, per policy), so the plan comes with a budget.

**Forecasting:**
- **Driver-based model** as the primary: `next year's peak RPS = business volume forecast × requests per business event × peak factor`. Easy to explain to finance and product.
- **Time-series trend** (linear/ETS/Prophet on the last 12-24 months) as a cross-check. If they disagree, find out why.
- **Scenarios:** expected, high (big new client onboarding), and a stress case. Plan to expected, have a lever ready for high.

**Worked example** (using the recommender's 100M/day as the base):
- Average `100M / 86,400 ≈ 1,157 RPS`. Peak factor 4x → `≈ 4,600 RPS`.
- Forecast growth 30% → `4,600 × 1.3 ≈ 6,000 RPS` peak next year.
- Load test shows one pod sustains 300 RPS at SLO while at 60% CPU → `6,000 / 300 = 20 pods` needed at peak.
- Survive a zone loss across 3 zones: the remaining 2 zones must hold 20 pods → `20 / (2/3) = 30 pods` total at peak.
- Then check the shared tiers: 30 pods × 10 DB connections = 300 connections, does the DB (or pgbouncer) handle that? Does the node pool fit inside the regional vCPU quota?

**Headroom:**
- Utilisation headroom for latency (Q80): run at ~50-70% at peak.
- Failure headroom: N+1 or zone-loss capacity, whichever is larger.
- Forecast error: +20-30% on top, or more for a new product.
- **Lead-time headroom:** anything slow to get must be planned early: quota increases, reserved capacity, DB tier changes (a Postgres Flexible Server scale-up needs a restart), subnet/IP exhaustion that forces a network redesign.
- Cost strategy: reservations or savings plans for the steady baseline, autoscaling (HPA, cluster autoscaler, KEDA for queue-driven workers) for the peaks.

Review it quarterly against actuals. The staff-level part is making the plan a shared artefact with product and finance, owning the assumptions, and naming the one or two resources that will hit their limit first.

**Your story:** have you done this formally anywhere (Jio scaling, Aurora/Pulse growth)? If it was "we watched Grafana and scaled when CPU was high", that is reactive scaling, be honest about it and present the process above as what you'd introduce.

### 82. A performance regression appeared somewhere in the last 50 commits. How do you find it? (git bisect, benchmark suites in CI, continuous profiling.)
**1. Confirm and quantify first.** Which metric (p99 of one endpoint, CPU per request, memory), how much worse, since when. Line it up with the deploy timeline. Rule out non-code causes: traffic mix change, data growth (a table crossing a size where the planner switches plan), a dependency upgrade in the lockfile, config/infra change (node SKU, pod limits causing CPU throttling), a noisy neighbour.

**2. Build a reliable, automatable reproduction.** A benchmark that runs in a minute or two and shows a clear difference between good and bad. Make it low-noise: pin CPU/frequency where possible, warm up, run several iterations and compare the median (`pyperf` handles this), use a threshold well above run-to-run noise.

**3. Bisect.** 50 commits need `ceil(log2(50)) = 6` steps. Automate it with `git bisect run`:
```bash
git bisect start
git bisect bad HEAD
git bisect good v2.14.0          # last known-good release
git bisect run ./scripts/perf_check.sh
git bisect log                   # save the trail
git bisect reset
```
```bash
#!/usr/bin/env bash
# scripts/perf_check.sh: exit 0 = good, 1 = bad, 125 = skip (can't test this commit)
pip install -q -e . || exit 125
ms=$(python bench/rate_quote.py --iterations 50 --print-median-ms) || exit 125
python -c "import sys; sys.exit(0 if float('$ms') < 120 else 1)"
```
Exit code 125 tells bisect to skip commits that don't build. If the regression is the combined effect of several commits, bisect finds the first one to cross the threshold; then look at the neighbours too.

**4. Explain it, don't just find it.** Profile the bad commit vs its parent: py-spy flame graphs side by side, or a differential flame graph. Typical culprits: an added N+1 query, a lost index or changed ORM query, synchronous I/O inside an async path, a removed cache, debug logging serializing big objects, a pydantic model now validating a huge nested payload.

**5. Prevent the next one:**
- **Benchmark suite in CI** on the hot paths (e.g. rater calculation, quote serialization) with `pytest-benchmark`, `pyperf`/asv, or a hosted tool like CodSpeed. Compare against the main-branch baseline and fail or flag the PR on a regression beyond a threshold. Run on dedicated or consistent runners; shared CI runners are noisy, so use relative comparison and thresholds of ~5-10%.
- **Query-count assertions** in tests (assert an endpoint issues at most N SQL queries), which catch N+1 regressions deterministically.
- **Continuous profiling in production** (Grafana Pyroscope, Datadog, or similar, with low-overhead sampling): you can diff profiles by deploy version and often skip bisecting entirely because the new hot frame is obvious.
- **Per-version SLO dashboards** and canary releases: compare p99 of the canary against the baseline before full rollout, and roll back automatically on regression.

**Your story:** have you ever bisected a regression or caught one in a canary? If not, pick a real slowdown you fixed in Aurora/Pulse or GeoStorm and explain how this process would have found it faster.
