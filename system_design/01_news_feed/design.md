# 01 · News feed / recommendation serving at 100M requests/day

Source: R4 Q11–12 · Anchor: Jio News recommendation engine · Plan: W14 Design 3

---

## 1. Your attempt (do this before reading further)

> "Design the backend that serves a personalized news feed for a news app: 100 million feed requests a day. Each request returns a ranked list of articles for that user. Walk me through it."

Clarifying questions a strong candidate asks first:

- How many users, and how many are logged in vs anonymous? (This drives cold start and feature storage.)
- What latency target, and is it measured at the server or the device? How fresh must it be: how soon after publishing must breaking news show up?
- Does the ML team own the model, or do I? Is this serving only, or training too?
- What's the traffic shape? Is it flat, or are there spikes from push notifications and big events?

Give yourself 45 minutes. Then come back.

---

## 2. Requirements

**Functional**
- `GET` a feed: about 20 ranked articles per page, personalized by reading history, language and region; infinite scroll.
- New articles enter feeds quickly: within about 5 minutes normally and under 1 minute for breaking news.
- Don't repeat articles the user has already seen; avoid near-duplicate stories (5 outlets, same event).
- Log impressions and clicks; that's the training data and the A/B test signal.
- Cold start: brand-new users (no history) and brand-new articles (no clicks yet).
- Ranking changes are A/B tested; the model can be redeployed and rolled back (R4 Q12).

**Non-functional**
- Load: 100M requests/day; **peak 33k RPS** (design for ~40k with headroom).
- Latency: **p50 100 ms, p95 200 ms** server-side.
- Errors: **under 0.5%**, and a failed personalization should *degrade* to a generic feed, not return an error.
- Availability: 99.9% for the feed endpoint. A stale feed beats no feed.
- Consistency: eventual everywhere. Nobody is harmed if a click takes 30 s to influence the next feed.

---

## 3. Estimation

