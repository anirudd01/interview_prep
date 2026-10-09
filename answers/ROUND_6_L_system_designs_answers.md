# Round 6 — Gap Fill & Staff Readiness: Answers, Section L (System Designs)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. **Original question numbers are kept.**

Run each design with the Round 4 rubric, in order: clarify, numbers, API & data model, architecture, deep dives, failure modes, trade-offs and v1 vs later. The numbers below are stated assumptions the interviewer can change; say them out loud and redo the maths when they do. Pick at most one per session.

---

## L. SYSTEM DESIGNS NOT COVERED IN ROUND 4

### 101. Design a multi-tenant, enterprise ChatGPT-style assistant: conversation storage, streaming, context and history management, file uploads, per-tenant quotas, model routing, and data isolation.
**Clarify**: who are the tenants (business units of one company, or external customers on a SaaS)? That decides how hard isolation must be. Which models (Azure OpenAI / Foundry, Anthropic, self-hosted)? Is it chat only, or also RAG over tenant documents and tools/agents? Data residency (EU tenants stay in EU)? Retention and legal hold? Must prompts be logged for audit, and who can read them? SSO via each tenant's IdP?
**Numbers**: say 50 tenants, 500k users, 100k DAU, 20 messages/user/day = **2M messages/day ≈ 23/s average, ~230/s peak** (10×, 9am Monday). Average call: 4k input tokens (history + retrieved context) + 500 output → 2M × 4.5k ≈ **9B tokens/day**: tokens are the cost and the capacity limit, not our RPS. Streams last ~10s, so peak **concurrent streams ≈ 230 × 10 = 2,300** (Little's law). Storage: 2M × ~2KB ≈ 4GB/day ≈ 1.5TB/year of text, trivial; uploaded files dominate storage.
**API**:
- `POST /conversations` → `{id}`; `GET /conversations?cursor=`; `DELETE /conversations/{id}`.
- `POST /conversations/{id}/messages {content, attachments[], model_hint?, idempotency_key}` → **SSE stream** of `delta`, `tool_call`, `citation`, `usage`, `done` events.
- `POST /files` → presigned/SAS upload URL; `GET /files/{id}` status (`uploaded|scanning|indexed|failed`).
**Data** (Postgres, every table carries `tenant_id`, **Row-Level Security** on it):
```
tenants(id, region, plan, model_policy JSON, retention_days, kms_key_id)
conversations(id, tenant_id, user_id, title, summary, summary_upto_seq, created_at)
messages(id, tenant_id, conversation_id, seq, role, content, model, tokens_in, tokens_out, created_at)
files(id, tenant_id, owner_id, blob_key, status, sha256)
chunks(id, tenant_id, file_id, embedding vector, text)        -- pgvector or a per-tenant search index
usage(tenant_id, user_id, day, tokens_in, tokens_out, cost_minor)
```
**Architecture**:
```
client --SSE--> API gateway (auth, tenant resolve, rate limit)
                   |
             chat orchestrator --- context builder (history, summary, RAG) --- vector index (per tenant)
                   |
             quota service (Redis token buckets) --- model router --- LLM gateway --> Azure OpenAI / Anthropic / vLLM
                   |                                                    (retries, fallback, PTU vs pay-go)
             Postgres (conversations, messages)      Blob (files) --> Event Grid --> scan + parse + embed workers
```
**Deep dives**:
- **Streaming**: SSE from orchestrator to client (one-way, works through proxies, auto-reconnect). The orchestrator writes the user message first, streams tokens to the client while buffering them, and persists the assistant message on `done` (or a partial with `status=incomplete` on disconnect/cancel). Disable proxy buffering (Nginx `X-Accel-Buffering: no`), send heartbeats every 15s so idle LBs don't cut the connection. Async Python (FastAPI + httpx) because each stream is I/O-bound and long-lived.
- **Context and history**: never send the whole history. Build the prompt within a **token budget**: system prompt + tenant instructions + a **rolling summary** of older turns (regenerated async every N turns, stored with `summary_upto_seq`) + the last K turns verbatim + retrieved chunks from attached files. Put the stable parts first so **prompt caching** on the provider hits (big cost and latency win). Truncation is by tokens, using the target model's tokenizer.
- **File uploads**: direct to Blob via short-lived SAS, scan, parse (Document Intelligence for PDFs/scans), chunk, embed, index under the tenant's namespace. Same pipeline shape as the ATS resume parsing at Jio and the org RAG pipeline at Aventum.
- **Per-tenant quotas**: two layers. **Rate** (requests/min and tokens/min per tenant and per user) as Redis token buckets checked before the call; tokens are reserved using an estimate (`input + max_tokens`) and corrected with real `usage` after. **Budget** (monthly spend) from the `usage` table, with soft alerts at 80% and a hard stop or downgrade to a cheaper model at 100%.
- **Model routing**: a policy per tenant (allowed models, regions, "no external providers" for some data). The router picks by task (cheap fast model for titles/summaries, frontier model for hard reasoning), by availability (fallback to a second deployment/region on 429/5xx), and by capacity (provisioned throughput first, spill to pay-as-you-go). An LLM gateway (LiteLLM, Azure API Management AI gateway, or our own) centralises keys, retries, and token metering.
- **Data isolation**: tenant ID comes **only from the validated token**, never from the request body. Postgres RLS with `SET app.tenant_id` per transaction as defence in depth; vector search always filtered by tenant (or separate indexes per tenant for large/regulated ones); per-tenant encryption keys (customer-managed keys) for the regulated tier; Blob containers per tenant; logs and traces scrubbed or tagged with tenant so support access is auditable. Caches keyed by tenant. Provider side: use enterprise endpoints with no training on data and zero/limited retention agreements.
**Failure modes**: provider 429/outage (fallback deployment, then degrade with a clear message), client disconnect mid-stream (persist partial, allow regenerate), runaway agent loops burning tokens (max steps, max tokens per request), prompt injection through uploaded files (treat retrieved text as data, no tool calls with side effects without confirmation), cross-tenant leak via a bug in retrieval (tenant filter enforced in the data layer, plus tests that try to read another tenant's data).
**Trade-offs/v1**: pooled multi-tenancy (shared DB + RLS) is cheap and simple; silo (DB per tenant) for the few that need it. v1: chat + streaming + file Q&A + quotas with one provider; later: tools/agents, model router with eval-driven policies, per-tenant fine-tunes, data residency per region.
**Interviewer pushes on**: how do you enforce a token quota when you don't know output length up front? What exactly stops tenant A's chunks from appearing in tenant B's answer? What happens to cost when users paste 100-page documents?

### 102. Design a real-time chat system (1:1 and groups, 10M daily active users): delivery guarantees, per-conversation ordering, presence, read receipts, offline sync, multi-device.
**Clarify**: max group size (100? 10k? channels with 100k members are a broadcast problem)? Message types (text, media, reactions, edits/deletes)? End-to-end encryption (changes what the server can do: no server-side search, fan-out of per-device ciphertexts)? History retention? Multi-device: how many devices per user?
**Numbers**: 10M DAU × 40 messages/day = **400M messages/day ≈ 4.6k/s average, ~15k/s peak**. Average 5 recipients → ~23k deliveries/s average, ~75k/s peak. Peak concurrent online ≈ 30% of DAU = **3M persistent connections**; a tuned gateway node holds ~100k idle-ish websockets, so ~30 nodes, run 50-60 for headroom and failure. Storage: 400M × ~300B ≈ **120GB/day ≈ 44TB/year** before replication (×3).
**API**: websocket for live traffic: `send {client_msg_id, conversation_id, body}` → `ack {client_msg_id, server_seq}`; server pushes `message {conversation_id, seq, ...}`, `receipt`, `presence`. REST for sync and history: `GET /sync?cursor=`, `GET /conversations/{id}/messages?before_seq=`.
**Data**:
```
messages(conversation_id, seq, msg_id, sender_id, client_msg_id, body, created_at)   -- partition key conversation_id (+ bucket for huge groups), clustering seq
conversation_members(conversation_id, user_id, role, last_read_seq, joined_at)
user_inbox(user_id, inbox_seq, conversation_id, seq)    -- per-user change feed for offline sync
devices(user_id, device_id, push_token, last_synced_inbox_seq)
```
Messages in **Cassandra/ScyllaDB** (write-heavy, append-only, partition-by-conversation access pattern, linear scale). Membership and metadata can live in a relational store.
**Architecture**:
```
devices <--ws--> gateway nodes (connections only) --> session registry (Redis: user -> gateway, device)
                        |
                 chat service (per-conversation sequencing) --> Kafka (partition by conversation_id)
                        |                                             |
                 Cassandra (messages)                       fan-out workers --> online: gateway of each recipient
                                                                              --> offline: user_inbox + push (APNs/FCM)
```
**Deep dives**:
- **Per-conversation ordering**: the server assigns a monotonic `seq` per conversation. Route all writes for one conversation to one owner (Kafka partition by `conversation_id`, or a sequencer that does `INCR conv:{id}:seq` in Redis / a lightweight transaction). Clients order by `seq`, never by client clocks. Ordering across conversations is not needed and not promised.
- **Delivery guarantees**: **at-least-once + dedupe = effectively-once**. Client retries `send` until it gets an ack; the server dedupes on `(sender_id, client_msg_id)`. The ack is only sent after the message is durably stored. Recipients ack by `seq`; the client ignores sequences it already has, and a gap in `seq` triggers a fetch of the missing range.
- **Offline sync and multi-device**: each device keeps a cursor into the user's inbox feed (`last_synced_inbox_seq`). On reconnect: `GET /sync?cursor=` returns conversations with new activity and the messages since the device's last seen seq per conversation. Every device of the user (including the sender's other devices) gets the message, so "sent from phone, visible on laptop" just works. Push notifications only for devices not connected.
- **Presence**: the expensive feature. Heartbeat every ~30s, `SET presence:{user} online EX 60` in Redis. Don't broadcast every change to every contact: clients **subscribe to presence only for conversations on screen**, and updates are batched/debounced (a flapping mobile connection shouldn't send 10 events). Large groups get no live presence.
- **Read receipts**: store `last_read_seq` per member per conversation (one row update, not one per message). 1:1 shows "read"; groups show counts or a list fetched on demand; batch receipt events and coalesce (only the highest seq matters).
- **Large groups**: write once, fan out on read for groups above a threshold (members pull from the conversation instead of getting pushes into their inbox), bucket the partition by time to avoid giant partitions.
**Failure modes**: gateway node dies (clients reconnect with jittered backoff to another node, resync from cursor; avoid a reconnect storm with jitter and connection rate limits), Kafka lag (messages stored but delayed; alert on send-to-deliver latency), hot conversation (one partition gets hot: rate limit per conversation, slow-mode), duplicate pushes (dedupe by msg_id on the device).
**Trade-offs/v1**: server-assigned seq gives simple ordering at the cost of a per-conversation serialization point (fine: one conversation never needs more than a few hundred writes/s). E2EE moves fan-out and search to clients. v1: 1:1 + small groups, at-least-once with dedupe, simple presence; later: large channels, E2EE, search, media pipeline.
**Interviewer pushes on**: walk through a message sent while the recipient has one phone offline and a laptop online. What breaks if two users send to the same group at the same millisecond? How does presence not become 90% of your traffic?

### 103. Design search autocomplete for a broker portal (policies, clients, brokers) with p99 under 50ms, typo tolerance, and per-user permission filtering.
**Clarify**: who searches (brokers see only their own book; underwriters see their class/region; admins see all)? What is searched: policy numbers, insured/client names, broker names, addresses? How fresh must results be (a policy bound 5 seconds ago must appear?)? Is 50ms measured server-side or end to end? Languages and diacritics?
**Numbers**: Aurora/Pulse-scale: say 2M policies, 500k clients, 5k brokers ≈ **2.5M documents × ~1KB ≈ 2.5GB** index: fits in memory on a small cluster. 20k users, 2k concurrently active at peak; debounced typing (~150ms) gives maybe **300-500 QPS peak**. Writes: tens of thousands of updates/day, low.
**API**: `GET /suggest?q=smi&types=policy,client&limit=8` → `[{type, id, title, subtitle, highlight}]`. User identity and permissions from the token, never from query params.
**Data/index**: one index (or one per type) in **OpenSearch / Azure AI Search**, documents denormalised: `{id, type, display_name, policy_number, client_name, broker_name, region, class_of_business, acl_tokens: ["broker:123","team:property-uk","region:uk"], status, updated_at}`. Fields: `display_name` analysed with an **edge n-gram** analyzer (index time prefixes, `min_gram 2`), a plain analyzed field for fuzzy matching, a **keyword** field for exact policy numbers (normalised, strip spaces/dashes), ASCII folding for names.
**Architecture**:
```
Postgres (system of record) --CDC/outbox--> indexer --> search cluster (2+ replicas)
browser --debounce--> API (auth, resolve ACL tokens, cache) --> search query (filter + match) --> rank --> response
```
**Deep dives**:
- **Permission filtering**: **pre-filter, never post-filter**. If you fetch top 8 and then drop what the user can't see, you return 0-2 results. Resolve the user's **ACL tokens** at login (broker ID, teams, regions; cache in Redis for minutes) and add them as a `terms` filter on `acl_tokens`. Filters are cached as bitsets by the engine, so they are cheap. Admins skip the filter. Permission changes must reindex affected docs (or keep the ACL tokens coarse, like team and region, so changes are rare). If a user's token list is huge (thousands of brokers), switch to a coarser token or a "global read" role instead.
- **Typo tolerance**: fuzzy match (Levenshtein distance 1 for 4-7 chars, 2 for longer) with **`prefix_length: 1-2`** (the first characters must match exactly, which slashes the candidate set and keeps latency down). No fuzzy on policy numbers; they get exact/prefix matches only. Optionally a phonetic field for names.
- **Ranking**: exact policy-number match first, then prefix match on name, then fuzzy. Boost the user's own and recently viewed items, active over lapsed policies, recency of `updated_at`. Keep it simple and explainable; tune with click logs later.
- **p99 < 50ms**: in-memory index, replicas sized so CPU stays under ~50%, small `size`, only needed fields returned (`_source` filtering), filter caching, query timeout at ~30ms with partial results, API close to the cluster (same region/VNet), Redis cache for very common prefixes per ACL group. Server-side p99 budget ≈ 5ms API + 20ms search + network.
- **Freshness**: outbox/CDC from Postgres → indexer → near-real-time refresh (~1s). If "just created" must appear instantly, the UI can add the user's own recent creations client-side.
**Failure modes**: search cluster slow or down (autocomplete is non-critical: time out, fall back to a Postgres `pg_trgm` exact/prefix search on policy number, or hide suggestions), indexer lag (alert on lag, reindex from the source of truth), stale ACLs leaking data (short ACL cache TTL, revocation events flush cache), reindex without downtime (index aliases, build new then swap).
**Trade-offs/v1**: Postgres `pg_trgm` + GIN can serve 2.5M rows under 50ms for v1 with fewer moving parts; move to a search engine when you need fuzzy + ranking + scale. Coarse ACL tokens trade some precision for cheap reindexing.
**Interviewer pushes on**: why not post-filter? What happens when a broker is moved to another team? How do you measure p99 honestly (client vs server, including network)?

### 104. Design a distributed in-memory cache from scratch (like Redis Cluster): partitioning, replication, eviction, failover, and client routing.
**Clarify**: pure cache (data loss acceptable, rebuildable from DB) or also a primary store? Data types (plain KV vs lists/hashes/sorted sets)? Consistency expectations (can a read after failover return an older value)? Multi-key operations needed? Single region?
**Numbers**: say **2TB** of hot data and **5M ops/s** peak. Keep shards small so failover and resync are fast: ~25GB per shard → **80 primaries + 80 replicas** (160 nodes; ~2.5 nodes' worth of RAM headroom each for fragmentation and fork/copy-on-write). 5M / 80 ≈ **62.5k ops/s per shard**, comfortable for a single-threaded event loop (100k+ ops/s for simple GET/SET). Network: 5M × 1KB ≈ 5GB/s total, ~62MB/s per shard, fine.
**API**: `GET/SET key [EX ttl] [NX]`, `DEL`, `INCR`, `MGET` (same-slot only), `EXPIRE`. Cluster: `CLUSTER SLOTS` (return slot → node map).
**Partitioning**: fixed **16,384 hash slots**, `slot = CRC16(key) mod 16384`. Slots, not nodes, are the unit of ownership, so adding a node means moving some slots, not rehashing everything (same idea as consistent hashing with virtual nodes, but with an explicit, inspectable map). **Hash tags** `{user:42}:cart` force related keys into one slot so multi-key ops work.
**Architecture**:
```
smart client (slot map cache) --TCP--> primary for slot  --async repl--> replica(s)
       ^  MOVED/ASK redirects                |
       +--------------------------------  gossip bus (cluster state, failure detection, config epochs)
```
**Deep dives**:
- **Client routing**: clients fetch the slot map once, hash locally, and talk directly to the owning node (no proxy hop). A node that doesn't own the slot replies **`MOVED slot host:port`** (update map permanently) or, during migration, **`ASK`** (try the target once for this key). Alternative: a proxy layer (Envoy/Twemproxy-style) for dumb clients, at the cost of a hop.
- **Replication**: **asynchronous** primary → replica (command stream + replication offset; full sync via snapshot when a replica is too far behind, partial resync from a backlog buffer otherwise). Async means an acknowledged write can be lost if the primary dies before replicating. Mitigations: `WAIT n timeout` for important writes (still not true consensus), `min-replicas-to-write` so an isolated primary stops accepting writes.
- **Failure detection and failover**: nodes gossip pings; a node not answering within `node-timeout` is marked PFAIL by peers, becomes **FAIL** when a **majority of primaries** agree. Its replicas then hold an election (the one with the most recent offset waits less), a majority of primaries vote, the winner gets a higher **config epoch** and takes the slots. The epoch resolves conflicting claims after partitions. Failover in ~1-2× node-timeout (seconds).
- **Split brain**: a primary on the minority side keeps taking writes until node-timeout, and those are lost when it rejoins as a replica. That's the bounded data loss you accept for a cache; for a store you'd need Raft per shard.
- **Eviction**: `maxmemory` + policy. True LRU needs a linked list per key (memory heavy); instead **sample N keys and evict the best candidate** (approximated LRU), or **LFU** with a small logarithmic counter that decays over time (better for scan-resistant workloads). TTL expiry is lazy (checked on access) plus an active background sampler.
- **Resharding**: move a slot key by key (`MIGRATE`) while serving: source keeps serving keys it still has, replies `ASK` for ones already moved; flip ownership when empty. Rebalance by moving slots to new nodes.
- **Memory and hot spots**: jemalloc fragmentation (active defrag), avoid big keys (a 500MB hash blocks the event loop on delete: use async `UNLINK`), hot keys (client-side near cache with short TTL, or replicate a hot key under N suffixes and read randomly), read from replicas for read-heavy, stale-tolerant traffic.
**Failure modes**: node loss (replica promotion), losing a primary and its replica together (slots unavailable: spread replicas across zones), mass expiry causing a DB stampede (TTL jitter, request coalescing), reconnect storm after failover (client backoff), fork latency for snapshots on huge shards (keep shards small).
**Trade-offs**: availability and latency over consistency (AP-ish with bounded loss). Fixed slots over a consistent-hash ring for operational clarity. Smart clients over proxies for latency. If you need durability and linearizability, you're building a database, use Raft (etcd-style) per shard and pay the latency.
**Interviewer pushes on**: exactly when can an acknowledged write be lost? Why 16,384 slots and not 2^32? What does the client do on MOVED vs ASK?

### 105. Design a metrics / time-series monitoring backend at scale: ingestion, compression, downsampling, retention, query engine, and cardinality limits.
**Clarify**: pull (Prometheus scrape) or push (OTLP/remote-write)? Multi-tenant (many teams)? Query patterns: dashboards over hours, alerts every 30-60s, capacity reports over a year? Retention per resolution? Do we also need logs/traces (out of scope here)?
**Numbers**: **100M active series**, 15s interval → 100M / 15 = **~6.7M samples/s**. Gorilla-style compression ≈ **1.3-1.5 bytes/sample**: 6.7M × 1.37B ≈ 9.2MB/s ≈ **~790GB/day** raw (× replication factor 3 in ingesters, ×1 in object storage after dedupe). 15 days raw ≈ 12TB; 5-minute rollups are 20× smaller, 1-hour rollups 240× smaller, so a year of 1h data is ~1.2TB. Index: series metadata (labels) is often a bigger memory problem than samples.
**API**: write: Prometheus remote-write / OTLP metrics. Read: PromQL `GET /api/v1/query_range?query=&start=&end=&step=`. Admin: per-tenant limits.
**Data model**: series = metric name + sorted label set → series ID. Samples `(series_id, timestamp, float64)`. Storage in **blocks** of 2h: chunks of compressed samples per series + an **inverted index** (label pair → posting list of series IDs) for selecting series by label matchers.
**Architecture** (Mimir/Cortex/Thanos shape):
```
agents (Prometheus agent / OTel collector) --> distributors (validate, limits, hash series to ingesters, RF=3)
                                                     |
                                        ingesters (WAL + in-memory head block, 2h) --flush--> object storage (blocks)
                                                                                                  |
                                                       compactor (merge, dedupe, downsample, retention)
query frontend (split by day, results cache, queue/fairness) --> queriers --> ingesters (recent) + store-gateways (blocks)
```
**Deep dives**:
- **Ingestion**: distributors hash each series (tenant + labels) on a ring to 3 ingesters, quorum write (2 of 3). Ingesters append to a **WAL** (crash recovery) and keep the head block in memory, cut a block every 2h, upload to object storage. Stateless distributors scale horizontally; ingesters scale by series count.
- **Compression**: Gorilla: timestamps as **delta-of-delta** (regular intervals become ~1 bit), values **XOR'd** with the previous value (slow-changing floats share most bits). That's how you get ~1.37 bytes per 16-byte sample.
- **Downsampling**: compactor rewrites old blocks into 5m and 1h resolutions, storing **min, max, sum, count** (and counter-aware values) per window, never just the average, so `max_over_time` and `rate` stay correct. Counters need reset handling before aggregation.
- **Retention**: per tenant and per resolution (raw 15d, 5m 90d, 1h 13 months), enforced by the compactor deleting blocks; object storage lifecycle to cheaper tiers.
- **Query engine**: the frontend splits a 30-day query into daily sub-queries, runs them in parallel, caches results per (query, day, step) since old days don't change, and enforces fairness per tenant. Queriers pick the coarsest resolution that satisfies `step`. Limits: max series per query, max samples loaded, timeout.
- **Cardinality limits**: the real operational killer. One engineer adding `user_id` or `request_id` as a label creates millions of series. Enforce **per-tenant max active series** and **per-metric limits** at the distributor (reject with a clear error), label value length limits, a cardinality explorer ("top metrics by series"), and relabel rules in agents to drop bad labels. Put high-cardinality data in logs/traces/exemplars instead.
**Failure modes**: ingester crash (WAL replay, RF=3 covers the gap), ingester ring rebalancing (slow, so scale ahead), cardinality explosion OOMing ingesters (limits, shuffle-sharding tenants so one bad tenant hits a few ingesters only), expensive dashboard queries (frontend limits, caching), clock skew in samples (out-of-order window, reject too-old samples), alerting must not depend on the slow path (rulers evaluate against ingesters for recent data, and alerting on the monitoring system itself from an independent, simple stack).
**Trade-offs/v1**: v1 is not to build: Prometheus + Thanos/Mimir, or managed (Azure Monitor managed Prometheus + Managed Grafana, Grafana Cloud). Building makes sense only at very large scale or special constraints. Push vs pull: pull gives "is it up" for free; push suits short-lived jobs and serverless.
**Interviewer pushes on**: why is cardinality, not sample rate, the scaling problem? How does `rate()` survive downsampling? How would you alert if the metrics backend itself is down?

### 106. Design a seat/ticket booking system for flash-sale traffic: no double booking, holds with expiry, a fair waiting room, and payment timeouts.
**Clarify**: reserved seating (specific seats) or general admission (counts)? How many events at once, how big? Per-user ticket limits? Payment provider and its latency? What "fair" means (first come first served, or randomised among everyone who arrived before opening)? Bot protection requirements?
**Numbers**: one big event: **50k seats**, **2M users** arrive in the first 10 minutes. Without a queue that's 2M users × several requests in minutes, thousands to tens of thousands of writes/s on 50k rows, mostly conflicts. With a waiting room admitting **2,000 users/minute**, the booking core sees ~33 users/s and a few hundred requests/s: easy. Queue status polling: 2M users every 10s = **200k req/s**, which must be served from the edge, not the booking DB.
**API**: `POST /queue/join {event_id}` → signed queue token with position; `GET /queue/status` (cacheable); `GET /events/{id}/seats` (map, cached a few seconds); `POST /holds {event_id, seat_ids[], admission_token}` → `{hold_id, expires_at}`; `POST /orders {hold_id, idempotency_key}` → payment intent; PSP webhook `POST /payments/webhook`.
**Data** (Postgres; 50k seat rows per event is tiny):
```
seats(event_id, seat_id, status: available|held|payment_pending|sold, hold_id, held_until, version)
holds(id, user_id, event_id, seat_ids[], expires_at, status)
orders(id, hold_id UNIQUE, user_id, amount_minor, status, psp_payment_id, idempotency_key UNIQUE)
```
**Architecture**:
```
users --> CDN/edge waiting room (static page + signed tokens, bot checks)
            | admitted (signed admission token, rate-controlled)
            v
   booking API --> Postgres (seats, holds, orders)    Redis (seat map cache, per-user limits)
        |                     ^
   payment service --> PSP    reaper (expire holds)    outbox --> tickets/email
```
**Deep dives**:
- **No double booking**: the database is the arbiter. One atomic conditional update: `UPDATE seats SET status='held', hold_id=$h, held_until=now()+'10 min' WHERE event_id=$e AND seat_id = ANY($s) AND (status='available' OR (status='held' AND held_until < now())) RETURNING seat_id`. If fewer rows come back than requested, roll back and tell the user which seats went. Partial unique constraints or `version` columns back it up. Redis `SET NX` locks can front this for speed but are not the source of truth.
- **Holds with expiry**: expiry is checked **inline** (the `held_until < now()` clause), so an expired hold is reusable immediately even if the reaper is late. The reaper just cleans up and republishes availability. The seat map is eventually consistent (cached seconds); the hold call is authoritative.
- **Payment timeouts**: when the user starts paying, move seats to **`payment_pending`** and stop the clock from reclaiming them while the PSP call is in flight (with a longer hard limit, e.g. 15 min). PSP result via webhook (idempotent, dedupe on event ID): success → `sold`; failure/timeout → release. If a success arrives after we released and resold the seat (race), **refund automatically** and apologise; that's rare and must be detected by reconciliation against PSP reports. Idempotency keys on every PSP call so retries never double-charge.
- **Fair waiting room**: everyone arriving before opening gets a **random position** (lottery, so refreshing or bots arriving at T-0.001s gain nothing); after opening, FIFO. The token is signed (HMAC/JWT) with position and event, so the queue is mostly stateless. The edge serves `GET /queue/status` as a single global "now admitting up to position N" value cached for 1-2s; clients compare their own position. A controller raises N based on booking-core health (holds/s, error rate, DB latency): **admission rate is the throttle**. Bots: CAPTCHA/attestation at join, one token per verified account, per-account ticket limits.
**Failure modes**: DB overload (the waiting room protects it; admission controller backs off on latency), PSP outage (pause admissions, extend holds), reaper lag (harmless, inline expiry), users opening 10 tabs (token bound to account, one active hold per user), cache showing sold seats as free (hold call fails cleanly, UI refreshes map), duplicate webhooks (dedupe).
**Trade-offs/v1**: general admission is much easier (a counter: `UPDATE inventory SET sold = sold + $n WHERE sold + $n <= capacity`). Strong consistency on seats over availability. Use a managed waiting room (Cloudflare/Queue-it/Azure Front Door rules) for v1 rather than building one.
**Interviewer pushes on**: what happens at second 599 of a 600s hold when the user clicks pay? How do you make the queue fair against bots? Why not just Redis for everything?

### 107. Design a secure execution sandbox for user-submitted code or formulas (e.g. Python or Excel logic uploaded by business users): isolation (containers vs gVisor vs Firecracker), resource limits, network egress control, multi-tenancy, and cold-start latency.
**Clarify**: is the code arbitrary Python, or a formula/rater language we could restrict (huge difference)? Who are the users: internal actuaries (semi-trusted) or external customers (hostile)? Execution length (100ms rating calls or 10-minute jobs)? Does code need network, packages, files? Latency target for a call (Cellular rater APIs are on the quote path, so sub-second)?
**Numbers**: say 200 tenants, **50 executions/s peak**, p50 run 200ms, p99 2s. Little's law: 50/s × ~0.5s average ≈ **25 concurrent executions**; keep a warm pool ~2× that plus per-tenant minimums ≈ 60-100 warm sandboxes. Each microVM ~128-512MB → a few nodes. If cold start were 1-2s per call, it would dominate p50, so warm pools are mandatory.
**API**: `POST /modules {tenant, source|workbook, runtime}` → build/validate → `{module_id, version}`; `POST /modules/{id}/invoke {inputs, timeout_ms}` → `{outputs, logs, usage}`.
**Architecture**:
```
upload --> static checks (AST allowlist, dependency allowlist, size) --> build artifact (versioned, signed)
invoke --> API (auth, tenant quota) --> scheduler --> warm pool manager --> sandbox (microVM / gVisor pod)
                                                               |                  - no creds, no metadata endpoint
                                                               |                  - read-only rootfs + tmpfs
                                            egress proxy (default deny, per-tenant allowlist)
```
**Deep dives**:
- **First, avoid needing a sandbox**: for rater/Excel logic, compile formulas to a **restricted DSL or AST-allowlisted Python** (no imports, no attribute access to dunder names, no I/O), which is roughly what Cellular does by turning workbooks into generated modules. Generated code from a trusted compiler is much safer than arbitrary uploads. Still run it sandboxed as defence in depth.
- **Isolation options**:
  - **Plain containers** (namespaces + cgroups + seccomp + AppArmor, non-root, dropped capabilities): share the host kernel, so one kernel bug = escape. Fine for trusted internal code only.
  - **gVisor** (`runsc`): a user-space kernel (the Sentry) intercepts syscalls, so the host kernel sees a small syscall surface. Easy to adopt as a Kubernetes RuntimeClass, fast start, but overhead on syscall- and I/O-heavy work and some compatibility gaps.
  - **Firecracker / Kata microVMs**: hardware virtualization (KVM), own guest kernel, ~125ms boot and a few MB overhead with Firecracker; strongest isolation, used by AWS Lambda. On AKS, **Pod Sandboxing** (Kata-based VM isolation) gives this per pod. **Azure Container Apps dynamic sessions** offer Hyper-V isolated sandboxes with a ready pool as a managed option.
  - Choice: hostile multi-tenant code → microVM per execution or per tenant session; semi-trusted internal formulas → gVisor or Kata pods, never plain containers shared across tenants.
- **Resource limits**: cgroups v2 CPU quota, memory limit (OOM kill = clean failure), pids limit (fork bombs), wall-clock timeout enforced from outside the sandbox, disk via small tmpfs, output size cap, and per-tenant concurrency quotas so one tenant can't take the pool.
- **Network egress**: default **deny all**. Block the cloud metadata endpoint (169.254.169.254) and the cluster network explicitly; if code needs data, inject it as inputs instead of letting it fetch. Where egress is required, route through an egress proxy with a per-tenant domain allowlist and logging. Sandboxes get **no credentials** (no managed identity, no service account token mounted).
- **Multi-tenancy**: never reuse a sandbox across tenants; ideally destroy after each execution or after each tenant session, and wipe tmpfs. Separate node pools for sandboxes from the control plane. Artifacts signed and versioned per tenant.
- **Cold start**: warm pools of pre-booted sandboxes with the runtime and allowed packages loaded; **snapshot/restore** (Firecracker snapshots resume in tens of ms); pre-import heavy libs once in a template and fork/clone; size pools per tenant from recent traffic, scale on queue depth.
**Failure modes**: escape attempt (layered isolation, patched kernels, seccomp, alert on denied syscalls), infinite loops (external timeout kill), memory bombs (cgroup OOM), pool exhaustion (queue with a deadline, return 429, scale out), noisy neighbour (per-tenant quotas, dedicated pools for big tenants), poisoned module versions (versioned artifacts, instant rollback).
**Trade-offs/v1**: isolation strength vs start latency vs density: containers (fast, weak), gVisor (fast, medium), microVMs (strong, slightly slower, more ops). v1: restricted DSL/AST checks + gVisor or Kata RuntimeClass on AKS + default-deny NetworkPolicy + warm pool; later: Firecracker snapshots for sub-50ms starts, or a managed service.
**Interviewer pushes on**: why is a container not a security boundary? What exactly does the attacker try first (metadata endpoint, service account token)? How do you get p99 under 300ms with VM isolation?

### 108. Design a webhook delivery platform for 5,000 partner endpoints: retries, ordering, signing, per-endpoint rate limits, a circuit breaker per endpoint, replay, and a partner dashboard.
**Clarify**: event volume and burstiness? Do partners need ordering, and at what scope (per resource like a policy, or global per endpoint)? Delivery SLA (seconds)? Retention for replay? Do partners filter by event type? Self-serve onboarding (then SSRF matters a lot)?
**Numbers**: say **50M events/day ≈ 580/s average, ~5k/s peak**. Partner endpoints are slow: 300ms average, some 10s timeouts. Concurrency needed = 5k/s × 0.5s ≈ **2,500 in-flight requests** at peak, plus retries; async HTTP workers (asyncio/httpx) handle thousands each. Storage: 50M × ~2KB ≈ **100GB/day**, 30 days replay ≈ 3TB, plus attempt logs.
**API**: internal producers: `POST /events {type, resource_id, payload, idempotency_key}`. Partners: `POST /endpoints {url, event_types[], ordered: bool, rate_limit}`, `POST /endpoints/{id}/rotate-secret`, `GET /deliveries?status=failed`, `POST /endpoints/{id}/replay {from, to, event_types}`, `POST /deliveries/{id}/retry`.
**Data**:
```
events(id, type, resource_id, payload, created_at)                      -- immutable, retained 30 days
endpoints(id, partner_id, url, secrets[], event_types[], ordered, rate_limit, state: active|open|disabled)
deliveries(id, event_id, endpoint_id, status, attempts, next_attempt_at, last_status_code)
attempts(delivery_id, attempt_no, at, status_code, latency_ms, response_snippet)
```
**Architecture**:
```
producers --outbox--> Kafka (events) --> fan-out (match subscriptions) --> deliveries table / per-endpoint queues
                                                                              |
                         scheduler (fair across endpoints, rate limit, breaker) --> delivery workers --> egress proxy --> partners
                                                                              |
                                                  attempts log --> partner dashboard + metrics
```
**Deep dives**:
- **Isolation per endpoint**: the core problem is **head-of-line blocking**: one partner timing out for 10s must not delay the other 4,999. So no single shared FIFO. Use per-endpoint queues (Postgres `deliveries` with `next_attempt_at` and `SKIP LOCKED`, or Redis per-endpoint lists) and a scheduler that round-robins endpoints with a per-endpoint concurrency cap.
- **Retries**: exponential backoff with jitter (e.g. 30s, 2m, 10m, 1h, 6h ... up to ~3 days), retry on timeouts, 5xx and 429 (respect `Retry-After`), don't retry most 4xx. After the last attempt → failed state, visible in the dashboard, replayable.
- **Ordering**: default **unordered** (fast, parallel) and every payload carries `event_id`, `created_at` and a per-resource `sequence`/version so partners can discard stale updates. For endpoints that opt in, enforce **one in-flight delivery per (endpoint, resource_id)** and block later events for that key until the earlier one succeeds or is dead-lettered; that costs throughput and lets one poison event block a key, so cap the block time.
- **Signing**: HMAC-SHA256 over `{event_id}.{timestamp}.{body}` (the Standard Webhooks scheme), headers `webhook-id`, `webhook-timestamp`, `webhook-signature`. Partners verify and reject timestamps older than ~5 min (replay protection) and dedupe on `webhook-id`. **Secret rotation**: send signatures for both old and new secret during an overlap window. mTLS or asymmetric signatures for partners that want them.
- **Per-endpoint rate limits**: token bucket per endpoint in the scheduler (configured by the partner or adaptive on 429s).
- **Circuit breaker per endpoint**: track failure rate over a window; on threshold → **open** (stop sending, keep queueing), after cooldown → **half-open** (one probe), success → closed. Failing for days → disable the endpoint and email the partner; their backlog stays replayable.
- **Replay**: events are immutable and retained, so replay just creates new deliveries for a time range/filter, at a throttled rate, marked as replays (same `event_id`, so partner dedupe works).
- **Security**: SSRF is the big one for self-serve URLs: HTTPS only, resolve DNS at **delivery time** and block private/link-local/metadata ranges (re-check after redirects, or don't follow redirects), send from fixed egress IPs partners can allowlist.
- **Dashboard**: per endpoint success rate, latency, last errors with request/response snippets, breaker state, "send test event", manual retry and replay.
**Failure modes**: partner down for a day (breaker, backlog grows on disk not memory, throttled drain on recovery so we don't DDoS them), worker crash mid-request (at-least-once: redelivery, partners dedupe), Kafka/DB outage (outbox on producer side keeps events), huge payloads (cap size, send a thin event + fetch URL), noisy endpoint hogging workers (per-endpoint concurrency cap).
**Trade-offs/v1**: at-least-once, not exactly-once (impossible over HTTP; idempotent receivers). Unordered by default, ordered opt-in. Buy vs build: Svix/Hookdeck or Azure Event Grid push delivery can cover v1; build when the dashboard and partner experience is the product.
**Interviewer pushes on**: show how one slow partner can't slow the others. How does a partner verify a signature during secret rotation? What stops someone registering `http://169.254.169.254/` as their URL?

### 109. Design an internal LLM evaluation and experimentation platform used by 10 product teams: datasets, runs, LLM judges, human annotation queues, CI integration, and dashboards.
**Clarify**: what is being evaluated: prompts, RAG pipelines, agents, models, or all? Offline only, or also production traces sampled into evals? Who annotates (team members, SMEs like underwriters, vendors)? Data sensitivity (PII in datasets, which judge models are allowed)? Budget for judge calls? Build vs buy appetite?
**Numbers**: 10 teams × 20 runs/day × 1,000 rows = **200k generations/day**, with ~3 judge calls per row = **600k judge calls**, ~800k LLM calls/day ≈ 9/s average but very bursty (CI and nightly). Judge cost: 600k × ~2k tokens ≈ **1.2B tokens/day**; at ~$1 per million input tokens for a mid-tier judge that's ~**$1.2k/day**, so caching, sampling and per-team budgets matter. Storage is small (millions of rows of text, tens of GB/month).
**API/SDK**: Python SDK used in notebooks and CI: `dataset = evals.dataset("claims-qa", version=7)`; `run = evals.run(dataset, target=my_pipeline, scorers=[exact_match, faithfulness_judge], tags={git_sha})`; `evals.compare(run_a, run_b)`. REST: `/datasets`, `/runs`, `/runs/{id}/results`, `/annotation-queues/{id}/next`, `/judges`.
**Data**:
```
datasets(id, team, name)  dataset_versions(id, dataset_id, version, created_at, frozen)
examples(id, dataset_version_id, input JSON, reference JSON, metadata, split)
targets(id, team, kind: prompt|pipeline|agent, config JSON, git_sha)
runs(id, dataset_version_id, target_id, model, params, status, cost, started_at)
results(run_id, example_id, output, latency_ms, tokens, trace_id)
scores(result_id, scorer_id, scorer_version, value, rationale, source: auto|judge|human)
judges(id, version, model, prompt, rubric, calibration_stats)
annotation_tasks(id, queue_id, result_id, assignee, status, claimed_until, label JSON)
```
**Architecture**:
```
SDK / CI / UI --> API --> Postgres (metadata, scores)     Blob (large inputs/outputs, artifacts)
                    |
             run orchestrator --> work queue --> workers (call target, call judges) --> LLM gateway (rate limits, cache, budgets)
                    |
     prod traces (OpenTelemetry GenAI spans) --> sampler --> "add to dataset" / annotation queues
                    |
     analytics (ClickHouse or Postgres views) --> dashboards: run comparison, regressions, cost, judge-human agreement
```
**Deep dives**:
- **Datasets**: versioned and **immutable once used in a run** (otherwise comparisons are meaningless). Sources: hand-written golden sets, production traces (sampled, PII-scrubbed), and failures found in annotation. Splits (smoke subset for CI, full set nightly, held-out set nobody tunes against).
- **Runs**: a run = dataset version × target config × model × params, fully recorded so it's reproducible. Workers fan out per example with concurrency limits per provider; results cached by `hash(model, prompt, input, params)` so re-running unchanged parts is free. Record latency, tokens and cost per row next to quality.
- **LLM judges**: judges are **versioned prompts + rubric + model**, treated as code. Known biases: position bias (swap order in pairwise and average), verbosity bias, self-preference (don't judge a model with itself), so prefer **pairwise or rubric-based binary checks** over vague 1-10 scores. **Calibrate every judge against human labels** (agreement or Cohen's kappa on a few hundred examples) and show the agreement number on the dashboard; a judge below threshold is not allowed to gate CI. Cheap deterministic scorers first (exact match, JSON schema validity, citation present), judges only for what needs them.
- **Human annotation queues**: tasks pulled from queues with **claim/release locks and timeouts** (same pattern as the RLHF dashboard: Redis claim locks, claimed_until), blind review (annotator doesn't see which variant), gold questions to monitor annotator quality, inter-annotator agreement with overlap on a sample, SMEs (e.g. underwriters for insurance answers) routed by tag.
- **CI integration**: on PR, run the smoke set (~50-200 examples) against the changed prompt/pipeline, post a comparison to the PR, and **gate on regressions with statistical sense**: bootstrap confidence intervals on the metric delta, so a 1% drop on 100 examples isn't treated as real. Full nightly runs on main with trends. Budgets and timeouts so CI doesn't cost $500 per PR.
- **Dashboards**: run-vs-run diff (per example, sortable by largest regressions), metric trends per team, cost and latency per run, judge-human agreement, annotation throughput.
- **Multi-team**: per-team namespaces and quotas, shared library of scorers and judges, RBAC on datasets with sensitive data, audit of who used what data.
**Failure modes**: provider rate limits during big runs (gateway queues and backoff, resumable runs that skip completed rows), flaky judges (fixed temperature 0, versioned, re-score on judge change instead of mixing versions), dataset drift vs production (regular sampling of prod traces), teams gaming the metric (held-out sets, human spot checks), PII leaking into datasets (scrub on ingest, access controls).
**Trade-offs/v1**: buy/self-host vs build: Langfuse (self-hostable, traces + datasets + annotation), Braintrust, LangSmith, MLflow GenAI evaluation, promptfoo/Inspect for CI. A good staff answer: **self-host one (e.g. Langfuse on AKS) for v1**, standardise the SDK and scorer library, and build only the glue (CI gates, insurance-specific judges, SME queues). Build fully only if data residency or scale rules the tools out.
**Interviewer pushes on**: how do you know your LLM judge is right? How do you stop CI flakiness from LLM non-determinism? How would 10 teams share judges without one team's rubric change silently moving everyone's numbers?