| Quantity | Arithmetic | Result |
| --- | --- | --- |
| Average RPS | 100M ÷ 86,400 | ≈ 1.2k RPS |
| Peak / average | 33k ÷ 1.16k | **≈ 28×**. That's abnormal (2–3× is typical), so the spikes need a cause: push notifications |
| In flight at peak | 33k × 0.2 s (Little's law) | ≈ 6.6k concurrent requests |
| Response bandwidth | 33k × ~5 KB | ≈ 165 MB/s ≈ 1.3 Gbps at peak |
| Users (assumed) | ~30M DAU × ~3–4 feed loads | consistent with 100M/day |
| Active article corpus | ~50k new/day × 7-day window | ≈ 350–500k articles |
| Article embeddings | 500k × 256 dims × 4 B | ≈ 0.5 GB. **Fits in RAM on every ANN replica** |
| User features | ~100M users × ~1 KB | ≈ 100 GB. Too big for one box: a Redis cluster / online feature store |
| Impression events | 100M × 20 items | 2B/day ≈ 23k events/s avg, ~600k/s at a push peak if not batched → **batch on the client** |

The two numbers that shape the design: **28× spikes** (so autoscaling alone is too slow, and you need pre-scaling plus load shedding) and **0.5 GB of embeddings** (so retrieval can be in-memory and fast).

---

## 4. API

```
GET  /v1/feed?cursor=<opaque>&limit=20          → {items:[{article_id, title, image, source, reason}], next_cursor}
POST /v1/events   (batched, gzip)               → 202   body: [{type: impression|click|dwell, article_id, feed_request_id, ts}]
POST /internal/articles   (from ingestion)      → 201   (publisher/CMS → pipeline)
```

- `cursor` encodes `{feed_request_id, offset}`. Page 2 re-uses the **same ranked list**, which is cached for ~10 min, so scrolling never reshuffles or duplicates.
- `feed_request_id` joins impressions and clicks back to the exact ranking that produced them. Without it you can't train or A/B test properly.
- Events are batched every ~30 s or 50 events on the device, and `202` means "accepted, async".

---

## 5. Data model

| Store | Holds | Key / access pattern | Why this store |
| --- | --- | --- | --- |
| Article store (Postgres or MongoDB) | metadata: title, source, language, category, publish time, embedding version | by `article_id`; batch reads of 20–50 | small, relational enough; ~500k hot rows, cache in front |
| ANN index (in-memory: FAISS / ScaNN, or a managed vector search) | article embeddings for the active window | top-k nearest to a user vector | 0.5 GB fits in RAM; rebuilt or incrementally updated as articles arrive |
| Online feature store (Redis cluster) | user vector, recent categories, recent clicks, article CTR counters | `MGET` by user id + candidate ids, < 10 ms | sub-ms reads at 40k RPS × ~500 keys needs memory |
| Seen set (Redis) | article ids shown to the user in the last ~3 days | per-user set or Bloom filter, TTL | a Bloom filter is ~1–2 KB/user and fine with rare false "seen" |
| Trending (Redis sorted sets) | click velocity per region/language/category | `ZREVRANGE` top-N, decayed scores | cheap, real-time, also the fallback feed |
| Event log (Pub/Sub or Kafka → data lake: BigQuery / GCS) | every impression, click, dwell | append-only, partitioned by day | training data, A/B analysis, replay |
| Model registry | ranker versions + metadata | by version | deploy, shadow, rollback |

---

## 6. Components

Each block: **what** · **why** · **without it** · **scaling knob**.

**Mobile client.** Renders the feed, batches events, keeps the last feed for offline. *Why:* client batching turns 2B events/day into a manageable stream. *Without it:* one HTTP call per impression melts the event collector at a push spike. *Knob:* batch size and flush interval.

**CDN / edge.** Serves images and the *non-personalized* trending feed per region and language. *Why:* the cold-start and fallback feed is identical for millions of users, so it's perfectly cacheable. *Without it:* every anonymous user hits the feed service. *Knob:* TTL (30–60 s for trending).

**API gateway / load balancer.** TLS, auth, per-user rate limits, routing to the feed service. *Why:* one choke point for auth and abuse. *Without it:* every service re-implements auth. *Knob:* replicas; rate-limit thresholds.

**Feed service (FastAPI on GKE).** The orchestrator: fan out to candidate sources in parallel, filter, call the ranker, re-rank, cache the ranked list, respond. Holds the **latency budget** and degrades gracefully. *Why:* one place owns the deadline and the fallbacks. *Without it:* the client would orchestrate, and every failure becomes user-visible. *Knob:* pods (stateless; async I/O, so ~1–2k RPS per pod is realistic) plus scheduled pre-scaling before pushes.

**Candidate generators** (run in parallel, each with its own timeout):
- **Personal (ANN):** user vector → top ~300 nearest articles. *Why:* this is the personalization. *Without it:* everyone gets trending.
- **Trending:** top ~100 by click velocity for the region and language. *Why:* freshness and cold start. *Without it:* new users see nothing relevant.
- **Followed topics / sources:** ~100 from categories the user follows.
- **Fresh / breaking:** the last N minutes of articles, ~50. *Why:* new articles have no clicks yet, so ANN on history finds them late.
*Knob:* k per source, timeout per source; drop a slow source rather than wait for it.

**Filter.** Removes seen articles, wrong language, blocked sources, and near-duplicates (cluster id from ingestion). *Why:* repeats are the #1 complaint in feeds. *Without it:* the same story five times. *Knob:* seen-set TTL.

**Online feature store (Redis).** User and article features fetched in one batched `MGET` for ~500 candidates. *Why:* ranking needs fresh features (what you clicked 2 minutes ago). *Without it:* ranking on stale features from the last batch job. *Knob:* cluster shards; pipeline/batch size.

**Ranker (model server).** Scores ~500 candidates per request with a light model (gradient-boosted trees or a small two-tower/MLP), batched. *Why:* candidate generation is about recall; ranking is about precision. *Without it:* you rank by a single heuristic. *Knob:* replicas, batch size, model size. CPU inference in Python must avoid the GIL: use ONNX / a C-backed runtime or process workers.

**Re-ranker / business rules.** Diversity (max 3 per category in the top 10), freshness boost, sponsored slots, editorial pins. *Why:* the model optimizes clicks, and the product needs variety. *Without it:* a clickbait monoculture. *Knob:* rule weights (A/B tested).

**Experiment service.** Assigns users to buckets by `hash(user_id) % 100`, which picks the ranker version and the rule weights. *Why:* every ranking change ships behind an experiment. *Without it:* you can't prove a model is better. *Knob:* traffic split.

**Article ingestion pipeline.** Publisher/CMS → validate → dedupe/cluster near-duplicates → classify (language, category) → **embed** → write to the article store, add to the ANN index, seed the fresh source. *Why:* an article must be embedded before it can be recommended. *Without it:* there's no corpus. *Knob:* workers; embedding batch size. Target end to end < 60 s for breaking news.

**Event collector → Pub/Sub / Kafka.** Accepts batched events and publishes them to topics (impressions, clicks). *Why:* it decouples the request path from analytics. *Without it:* writes to the warehouse sit on the request path. *Knob:* partitions; the collector is stateless.

**Stream processor.** Consumes events and updates trending counters (decayed), seen sets, user recent-interest features and article CTR in Redis within seconds. *Why:* it closes the loop quickly (you clicked on cricket, so your next feed has more cricket). *Without it:* features update only daily. *Knob:* consumer parallelism; **alert on consumer lag**.

**Data lake + offline training.** Events land in BigQuery/GCS; daily jobs train the ranker and recompute user embeddings, and a batch job rebuilds the ANN index. *Why:* heavy learning belongs offline. *Knob:* job schedule; compute.

**Model registry + deploy.** Versioned models; new versions run in **shadow** (scored but not served), then canary 5%, then ramp; rollback means switching the version pointer (R4 Q12). *Why:* twice-a-day model releases need a safe path. *Without it:* every model push is a gamble.

---

## 7. Request flows

**A. Read path: `GET /feed` (budget ~110 ms of a 200 ms p95).**
1. Client → CDN (miss, personalized) → gateway: auth, rate limit (~5 ms).
2. Feed service: experiment bucket lookup; check the cached ranked list for `cursor` (page 2+ returns here).
3. Parallel fan-out to the 4 candidate sources, each with a 40 ms timeout; late sources are dropped (~30–40 ms).
4. Union about 500 candidates → filter seen, language, duplicates (~3 ms).
5. One batched `MGET` of user and article features (~10–15 ms).
6. Ranker scores 500 candidates in one batch (~30–40 ms).
7. Re-rank for diversity and rules; cache the full ranked list for 10 min under `feed_request_id` (~5 ms).
8. Respond with page 1; the client logs impressions with `feed_request_id`.

**B. New article path (breaking news in < 60 s).**
1. Publisher → ingestion: validate, dedupe/cluster.
2. Classify and embed (batched GPU/CPU).
3. Write metadata → article store; upsert the vector → ANN index; push the id → fresh source.
4. Next feed requests pick it up through the *fresh* candidate source, before it has any clicks.

**C. Feedback loop (seconds online, daily offline).**
1. Client batches impressions and clicks → event collector → Pub/Sub/Kafka.
2. Stream processor → Redis: trending counters, seen set, recent interests, article CTR (seconds).
3. Events → data lake → daily training → registry → shadow → canary → full rollout.

---

## 8. Deep dives

### Deep dive 1: holding p95 at 200 ms at 33k RPS

- **Budget it explicitly** (flow A) and enforce it with deadline propagation: the feed service passes the remaining budget to each call (`asyncio.timeout_at`).
- **Parallel fan-out with per-source timeouts.** Personalization is "best effort": if ANN is slow, serve trending + topics. Hedge the slowest call (send a duplicate after the p95 latency) only if it's idempotent and cheap.
- **Batch everything.** One `MGET` for 500 feature keys, not 500 GETs (500 × 0.5 ms round trips = 250 ms, already over budget).
- **Python specifics.** Async I/O for the fan-out; CPU work (ranking, numpy) in a C-backed runtime or process pool so it doesn't block the event loop or fight the GIL. Keep connection pools warm: Postgres/Redis pool exhaustion shows up as a latency cliff, not as errors.
- **The 28× spike.** Pushes are scheduled, so **pre-scale before each push** (scheduled HPA/cron scaling). Then shed load in tiers: first drop the expensive personal ANN source, then serve the CDN trending feed. Never return 5xx when a generic feed would do.

### Deep dive 2: precompute vs online, and caching

- **Fully precomputed feeds** (batch job writes each user's feed): fast reads, but stale (breaking news is missed), expensive for users who never return, and the storage is 100M × 20 ids.
- **Fully online** (rank everything per request): fresh, but expensive, and the latency is hard to hold.
- **Hybrid (chosen).** Precompute the slow parts (user embeddings daily, ANN index, trending counters continuously) and do the cheap parts online (retrieval from in-memory ANN, ranking ~500 candidates). Freshness comes from the *fresh* source and streaming features.
- **Cache layers:** CDN for the trending/fallback feed; ranked-list cache per `feed_request_id` (pagination stability); feature store in Redis; ANN index in process memory. Hit ratio to quote: page 2+ requests are ~100% cache hits.
- News is **pull-and-rank on read**, unlike a social feed's fan-out-on-write. There's no "followers" graph to push to, and relevance changes by the minute.

---

## 9. Failure modes

| Failure | Effect | Mitigation |
| --- | --- | --- |
| Ranker down/slow | can't score | fall back to candidate-source scores (ANN similarity, trending score); alert |
| ANN index unavailable | no personal candidates | trending + topics + fresh; feeds are less personal, not broken |
| Redis feature store down | no features | default/global features; still rank; or serve trending |
| Pub/Sub consumer lag | stale trending, seen set lags (repeats) | alert on lag; autoscale consumers; trending degrades gracefully |
| Push-notification spike | 28× load in seconds | pre-scale on the push schedule; tiered load shedding; CDN fallback |
| Bad model deployed | CTR drops | shadow + canary with CTR/latency guardrails; rollback = switch the version pointer |

- **Where data can be lost:** client event batches (app killed before flush), so persist them on the device and retry. The collector accepts at-least-once delivery, and impressions dedupe on `(feed_request_id, article_id)`. Losing a few impressions is acceptable; losing a whole day is not, so the event log is the durable record.
- **SPOF you accept:** single region (for the read path) behind a CDN fallback. Multi-region active-active isn't worth its cost for a news feed with a static fallback.
- **10× traffic tomorrow:** first to break is Redis feature store connections and throughput, then ranker CPU, then Postgres if article-metadata caching misses. That's why the metadata cache and connection pooling exist.

---

## 10. Trade-offs (chosen against)

- **Two-stage retrieve → rank** over one big model on all articles: you can't score 500k articles in 40 ms.
- **Hybrid** over fully precomputed feeds: freshness wins in news.
- **In-memory ANN** over a remote vector DB: 0.5 GB fits in RAM and saves a network hop. Revisit if the corpus grows 20×.
- **Redis** over Bigtable/Cassandra for online features: lower latency at this size; the cost is memory, and persistence is weaker (it's a cache of truth in the lake).
- **Eventual consistency** for features and counters: a click influencing the next feed after 10 s is fine; strong consistency would buy nothing.
- **A lightweight ranker** over a deep model: holds the CPU budget at 40k RPS; a heavier model can come with GPU serving later.

---

## 11. v1 vs later (2 engineers, 6 weeks)

**v1:** trending + topic candidates + simple personal ranking from category affinities (no ANN), Redis for counters and seen sets, the CDN fallback, event logging to the lake, `feed_request_id` from day one.
**Later:** ANN retrieval with embeddings, an ML ranker, shadow/canary model deploys, the experiment service, near-duplicate clustering, streaming features.
The one thing *not* to defer: `feed_request_id` and event logging. Without them you can never train or prove anything.

---

## 12. Interviewer follow-ups

1. **Why is your peak 28× the average?** Push notifications fire to millions at once; the traffic is scheduled, so pre-scale on the push calendar.
2. **How does a brand-new article get recommended with zero clicks?** The *fresh* candidate source plus content embeddings from ingestion; an exploration boost for its first N impressions.
3. **New user with no history?** Region/language trending from the CDN, onboarding topic picks, then streaming features personalize within a few clicks.
4. **How do you A/B test a ranker?** Hash users into buckets; log `feed_request_id` + model version with every impression; compare CTR/dwell with guardrails on latency and diversity.
5. **The ML team ships twice a day: how do you deploy safely?** Registry → shadow scoring → 5% canary with automatic guardrails → ramp; rollback is a pointer switch.
6. **Where is your cache hit ratio, and what's cached?** CDN for the generic feed, ranked lists for pagination (page 2+ ≈ 100%), features in Redis; the personalized first page is computed, not cached.
7. **Why not precompute every user's feed nightly?** Stale for breaking news, wasted on users who don't return, 100M × 20 writes/night.
8. **What happens when Redis is down?** Default features plus trending: the feed degrades and doesn't fail. That's the 0.5% error budget being protected.

---

## 13. Your anchor: Jio News (fill these in with your real answers)

- Your resume says **GCP, GKE, FastAPI, Redis, PostgreSQL, MongoDB, Pub/Sub**. In the 6 Oct session you described **Kafka**. Which was it, and where? An interviewer will catch the mismatch.
- **What drove the 28× peak?** Push notifications, match days, elections? How long did spikes last, and did you pre-scale or rely on HPA?
- **Where was p95 200 ms measured?** At the load balancer, the service, or the device?
- **What was cached, and what was the hit ratio?**
- You split **embedding and similarity** into separate services. Why the split, and what was the call pattern between them?
- You named the **GIL and Postgres connection pooling** as real bottlenecks. What exactly happened, and what did you change? Have a number for before and after.
- **"Single-handedly":** what did the data science team own vs you? Interviewers probe solo-ownership claims.
- **Pods at peak, cost per month, and what Redis and MongoDB each stored.** If you don't remember, estimate it now and say "approximately".
