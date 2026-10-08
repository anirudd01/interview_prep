# Round 2 — Fundamentals Breadth: Answers

Companion to `questions/ROUND_2_fundamentals_breadth.txt`. Same numbering. Short answer for direct questions, a paragraph for bigger ones.

Where a question asks "which did *you* use / where did it bite *you*", I give the technical answer plus a note marked **Your story:** — those you have to fill in from real experience. Don't memorise my wording for those.

---

## A. PYTHON BASICS

### 1. What is the GIL, and name two situations where it genuinely does not matter.
The GIL (Global Interpreter Lock) is a mutex in CPython that lets only one thread execute Python bytecode at a time. It exists because CPython's memory management (reference counting) isn't thread-safe.
It doesn't matter when: (1) the work is **I/O-bound** — the GIL is released while a thread waits on network/disk, so threads still overlap; (2) the heavy work runs in **C extensions that release the GIL** (NumPy, hashing, zlib, many DB drivers); (3) you use **multiprocessing** — each process has its own interpreter and GIL; (4) plain **asyncio** — single thread anyway, so no contention.
Side note: Python 3.13+ has an optional free-threaded (no-GIL) build; it's not the default yet.

### 2. list vs tuple vs set vs dict - time complexity of membership check in each, and when would you pick a tuple over a list for a real reason?
`x in list` → O(n). `x in tuple` → O(n). `x in set` → O(1) average. `x in dict` (checks keys) → O(1) average. Sets/dicts use hash tables; worst case O(n) with pathological collisions.
Tuple over list for a real reason: **immutability makes it hashable** (if its elements are), so it can be a dict key or set member — e.g. `(tenant_id, user_id)` or `(lat, lon)` as a cache key. Also: signals "fixed-shape record", safe to share without defensive copies, slightly less memory.

### 3. Mutable default arguments - why is `def f(x=[])` a bug? What's the fix?
Default values are evaluated **once, when the function is defined**, not on each call. So every call that uses the default shares the same list, and mutations persist between calls.
Fix: `def f(x=None): if x is None: x = []`.

### 4. Shallow vs deep copy - give an example where the difference caused a real bug.
Shallow copy (`copy.copy`, `list(x)`, `x[:]`, `dict(x)`) creates a new outer container but the nested objects are still the *same* objects. Deep copy recursively copies everything.
Classic bug: copying a default config dict that contains nested dicts, then modifying `cfg["db"]["pool"] = 50` for one tenant — and every other tenant (and the default) changes too, because the nested `db` dict is shared. Fix: `copy.deepcopy(DEFAULT_CONFIG)`.

### 5. What does a generator give you that a list doesn't? When is a generator the wrong choice?
Gives you: **lazy evaluation** — values produced one at a time, O(1) memory regardless of size, can represent infinite streams, and lets you build streaming pipelines (read file → parse → transform → write) without loading everything.
Wrong choice when: you need `len()`, indexing or slicing; you need to iterate **more than once** (a generator is exhausted after one pass); you need to share/pickle results; the data is small and a list is simpler; or you need to debug/inspect the contents easily.

### 6. `is` vs `==`. Why does `256 is 256` behave differently from `257 is 257`?
`==` compares **value** (calls `__eq__`). `is` compares **identity** (same object in memory).
CPython pre-allocates and caches small ints from -5 to 256, so those are always the same object → `is` returns True. 257 is not cached, so separately created 257s can be different objects (in the REPL, `a = 257; b = 257; a is b` is usually False; inside one compiled block the compiler may reuse a constant, so it can be True). Rule: use `is` only for `None`/singletons, never for value comparison.

### 7. How does Python manage memory? Refcounting + generational GC - what does the cycle collector actually do?
Every object has a reference count; when it hits 0, memory is freed immediately. That handles most cases deterministically.
Refcounting can't free **reference cycles** (A → B → A, count never reaches 0). The cyclic GC handles those: it only tracks container objects (lists, dicts, instances), organised in 3 generations. New objects start in gen 0; survivors get promoted to gen 1, then 2. Younger generations are collected far more often (most objects die young). A collection works out which objects are only referenced from *within* the candidate set (by subtracting internal references from the refcount) — those are unreachable cycles, so it finalises and frees them. You can inspect/tune with the `gc` module.

### 8. What is a context manager and how would you write one without contextlib?
An object that sets something up on entering a `with` block and guarantees cleanup on exit, even if an exception occurs. You implement `__enter__` and `__exit__`:
```python
class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self                      # bound to the `as` variable
    def __exit__(self, exc_type, exc, tb):
        self.elapsed = time.perf_counter() - self.start
        return False                     # True would swallow the exception
```
Typical uses: files, locks, DB transactions, temporary state.

### 9. Decorators: write (verbally) a decorator that retries a function 3 times with backoff.
Three layers: an outer function taking the config (`retries`, `base_delay`), which returns the actual decorator, which takes the function and returns a wrapper. The wrapper loops up to N attempts, calls the function in a try/except, on failure sleeps `base_delay * 2**attempt` (ideally plus jitter), and re-raises on the last attempt. Use `functools.wraps` to preserve the function's name/docstring.
```python
def retry(retries=3, base_delay=0.5, exceptions=(Exception,)):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt == retries - 1:
                        raise
                    time.sleep(base_delay * 2**attempt + random.random() * 0.1)
        return wrapper
    return decorator
```
Mention: only retry transient/idempotent errors; for async functions the wrapper must be `async` and use `asyncio.sleep`.

### 10. `__slots__` - what problem does it solve and what does it cost you?
Normally each instance has a `__dict__` (a per-instance hash table) for attributes — memory heavy. `__slots__ = ("a", "b")` replaces it with fixed storage, saving significant memory when you have millions of small objects and making attribute access slightly faster.
Costs: can't add arbitrary attributes dynamically; no `__weakref__` unless you add it to slots; trickier with inheritance/multiple inheritance; can't have class-level defaults with the same name as a slot. `@dataclass(slots=True)` is the convenient way.

### 11. Difference between `async def`, a coroutine, a Task, and a Future.
`async def` defines a coroutine **function**. Calling it returns a **coroutine object** — it does nothing until awaited or scheduled. A **Task** wraps a coroutine and schedules it on the event loop (`asyncio.create_task`) so it runs concurrently with others. A **Future** is a low-level placeholder for a result that will be set later; Task is a subclass of Future. In day-to-day code you use `await` and tasks; you rarely touch raw Futures.

### 12. What happens if you call a blocking `requests.get()` inside an async FastAPI endpoint?
It **blocks the entire event loop** for the duration of the call, so every other request on that worker stalls — latency spikes and throughput collapses. Fixes: use an async client (`httpx.AsyncClient`/`aiohttp`), make the endpoint a plain `def` (FastAPI runs it in a threadpool), or wrap with `asyncio.to_thread` / `run_in_threadpool`.

### 13. multiprocessing vs threading vs asyncio - give one real workload for each from your own projects.
- **multiprocessing** → CPU-bound work, bypasses the GIL: e.g. parsing/OCR/embedding batches of documents (think Jio ATS resume processing).
- **threading** → blocking I/O with libraries that aren't async: e.g. boto3 calls, legacy DB drivers, calling a sync SDK.
- **asyncio** → massive numbers of concurrent network waits: e.g. fanning out LLM/API calls, streaming SSE responses, many websocket clients.
**Your story:** pick the real one from your projects and say why that model fit.

### 14. What's the difference between `@staticmethod`, `@classmethod`, and a plain method?
Plain method receives the instance (`self`). `@classmethod` receives the class (`cls`) — used for alternative constructors (`User.from_json(...)`) and it respects subclasses. `@staticmethod` receives nothing — just a function namespaced inside the class.

### 15. What are Python's dunder methods you've actually implemented in production code?
Common real ones: `__init__`, `__repr__`/`__str__`, `__eq__` + `__hash__` (always together), `__enter__`/`__exit__`, `__iter__`/`__next__`, `__len__`, `__getitem__`, `__call__`, `__lt__` (ordering), `__bool__`, `__post_init__` (dataclasses).
**Your story:** name the ones you truly wrote and what for — don't claim `__getattr__` magic you haven't used.

---

## B. WEB / API

### 16. FastAPI vs Flask - beyond "async", what architecturally differs? Where does Pydantic fit and what does it cost at request time?
FastAPI is an **ASGI** framework built on Starlette; Flask is **WSGI**, synchronous, minimal. FastAPI is driven by **type hints**: path/query/body parsing, validation, serialization, a dependency injection system and auto-generated OpenAPI docs all come from function signatures. Flask gives you routing and leaves validation/serialization to you.
Pydantic is the validation/serialization layer: it parses the request body into typed models and serializes the response via `response_model`. Cost: CPU per request for validation and serialization — pydantic v2's core is in Rust so it's fast, but large/deeply nested payloads and `response_model` re-validation add measurable overhead. Mitigate with simpler models, returning pre-validated data, or skipping `response_model` on hot paths.

### 17. What is ASGI vs WSGI? Why can't Flask (classic) do WebSockets natively?
WSGI is a synchronous interface: one callable handles one request and returns one response — then it's done. ASGI is the async successor: an event-based interface that supports HTTP, **WebSocket**, and lifespan events, with long-lived connections and concurrency in one process.
Classic Flask can't do WebSockets natively because WSGI has no concept of a persistent, bidirectional connection, and each worker is tied up per request/connection. You need extensions (flask-sock, gevent/eventlet) or move to ASGI.

### 18. FastAPI `Depends` - how does dependency caching work within a request?
By default (`use_cache=True`) a dependency is called **once per request**, and the result is reused if the same dependency appears multiple times in the dependency tree (e.g. `get_current_user` used by both the endpoint and another dependency). Pass `Depends(dep, use_cache=False)` to force re-evaluation. Dependencies with `yield` run their cleanup after the response.

### 19. Difference between `def` and `async def` path operations in FastAPI - what does FastAPI do differently under the hood for each?
`async def` endpoints run **directly on the event loop** — so they must never block. Plain `def` endpoints are run in an **external threadpool** (AnyIO, default ~40 threads), so blocking code is OK but you pay thread overhead and are limited by the pool size.

### 20. gRPC vs REST - three concrete reasons to pick gRPC, and two reasons not to.
Pick gRPC: (1) compact binary protobuf — faster and smaller payloads; (2) strongly typed contract + code generation in many languages; (3) HTTP/2 multiplexing plus first-class streaming (client, server, bidirectional), deadlines and cancellation propagation. Great for internal service-to-service.
Don't: (1) poor native browser support (needs grpc-web/proxy) and weak fit for public APIs; (2) harder to debug/inspect (binary, no curl), and awkward with HTTP caching/CDNs; also long-lived HTTP/2 connections need L7-aware load balancing.

### 21. What is protobuf backward/forward compatibility? What field changes are safe?
Fields are identified on the wire by **tag number**, not name. Backward compatible = new code can read old data; forward compatible = old code can read new data (it ignores unknown fields).
Safe: adding new fields with new tag numbers; removing a field *if* you `reserve` its number and name; renaming (wire-safe, but breaks JSON mapping); adding enum values. Unsafe: changing a field's number, changing type incompatibly (e.g. string ↔ int), reusing a deleted tag number, changing repeated ↔ singular carelessly.

### 22. SSE vs WebSockets vs long polling - decision table. Which did you use where and why?
| | Long polling | SSE | WebSocket |
|---|---|---|---|
| Direction | Server→client (via repeated requests) | Server→client only | Full duplex |
| Transport | Plain HTTP | HTTP, one long response | Upgraded TCP connection |
| Reconnect | Manual | Built-in (`Last-Event-ID`) | Manual |
| Data | Anything | Text only | Text + binary |
| Proxy/LB friendliness | Best | Good (turn off buffering) | Needs upgrade support/sticky handling |
| Use for | Legacy/fallback | LLM token streaming, notifications, live feeds | Chat, collaboration, games, bidirectional |

**Your story:** you used SSE for streaming (Turing project per the question bank) — say it's one-way, simple, auto-reconnect, works over plain HTTP; and where you'd choose WebSockets instead.

### 23. HTTP status codes: when do you return 400 vs 409 vs 422 vs 429? What does a Retry-After header do?
- **400** — malformed/unparseable request or generic client error.
- **422** — well-formed but semantically invalid (FastAPI's default for validation errors).
- **409** — conflicts with current resource state (duplicate create, version/ETag mismatch, optimistic-lock failure).
- **429** — rate limited.
`Retry-After` (seconds or an HTTP date) tells the client how long to wait before retrying; well-behaved clients honour it, ideally with jitter. Also used with 503.

### 24. Idempotency in APIs - what is an idempotency key and how would you implement one?
An idempotent operation gives the same result no matter how many times it's repeated (GET/PUT/DELETE are by definition; POST isn't). An idempotency key is a unique client-generated ID (UUID) sent in a header (`Idempotency-Key`) for one logical operation, so retries after timeouts don't double-charge/double-create.
Implementation: on request, atomically claim the key (table with a unique constraint, or Redis `SET key NX EX`). If new → mark in-progress, execute, store the response (status + body) against the key. If it exists and is complete → return the stored response without re-executing. If in-progress → return 409/wait. Store a hash of the request so the same key with a different payload is rejected. Expire keys after ~24h. Ideally commit the stored result in the same DB transaction as the side effect.

### 25. What is CORS, and what actually happens in a preflight request?
Browsers enforce the same-origin policy: JS on `a.com` can't read responses from `b.com` unless `b.com` opts in via CORS headers. It's enforced by the browser, not the server — curl ignores it.
For "non-simple" requests (methods other than GET/HEAD/POST, custom headers like `Authorization`, `Content-Type: application/json`), the browser first sends an `OPTIONS` **preflight** with `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`. The server replies with `Access-Control-Allow-Origin/Methods/Headers` (and `Max-Age` to cache it). If allowed, the browser sends the real request. With credentials you can't use `*` as the allowed origin.

### 26. REST pagination: offset vs cursor. Why does offset pagination break at scale?
Offset (`LIMIT 20 OFFSET 100000`) forces the DB to read and discard all skipped rows — cost grows linearly with page depth — and results shift when rows are inserted/deleted between page requests (duplicates/missing items).
Cursor/keyset pagination (`WHERE (created_at, id) < (:last_created, :last_id) ORDER BY created_at DESC, id DESC LIMIT 20`) uses an index seek, constant cost, stable results. Tradeoff: no jumping to arbitrary page N, and you need a unique, indexed sort key.

### 27. What is the N+1 problem in an API context and how do you detect it?
One query to fetch a list, then one extra query per item to fetch a related object (e.g. list 100 orders, then lazy-load each order's customer → 101 queries). It also happens at the API level when a client calls an endpoint once per item.
Detect: log/echo SQL (SQLAlchemy `echo=True`), APM traces showing many near-identical queries per request, `pg_stat_statements` with huge call counts, query counters in tests. Fix: eager loading (`joinedload`/`selectinload`), joins, batching, DataLoader-style batching, or a bulk endpoint.

### 28. API versioning strategies - URL, header, content negotiation. What did you use?
- **URL** (`/v1/users`) — simplest, visible, cache/route-friendly; most common.
- **Header** (`API-Version: 2`) — clean URLs but less discoverable.
- **Content negotiation** (`Accept: application/vnd.company.v2+json`) — most "RESTful", hardest to test/use.
Best practice: prefer additive, non-breaking changes; only cut a new version for breaking ones, and deprecate with notice.
**Your story:** most likely URL versioning — say what you actually did.

---

## C. DATABASES

### 29. ACID - explain each letter with a real failure you've seen when one wasn't held.
- **Atomicity** — all steps of a transaction happen or none do. Failure: transfer debits account A, crashes before crediting B → money vanished.
- **Consistency** — a transaction takes the DB from one valid state to another; constraints (FK, unique, check) always hold. Failure: orphan rows because FK/constraint wasn't enforced.
- **Isolation** — concurrent transactions don't see each other's partial work. Failure: two requests both read stock=1 and both sell it (lost update / oversell).
- **Durability** — once committed, it survives a crash (WAL flushed to disk). Failure: a cache/DB with async/no fsync loses acknowledged writes on power loss.
**Your story:** pick a real incident for at least one letter.

### 30. Postgres isolation levels. What is a phantom read, and does Postgres' REPEATABLE READ allow it?
Levels: Read Uncommitted (Postgres treats it as Read Committed), **Read Committed** (default — each statement sees data committed before it started), **Repeatable Read** (the whole transaction sees one snapshot), **Serializable** (behaves as if transactions ran one at a time; uses SSI, may abort with serialization failures).
A **phantom read**: within one transaction you run the same range query twice and the second returns extra/missing rows because another transaction committed inserts/deletes in between. Postgres' REPEATABLE READ is snapshot-based, so it does **not** allow phantoms (stricter than the SQL standard) — but it still allows write skew; use SERIALIZABLE for that. Dirty reads never happen in Postgres.

### 31. B-tree vs GIN vs GiST vs BRIN vs HNSW - name a workload for each.
- **B-tree** — default; equality, range, ORDER BY (ids, timestamps, strings).
- **GIN** — inverted index for "many values per row": JSONB containment, arrays, full-text (`tsvector`), trigram search.
- **GiST** — generalized balanced tree for geometry/ranges/nearest-neighbour: **PostGIS** spatial queries, range types, exclusion constraints.
- **BRIN** — tiny index storing min/max per block range; for huge append-only tables physically ordered by the column (time-series logs by timestamp).
- **HNSW** — graph-based approximate nearest neighbour for vector similarity: **pgvector** embeddings.

### 32. What is a covering index? What is index-only scan?
A covering index contains every column a query needs, so Postgres can answer from the index without visiting the table (heap). In Postgres: `CREATE INDEX ... ON t (a) INCLUDE (b, c)`. An **index-only scan** is that execution plan. Caveat: Postgres still needs the visibility map to confirm rows are visible — if VACUUM hasn't run recently, it falls back to heap fetches, and `EXPLAIN ANALYZE` shows `Heap Fetches: N`.

### 33. Explain MVCC in Postgres. What is bloat, and what does VACUUM actually do?
MVCC (multi-version concurrency control): an UPDATE doesn't modify a row in place; it writes a **new row version** and marks the old one as expired (tracked via `xmin`/`xmax`). Each transaction sees a consistent snapshot, so readers never block writers and vice versa.
The old versions (dead tuples) pile up → **bloat**: tables/indexes larger than needed, slower scans, wasted cache. **VACUUM** finds dead tuples no transaction can see anymore and marks their space reusable, updates the visibility map (enables index-only scans) and freezes old transaction IDs (prevents wraparound). It doesn't normally shrink the file (`VACUUM FULL` does, but takes an exclusive lock). Autovacuum does this in the background; long-running transactions block cleanup and cause bloat.

### 34. Connection pooling - why does Postgres need PgBouncer? Transaction vs session pooling and what breaks in transaction mode.
Postgres uses a process per connection (several MB each, plus context-switching), so thousands of direct connections degrade it. PgBouncer keeps a small pool of real server connections and multiplexes many client connections onto it.
**Session pooling**: a server connection is held for the client's whole session — safe, little multiplexing benefit. **Transaction pooling**: a server connection is held only during a transaction — much better multiplexing, but anything relying on session state breaks: session-level `SET`, advisory locks, `LISTEN/NOTIFY`, temp tables, `WITH HOLD` cursors, and (in older PgBouncer versions) prepared statements — a common gotcha with asyncpg/SQLAlchemy.

### 35. When would you deliberately choose MongoDB over Postgres in 2026? Defend it - JSONB exists.
Honest answer: Postgres is the default for most systems and JSONB covers a lot. Choose MongoDB when: the data is truly document-shaped and read/written as one aggregate with highly variable structure; you need built-in **horizontal sharding** and easy replica-set HA at large scale; very high write ingest with simple access patterns; change streams matter; or the team is already strong in it. JSONB weak spots: updating a big JSONB value rewrites the whole value, no native sharding (needs Citus), and tooling around document-style queries is less ergonomic. If your data is relational or you need multi-table transactions/joins, stay on Postgres.

### 36. MongoDB: what is a write concern and a read preference? What does `w:1` risk?
**Write concern** = how many nodes must acknowledge a write before it's reported successful (`w:1` primary only, `w:"majority"`, plus `j:true` for journaled). **Read preference** = which replica-set members serve reads (`primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest`) — secondary reads can be stale.
`w:1` risk: the primary acknowledges, then fails before replicating; a new primary is elected without that write and it's **rolled back** — acknowledged data lost. (Modern MongoDB defaults to `majority`.)

### 37. CosmosDB: what is an RU, and how do you design a partition key? What is a hot partition and how would you detect one?
**RU (Request Unit)** — the normalized cost currency for CPU/IO/memory of an operation; a 1 KB point read by id + partition key ≈ 1 RU; you provision RU/s (manual, autoscale) or go serverless.
**Partition key**: pick a property with **high cardinality**, even distribution of both storage and request volume, and that appears in most queries (so they hit one partition, not cross-partition fan-out). E.g. `tenantId` or `userId`, or hierarchical partition keys / synthetic keys.
**Hot partition**: one logical partition receives a disproportionate share of traffic (limit ~10,000 RU/s and 20 GB per logical partition) → 429s even though total provisioned RU is under-used. Detect via Azure Monitor/Insights: *Normalized RU Consumption* split by partition key range (one range at 100% while others are low) and 429 rates.

### 38. What's the difference between logical and physical replication in Postgres?
**Physical (streaming)**: ships WAL byte-for-byte; replica is an exact copy of the whole cluster, same major version, read-only. Used for HA/failover and read replicas.
**Logical**: decodes WAL into row-level changes (publish/subscribe per table); can replicate selected tables, between different major versions, into a writable target with different indexes/schema. Doesn't replicate DDL or sequences automatically. Used for zero-downtime major upgrades, migrations, CDC (e.g. Debezium).

### 39. Database migrations on a live table with 500M rows - how do you add a NOT NULL column with a default without locking?
On Postgres 11+, `ALTER TABLE t ADD COLUMN c type NOT NULL DEFAULT <constant>` is a metadata-only, near-instant change (non-volatile default). For anything not instant (e.g. volatile default, or older versions) do it in steps:
1. `ADD COLUMN c type` (nullable, no default) — instant.
2. Set the default for new rows.
3. **Backfill in small batches** (e.g. 10k rows by PK range, commit each) to avoid long locks/WAL spikes.
4. `ADD CONSTRAINT ... CHECK (c IS NOT NULL) NOT VALID`, then `VALIDATE CONSTRAINT` (only a light lock).
5. `SET NOT NULL` (PG12+ uses the validated check to skip the table scan), drop the check.
Always set `lock_timeout` so your DDL doesn't queue behind a long transaction and block everything behind it.

### 40. Explain a deadlock. How do you reproduce one deliberately and how do you fix it?
Two transactions each hold a lock the other needs → circular wait. Postgres detects it after `deadlock_timeout` (1s) and aborts one with error `40P01`.
Reproduce: open two psql sessions. A: `BEGIN; UPDATE acct SET x=1 WHERE id=1;` B: `BEGIN; UPDATE acct SET x=1 WHERE id=2;` A: `UPDATE ... WHERE id=2;` (blocks) B: `UPDATE ... WHERE id=1;` → deadlock.
Fix: always acquire locks in a **consistent order** (e.g. sort IDs), keep transactions short, lock rows upfront with `SELECT ... FOR UPDATE ORDER BY id`, and retry on deadlock errors.

### 41. pgVector: what index types does it offer, and what's the recall/latency tradeoff?
- **No index (exact)**: sequential scan, perfect recall, slow at scale.
- **IVFFlat**: clusters vectors into `lists`; at query time searches the nearest `probes` lists. Fast build, smaller; needs data present to build well; recall depends on `lists`/`probes`.
- **HNSW**: layered graph; better recall/speed tradeoff, no training step, but slower to build and more memory. Tune `m`, `ef_construction` (build) and `hnsw.ef_search` (query).
Tradeoff: raising `probes`/`ef_search` improves recall but increases latency. Watch out: ANN index + `WHERE` filter can return fewer results than `LIMIT` since filtering happens after the index scan (newer versions add iterative scans to help).

---

## D. CACHING

### 42. Redis vs Memcached - when is Memcached still the right answer?
Memcached: simple, multi-threaded in-memory string key/value cache, very memory-efficient for simple objects, scales across cores trivially. Redis: rich data structures, persistence, replication, pub/sub, Lua, cluster. Memcached is still right when you need a **pure, simple, large cache** with no persistence or data structures and want multi-core throughput with minimal operational complexity (or you already run it). Otherwise Redis usually wins.

### 43. Redis data structures beyond strings - name five and a real use case for each.
- **Hash** — object/session fields (`HSET user:1 name ...`).
- **List** — simple queues, recent-activity feeds.
- **Set** — unique members: tags, who's online, dedupe.
- **Sorted set** — leaderboards, sliding-window rate limiters, delayed-job queues (score = timestamp).
- **Stream** — durable event log with consumer groups.
- Also: **Bitmap/HyperLogLog** (daily active user counts), **Geo** (nearby search), **Pub/Sub**.

### 44. Cache-aside vs write-through vs write-behind. Which did you use and why?
- **Cache-aside (lazy loading)**: app checks cache; on miss reads DB and fills cache. Most common; simple; risk of stale data and a cold-start miss penalty.
- **Write-through**: writes go to cache and DB synchronously; cache always fresh; higher write latency; caches data that may never be read.
- **Write-behind**: write to cache, flush to DB asynchronously; fastest writes but risk of data loss and complexity.
**Your story:** almost certainly cache-aside — explain TTLs and how you handled invalidation.

### 45. What is a cache stampede / thundering herd, and three ways to prevent it?
A hot key expires and many concurrent requests all miss at once and hammer the DB to recompute it. Prevention: (1) **single-flight / lock** — only one request recomputes (e.g. `SET lock NX`), others wait or serve stale; (2) **TTL jitter** — randomise expiry so keys don't expire together; (3) **stale-while-revalidate / early (probabilistic) refresh** — refresh before expiry in the background; also pre-warming and negative caching for missing keys.

### 46. Redis eviction policies - what does allkeys-lru vs volatile-ttl mean and how do you choose?
Eviction applies when `maxmemory` is reached. **allkeys-lru** evicts the least-recently-used key from *all* keys — right for a pure cache. **volatile-ttl** only considers keys that have an expiry and evicts those with the shortest remaining TTL. Other options: `allkeys-lfu` (least frequently used), `volatile-lru`, `random` variants, and `noeviction` (writes error out — default).
Choose: pure cache → `allkeys-lru`/`lfu`. Mixed instance where some keys must never be evicted (locks, queues, config) → a `volatile-*` policy and only put TTLs on cache keys. Note: if no keys have TTLs, `volatile-*` behaves like `noeviction`.

### 47. Is Redis single-threaded? What does that imply for a `KEYS *` command in prod?
Command execution is single-threaded (I/O can be threaded since Redis 6, but commands still run one at a time). So one slow command blocks **every** client. `KEYS *` is O(N) over the whole keyspace → blocks Redis for the entire scan, causing latency spikes or an outage on a big dataset. Use `SCAN` (cursor-based, incremental), and disable/rename `KEYS` in prod via ACLs.

### 48. How would you implement a distributed lock in Redis? What is Redlock and why is it controversial?
Basic lock: `SET lock:resource <random-token> NX PX 30000` — set only if absent, with an expiry so a crashed holder doesn't hold it forever. Release with a Lua script that deletes only if the stored token matches yours (so you never delete someone else's lock after yours expired).
Problem: if your work outlives the TTL (GC pause, slow call), the lock expires and two holders run concurrently. Mitigations: renew the lock (watchdog), and use a **fencing token** that the protected resource checks.
**Redlock** acquires the lock on a majority of N independent Redis nodes. It's controversial (Martin Kleppmann's critique) because it relies on timing assumptions (bounded clock drift, pauses, network delay) and has no fencing token, so it isn't safe for strict correctness. Fine for efficiency locks ("avoid doing the work twice"); for correctness use a DB lock/ZooKeeper/etcd with fencing, or make the operation idempotent.
**Your story:** go deep on your Turing Redis lock: what it protected, TTL, what happened on expiry.

### 49. Redis persistence: RDB vs AOF. What do you lose in a crash with each?
**RDB**: periodic point-in-time snapshots (fork + dump). Compact, fast restart. A crash loses everything since the last snapshot (minutes).
**AOF**: appends every write to a log. With `appendfsync always` you lose ~nothing (slow); `everysec` (recommended) loses up to ~1 second; `no` lets the OS decide. Bigger files, needs rewrites. Often both are enabled. If Redis is purely a cache, you may use neither.

### 50. How do you invalidate cache across multiple services? What is the hardest part?
Options: short TTLs; the owning service deletes/updates the key on write; **event-driven invalidation** (publish "entity changed" events via Pub/Sub/Kafka/CDC and each cache consumer evicts); versioned keys (bump a version/namespace to orphan old entries).
Hardest part: knowing *everything* that has cached a value derived from the changed data (dependency tracking), and **races** — a reader can repopulate the cache with stale data just after invalidation. Plus partial failures and unclear ownership across teams. This is the "two hard things in computer science" problem.

---

## E. MESSAGING

### 51. Kafka vs RabbitMQ in one minute. What is fundamentally different about the model?
**Kafka** is a distributed, partitioned, append-only **log**: messages are retained for a set period regardless of consumption; consumers pull and track their own offsets; many independent consumer groups can read and **replay** the same data; huge throughput; ordering per partition.
**RabbitMQ** is a **smart broker with queues**: the broker routes messages (exchanges) into queues, pushes them to consumers, and deletes them once acknowledged; flexible routing, per-message acks/priorities, lower throughput, no natural replay. Rule of thumb: Kafka for event streaming/log/replay at scale; RabbitMQ for task queues and complex routing.

### 52. Kafka: partition, offset, consumer group, rebalance - explain each and what triggers a rebalance storm.
- **Partition**: a topic is split into partitions — each an ordered log; the unit of parallelism and ordering.
- **Offset**: a message's sequential position within a partition; consumers commit offsets to record progress.
- **Consumer group**: consumers sharing a topic; each partition is assigned to exactly one consumer in the group (different groups each get everything).
- **Rebalance**: redistributing partitions across group members. Triggered by consumers joining/leaving/crashing, missed heartbeats (`session.timeout.ms`), exceeding `max.poll.interval.ms`, or partition changes.
**Storm**: slow processing exceeds `max.poll.interval.ms` → consumer kicked → rebalance → (eager protocol stops everyone) → partitions reprocessed → even more lag → more timeouts. Also rolling deploys of many consumers. Fixes: cooperative-sticky assignor, static membership (`group.instance.id`), smaller `max.poll.records`, larger `max.poll.interval.ms`, faster processing.

### 53. How do you guarantee ordering in Kafka? What does that cost you in parallelism?
Ordering is guaranteed only **within a partition**. Use a message **key** (e.g. `user_id`/`order_id`) so all events for an entity hash to the same partition. Producer: enable idempotence (and keep in-flight requests ≤5) so retries don't reorder. Cost: parallelism is capped at the number of partitions (one consumer per partition per group), hot keys create skewed partitions, and global ordering means a single partition.

### 54. At-most-once / at-least-once / exactly-once - which is real, which is a marketing term, and how do you achieve effective exactly-once?
- **At-most-once**: commit/ack before processing; may lose messages, never duplicates.
- **At-least-once**: process, then commit/ack; never loses, may duplicate. The practical default.
- **Exactly-once**: across arbitrary systems you can't truly have it (a crash between side effect and ack is unavoidable). Kafka offers exactly-once *within Kafka* (idempotent producer + transactions + `read_committed`) for consume-transform-produce.
**Effective exactly-once** = at-least-once delivery + **idempotent processing**: dedupe by message ID, unique constraints/upserts, idempotency keys downstream, or outbox/inbox patterns.

### 55. RabbitMQ: exchange types (direct, topic, fanout, headers) - one use case each.
- **Direct**: route on exact routing-key match — send tasks to a specific queue (e.g. `pdf` vs `email` workers).
- **Topic**: routing key with wildcards (`order.*.failed`, `logs.#`) — subscribe to categories of events.
- **Fanout**: broadcast to all bound queues, ignoring the key — notifications/cache-invalidation to every instance.
- **Headers**: route on message header attributes instead of the key — multi-attribute matching.

### 56. What is a dead letter queue and what do you do with the messages in it?
A DLQ holds messages that couldn't be processed successfully — exceeded max retries, rejected without requeue, expired (TTL), or queue overflow. Don't let it become a black hole: alert on its depth, inspect the messages and error metadata to find the root cause (bad payload vs bug vs downstream outage), fix it, then **redrive/replay** them to the main queue (or archive/discard deliberately).

### 57. SQS standard vs FIFO. What is the visibility timeout and what breaks if it's too short?
**Standard**: near-unlimited throughput, at-least-once, best-effort ordering. **FIFO**: strict ordering per message group, exactly-once processing via a 5-minute deduplication window, lower throughput limits (higher with batching/high-throughput mode).
**Visibility timeout**: after a consumer receives a message, it's hidden from others for N seconds (default 30) while it processes and deletes it. If the timeout is too short, the message reappears before processing finishes → another consumer processes it → **duplicates** (and possibly an endless duplicate loop). Set it above your max processing time, or extend it with `ChangeMessageVisibility` heartbeats.

### 58. SNS + SQS fan-out pattern - draw it and say why you'd use it over SNS alone.
```
                       ┌──> SQS queue A ──> Consumer A (own retries + DLQ)
Producer ──> SNS topic ├──> SQS queue B ──> Consumer B
                       └──> SQS queue C ──> Consumer C
```
SNS alone pushes to endpoints with limited retries — if a consumer is down or slow, messages can be lost. With a queue per subscriber you get **durable buffering**, **independent retry/backoff/DLQ** per consumer, load smoothing, and you can add consumers without touching the publisher. Per-subscription filter policies let each queue receive only what it needs.

### 59. GCP Pub/Sub: push vs pull subscriptions. When is push a trap?
**Pull**: subscribers fetch messages; you control rate, batching and flow control. **Push**: Pub/Sub POSTs each message to an HTTPS endpoint; simple, ideal for serverless (Cloud Run/Functions).
Push is a trap when: you need to control throughput (a burst floods your service; you're at the mercy of the push rate), the endpoint must be public HTTPS and authenticated, it must return 2xx within the ack deadline or the message is redelivered (duplicates), slow cold starts/timeouts cause retry storms, and high-throughput/ordered workloads suit pull better.

### 60. Consumer is slower than producer. Walk me through your options, in order.
1. **Measure** — is lag growing steadily (capacity gap) or just bursty? Where's the time going?
2. **Optimise the consumer** — batch DB writes, remove slow synchronous calls, fix the downstream bottleneck.
3. **Scale out consumers** (autoscale on lag) — bounded by partition count in Kafka, so add partitions if needed.
4. **Let the queue absorb bursts** — ensure retention/size is enough.
5. **Backpressure / shed load** — rate limit or throttle producers, drop/sample low-priority messages, prioritise queues.
6. Check for poison messages blocking progress, and fix the true bottleneck (often the database), not just the consumer count.

---

## F. CONTAINERS & ORCHESTRATION

### 61. What is a container, actually? Namespaces and cgroups - what does each provide?
A container is just a normal Linux process (tree) with isolation and limits — not a VM, it shares the host kernel. **Namespaces** control *what it can see* (PID, network, mount/filesystem, hostname/UTS, IPC, user, cgroup). **cgroups** control *what it can use* (CPU, memory, I/O, number of processes). Image layers (union filesystem) provide the filesystem; seccomp/capabilities restrict syscalls and privileges.

### 62. Image layers - how do you cut a 1.2GB Python image down? Multi-stage build for a FastAPI app - walk me through it.
Cut size: use `python:3.x-slim` (alpine often causes musl/wheel pain), **multi-stage** build, `pip install --no-cache-dir`, no build tools in the final image, clean apt lists in the same `RUN`, a good `.dockerignore`, install only runtime deps, and copy `requirements.txt` first to leverage layer caching.
```dockerfile
FROM python:3.12 AS builder
WORKDIR /app
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /venv /venv
COPY ./app ./app
ENV PATH="/venv/bin:$PATH"
RUN useradd -m app && chown -R app /app
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
The builder stage (with compilers) is discarded; only the venv and code reach the final image.

### 63. `CMD` vs `ENTRYPOINT`. `COPY` vs `ADD`. Why does `.dockerignore` matter?
`ENTRYPOINT` = the fixed executable; `CMD` = default arguments (or default command), overridden by `docker run <args>`. Common combo: `ENTRYPOINT ["uvicorn"]`, `CMD ["app:app"]`. Use **exec form** (JSON array) so the process is PID 1 and receives signals.
`COPY` just copies files; `ADD` also auto-extracts local tarballs and fetches URLs — prefer `COPY` for predictability.
`.dockerignore` keeps `.git`, `venv`, `__pycache__`, `.env`, etc. out of the build context: faster builds, smaller images, no secret leakage, and better layer caching.

### 64. Why should a container run as non-root, and what's the minimal change to do it?
If an attacker breaks out of the app or container, root inside the container makes escalation to the host far easier (and root-owned mounted volumes are writable). Many clusters enforce non-root (`runAsNonRoot`). Minimal change: create a user (`RUN useradd -m app`), `chown` the app dir, `USER app`, and listen on a port >1024. In K8s add `securityContext: runAsNonRoot: true, runAsUser: 1000, readOnlyRootFilesystem: true`.

### 65. K8s: Pod, ReplicaSet, Deployment, Service, Ingress - describe the chain in one pass.
A **Pod** is the smallest unit — one or more containers sharing network and storage. A **ReplicaSet** keeps N identical pods running. A **Deployment** manages ReplicaSets to give declarative rolling updates and rollbacks. A **Service** gives those pods a stable virtual IP/DNS name and load-balances across them by label selector. An **Ingress** (implemented by an ingress controller like nginx) routes external HTTP(S) traffic by host/path to Services and terminates TLS. Traffic: Client → Ingress → Service → Pod.

### 66. Liveness vs readiness vs startup probes. What happens if liveness is misconfigured on a slow-starting app?
- **Liveness**: "is it stuck?" — failure → kubelet **restarts** the container.
- **Readiness**: "can it take traffic?" — failure → removed from Service endpoints, **not** restarted.
- **Startup**: gives slow starters time; liveness/readiness are disabled until it succeeds.
Misconfigured liveness on a slow-starting app: the probe fails before the app finishes booting → container killed → restarts → fails again → **CrashLoopBackOff** forever. Fix with a `startupProbe` (or longer initial delay/failure threshold). Also: liveness shouldn't check dependencies (DB down → restart storm of healthy pods).

### 67. Requests vs limits. What is QoS class, and what gets OOMKilled first?
**Requests** = guaranteed minimum, used by the scheduler to place the pod. **Limits** = hard cap: exceeding CPU limit → throttled; exceeding memory limit → **OOMKilled**.
QoS classes: **Guaranteed** (requests == limits for every container, CPU and memory), **Burstable** (some requests/limits set), **BestEffort** (none). Under node memory pressure, eviction/OOM order is BestEffort first, then Burstable (most over their request first), Guaranteed last. A container exceeding its own memory limit is killed regardless of class.

### 68. HPA - what metrics can it scale on? How would you scale on Kafka consumer lag?
HPA scales replicas on **resource metrics** (CPU, memory via metrics-server), **custom metrics** (per-pod, e.g. requests/sec via Prometheus Adapter), and **external metrics** (outside the cluster, e.g. queue length). For Kafka lag: expose consumer-group lag as an external metric (Prometheus + adapter) or, more simply, use **KEDA's Kafka scaler**, which feeds an HPA with a target lag per replica. Cap max replicas at the partition count, since extra consumers beyond that sit idle. Formula: `desired = ceil(current × currentMetric / targetMetric)`.

### 69. What is a rolling update, and how do you do a zero-downtime deploy of a service that holds long-lived SSE/WebSocket connections?
A rolling update replaces pods gradually (`maxSurge`/`maxUnavailable`); new pods must pass readiness before old ones are removed.
For long-lived connections: on `SIGTERM` the app stops accepting new connections and tells clients to reconnect (close frame / SSE event); add a `preStop` sleep so endpoints deregister from the Service/ingress first; set a long enough `terminationGracePeriodSeconds`; clients auto-reconnect with jitter (avoid a thundering herd) and resume (e.g. SSE `Last-Event-ID`); keep session state outside the pod (Redis) so any pod can serve the reconnect; use a PodDisruptionBudget; and make sure ingress/proxy timeouts don't kill connections early.

### 70. ConfigMap vs Secret. Are K8s Secrets encrypted? What do you actually use in prod?
ConfigMap = non-sensitive config; Secret = sensitive values. Secrets are only **base64-encoded**, not encrypted — and sit unencrypted in etcd unless you enable encryption at rest; access is controlled by RBAC. In prod: keep real secrets in an external manager (Azure Key Vault / AWS Secrets Manager / HashiCorp Vault) and sync/mount them via the **Secrets Store CSI driver** or **External Secrets Operator**, authenticated with workload identity; enable etcd encryption; for GitOps use Sealed Secrets/SOPS.

### 71. StatefulSet vs Deployment - when did you need a StatefulSet?
Deployment: interchangeable stateless pods. StatefulSet gives each pod a **stable identity** (`app-0`, `app-1`), **stable per-pod persistent storage** (`volumeClaimTemplates`), and ordered start/stop. Needed for databases, Kafka, Elasticsearch, ZooKeeper, Redis clusters.
**Your story:** if you haven't needed one, say so — and that you'd normally use a managed service instead of running stateful systems on K8s.

### 72. Your pod is CrashLoopBackOff. Give me your exact debugging sequence of commands.
1. `kubectl get pods` — status, restart count.
2. `kubectl describe pod <pod>` — events and **Last State**: OOMKilled (exit 137), failed probes, image/config/secret errors, exit code.
3. `kubectl logs <pod>` and **`kubectl logs <pod> --previous`** (logs of the crashed instance); add `-c <container>` if multi-container.
4. `kubectl get events --sort-by=.lastTimestamp`.
5. Check config: env vars, mounted ConfigMaps/Secrets, resource limits, probe settings.
6. If still unclear: override the command with `sleep` or use `kubectl debug` / an ephemeral container and exec in to run the app by hand.
7. If it began after a deploy: `kubectl rollout undo deployment/<name>`.
Exit codes: 137 = OOM/SIGKILL, 1 = app error, 139 = segfault.

### 73. What is a sidecar? Name one you've deployed.
A second container in the same pod, sharing network and volumes, that extends the main app without changing it. Examples: service-mesh proxy (Envoy/Istio), log shipper (Fluent Bit), Cloud SQL Auth Proxy, Vault agent, OpenTelemetry collector. (K8s 1.29+ has native sidecar support.)
**Your story:** name the one you really ran.

### 74. Namespace, ResourceQuota, NetworkPolicy - which have you actually configured?
**Namespace**: logical partition for names, RBAC scoping and quotas. **ResourceQuota**: caps total resources/object counts in a namespace (pairs with **LimitRange** for per-container defaults). **NetworkPolicy**: pod-level firewall rules for ingress/egress; by default all pod traffic is allowed, so you apply default-deny and then allow specific flows (needs a CNI that enforces it — Calico, Cilium, etc.).
**Your story:** say honestly which ones you've actually written.

---

## G. CLOUD — AWS / AZURE / GCP

### 75. Map the equivalents across AWS/Azure/GCP.
| Concept | AWS | Azure | GCP |
|---|---|---|---|
| Object storage | S3 | Blob Storage | Cloud Storage |
| Managed Postgres | RDS / Aurora PostgreSQL | Azure Database for PostgreSQL (Flexible Server) | Cloud SQL / AlloyDB |
| Serverless functions | Lambda | Azure Functions | Cloud Functions / Cloud Run functions |
| Managed K8s | EKS | AKS | GKE |
| Message queue | SQS (+SNS) | Service Bus / Storage Queues | Pub/Sub (Cloud Tasks) |
| Secret store | Secrets Manager / SSM Parameter Store | Key Vault | Secret Manager |

### 76. IAM: role vs policy vs principal. What is an assumed role and why is it better than long-lived access keys?
**Principal** = who is making the request (user, role, service). **Policy** = JSON document stating allowed/denied actions on resources. **Role** = an identity with policies attached that has no permanent credentials and can be *assumed* by principals allowed in its trust policy.
**Assuming a role**: STS issues **temporary** credentials (access key + secret + session token, expiring in 1–12 hours). Better than long-lived keys: they expire automatically, nothing permanent to leak or commit, they're scoped, auditable per session (CloudTrail), and work cross-account. For workloads use instance profiles / IRSA / workload identity so there are no keys at all.

### 77. Azure: Managed Identity - system-assigned vs user-assigned. Where did you use it?
A Managed Identity is an Entra ID identity for an Azure resource whose credentials Azure manages — your code gets a token from the platform (`DefaultAzureCredential`) and calls Key Vault/Storage/SQL with no secrets.
**System-assigned**: created with and bound to one resource; deleted with it; 1:1. **User-assigned**: a standalone resource you attach to many resources; lifecycle independent; you can pre-grant RBAC before the app exists, and it survives resource recreation. Use system-assigned for a simple single resource, user-assigned when sharing across multiple resources or when IaC needs to assign roles in advance.
**Your story:** say what resource used it and what it accessed.

### 78. S3 storage classes and lifecycle policies - how would you cut a storage bill 70%?
Classes: Standard, Intelligent-Tiering, Standard-IA, One Zone-IA, Glacier Instant Retrieval, Glacier Flexible Retrieval, Glacier Deep Archive. **Lifecycle policies** automatically transition objects by age and expire them.
Approach: analyse access patterns first (Storage Lens / Storage Class Analysis); move cold data to IA/Glacier tiers (or Intelligent-Tiering when access is unknown); expire old objects and **noncurrent versions**; abort incomplete multipart uploads; delete duplicates/temp/log data; compress or convert to columnar formats (Parquet). Watch the catches: retrieval fees, minimum storage durations, minimum object sizes (e.g. 128 KB for IA), per-object transition costs for millions of tiny files.

### 79. VPC basics: public vs private subnet, NAT gateway, security group vs NACL.
**Public subnet**: route table has a route to an Internet Gateway; resources can have public IPs. **Private subnet**: no direct internet route; outbound-only via a **NAT gateway** (which lives in a public subnet), no inbound from the internet. NAT gateways cost hourly plus per-GB — a classic bill surprise; use VPC endpoints for AWS services to avoid it.
**Security group**: stateful, attached to the instance/ENI, allow rules only. **NACL**: stateless, attached to the subnet, allow and deny rules, evaluated in numbered order, and must explicitly allow return traffic.

### 80. Lambda: cold start, concurrency limits, 15-min ceiling, /tmp size. Which of these bit you on the McKinsey OHI project?
- **Cold start**: first invocation in a new execution environment pays init time (bigger for large packages/VPC/heavy imports). Mitigate: provisioned concurrency, smaller packages, lazy imports, SnapStart where available.
- **Concurrency**: default ~1000 concurrent executions per region per account; reserved/provisioned concurrency; excess is throttled (429).
- **15-minute max timeout** → long jobs must be chunked or moved to Step Functions/Batch/containers.
- **/tmp**: 512 MB by default, configurable up to 10 GB. Also: 6 MB sync payload limit.
**Your story:** be honest which one actually hit you (large file processing → /tmp or timeout is a common one).

### 81. Azure Functions: consumption vs premium vs dedicated plan. Which did you use at Aventum and why?
- **Consumption**: scale to zero, pay per execution, cold starts, short max timeout (5 min default/10 max), limited networking.
- **Flex Consumption** (newer): pay-per-use with optional always-ready instances and VNet support.
- **Premium (Elastic)**: pre-warmed instances (no cold start), VNet integration, longer runtime, pay for the always-on baseline.
- **Dedicated (App Service plan)**: fixed VMs, always on, predictable cost, good if you have spare App Service capacity.
**Your story:** say which plan and the real reason (cold start, VNet access, timeout, cost).

### 82. Azure Blob: what are access tiers, SAS tokens, and how do you do secure upload from a browser without proxying through your API?
**Tiers**: Hot (frequent access), Cool (≥30 days), Cold (≥90 days), Archive (≥180 days, offline — rehydration takes hours). Cooler tiers = cheaper storage, costlier access.
**SAS (Shared Access Signature)**: a signed URL granting scoped, time-limited permissions (blob/container, read/write, expiry, IP) without sharing account keys. Prefer **user-delegation SAS** (signed with Entra ID credentials).
**Browser upload**: the browser calls your API (authenticated); the API generates a short-lived (~5–15 min) SAS with create/write-only permission for one specific blob name and returns the URL; the browser PUTs the file straight to Blob Storage (block upload for large files; configure CORS on the storage account). Then process via a Blob-created Event Grid event or a callback. Validate size/type server-side and scan if needed.

### 83. Azure AI Search indexers - what is an indexer, a skillset, and a data source? What are the failure modes?
**Data source**: connection to where the data lives (Blob, SQL, Cosmos DB). **Indexer**: the crawler that pulls from the data source on a schedule, with change tracking, and maps fields into the search index. **Skillset**: an AI enrichment pipeline between extraction and indexing — OCR, text splitting/chunking, entity extraction, embeddings, custom web-API skills.
Failure modes: documents too large/unsupported formats; skill timeouts and throttling (429s from Azure OpenAI/AI services); indexer run-time limits; hitting `maxFailedItems`; field-mapping/schema mismatches; network/credential/firewall issues to the source; deletions not propagating without a deletion-detection policy; needing a reset/re-run after changing the skillset; enrichment costs.

### 84. What is the difference between an Application Gateway, a Load Balancer, and Front Door in Azure?
- **Azure Load Balancer**: Layer 4 (TCP/UDP), regional, very fast, no HTTP awareness.
- **Application Gateway**: Layer 7 regional HTTP load balancer — URL/host routing, TLS termination, cookie affinity, optional WAF.
- **Front Door**: **global** Layer 7 entry point — anycast edge network, CDN, WAF, global load balancing and failover across regions.
(Traffic Manager is DNS-based routing.)

### 85. Cloud cost: name the three biggest surprise line items you've personally seen on a bill and what caused them.
Common culprits: NAT gateway/data-transfer charges (cross-AZ, cross-region, egress); log/metric ingestion (CloudWatch, Log Analytics, App Insights) from verbose debug logs; forgotten dev/test resources (idle VMs, GPUs, clusters, unattached disks); over-provisioned databases (Cosmos RUs, oversized RDS); LLM/API token usage; AI Search replicas; S3 request and early-deletion charges.
**Your story:** use three real ones — don't invent them.

### 86. How do you handle secrets in cloud? Key Vault / Secrets Manager / SSM Parameter Store - rotation strategy?
Never in code, git, images or plain env files. Store in Key Vault / Secrets Manager / SSM Parameter Store (SecureString — cheaper but no built-in rotation), and have apps read them at startup or with a short cache using a managed identity/IAM role. Prefer passwordless/short-lived credentials (managed identity, IAM DB auth) so there's nothing to rotate.
Rotation: automate it (Secrets Manager rotation Lambdas for RDS; Key Vault rotation policies + Event Grid near-expiry events); use a **two-credential/alternating-user** strategy so old and new work during the switchover (zero downtime); apps must re-fetch rather than cache forever; audit access.

---

## H. DEVOPS / CI-CD / IaC

### 87. Terraform: what is state, why is remote state necessary, and what is state locking?
State is Terraform's record mapping your config to the real resources it created (IDs, attributes). Terraform diffs config vs state vs reality to build a plan. It can contain secrets, so protect it.
**Remote state** (S3, Azure Blob, GCS, Terraform Cloud) is needed so the team and CI share one source of truth rather than a file on a laptop; it also gives encryption, versioning and backup. **State locking** prevents two applies running at once and corrupting state (S3 + DynamoDB or S3 native lockfile, Azure Blob lease, etc.). If a lock gets stuck: `terraform force-unlock` — carefully.

### 88. `terraform plan` shows a destroy you did not expect. What do you do?
**Don't apply.** Find out why: read the plan for `# forces replacement` (an immutable attribute changed); a resource was renamed/moved (use `moved` blocks or `terraform state mv`); a `count`/`for_each` index shifted; a provider upgrade changed defaults; someone changed the resource manually (drift); wrong workspace/state/backend. Compare with `git diff`, inspect state with `terraform state show`. Protect critical resources with `lifecycle { prevent_destroy = true }`, use `import`/`moved` to reconcile, get review, test in a lower environment, and keep a state backup.

### 89. Module vs workspace vs environment folders - how did you structure multi-region on the McKinsey project?
- **Module**: reusable packaged config with inputs/outputs (a VPC, an AKS cluster).
- **Workspace**: multiple state files from the *same* config in one backend — lightweight, but easy to apply to the wrong one, and not great for envs with different config/permissions.
- **Environment folders** (`envs/dev`, `envs/prod`): each with its own backend/state and `tfvars`, calling shared modules — clearer isolation and blast radius.
Multi-region typically: shared modules, one instantiation per region (provider aliases/separate state per region+env).
**Your story:** describe what you actually built on that project.

### 90. What is drift, and how do you detect and prevent it?
Drift = real infrastructure no longer matches your code/state (manual console edits, other automation). Detect: scheduled `terraform plan -detailed-exitcode` (exit code 2 = changes) in CI with alerting, cloud tools (AWS Config, Azure Policy), Terraform Cloud drift detection. Prevent: make console access read-only, push all changes through the pipeline, policy-as-code, and `ignore_changes` only for fields intentionally managed elsewhere.

### 91. Terraform vs Bicep vs ARM vs CloudFormation vs Pulumi - which have you used, and when is Terraform the wrong tool?
Terraform: multi-cloud, huge provider ecosystem, HCL, explicit state. **Bicep**: Azure-only, compiles to ARM, no state file, day-one support for new Azure features. **ARM**: verbose JSON underlying Azure. **CloudFormation**: AWS-only, managed stacks. **Pulumi**: real languages (Python/TS) + state.
Terraform is the wrong tool when: you're Azure-only and want day-one features and no state management (Bicep); AWS-only with deep CFN/CDK integration; you need real programming-language logic (Pulumi/CDK); or for application deployment (Helm/ArgoCD rather than Terraform). Licensing change (BSL, 2023) also spawned the OpenTofu fork.
**Your story:** state which you really used.

### 92. Design a CI/CD pipeline for a Python FastAPI service on AKS. Stages, gates, and what runs on PR vs on main.
**On PR** (fast feedback, no deploy): lint/format (ruff, black), type-check (mypy), unit tests + coverage threshold, dependency & SAST scans (pip-audit, bandit), build the Docker image (don't push or push to a temp tag), Dockerfile/IaC validation (`terraform validate/plan`, `helm lint`).
**On merge to main**: build once, tag with the **git SHA**, scan the image (Trivy), generate SBOM, push to ACR, (sign) → auto-deploy to dev (Helm/ArgoCD) → run DB migration step → integration/smoke tests → manual approval gate → staging → prod (rolling or canary) → post-deploy health checks and automatic rollback on failure.
Gates: tests green, coverage, no critical CVEs, approvals for prod, change windows.

### 93. Blue/green vs canary vs rolling. Which have you actually run, and how did you decide rollback?
- **Rolling**: replace instances gradually; default, cheap; both versions run side-by-side during rollout.
- **Blue/green**: two full environments, flip traffic at once; instant rollback; double the cost and DB compatibility concerns.
- **Canary**: send a small % (1→5→25→100) to the new version while watching error rate/latency; safest, slowest (Argo Rollouts/Flagger automate it).
Rollback decision should be pre-defined and metric-based (error rate, p99, saturation vs thresholds over a bake window), ideally automated.
**Your story:** say which you ran and what triggered rollback.

### 94. How do you manage DB migrations in a CD pipeline where deploys are automatic?
Run migrations as a **separate, single step** before the new app version rolls out (a pipeline stage, K8s Job, or Helm pre-upgrade hook) — not on app startup where 5 replicas race. Migrations must be **backward-compatible** (expand/contract): during a rolling deploy old code runs against the new schema. So: expand (add nullable column) → deploy code → backfill → contract (drop old column) in a later release. Use `lock_timeout`, test against production-sized data, and prefer forward-fix migrations over automated downgrades in prod.

### 95. What do you do about a flaky test in CI? Be specific.
Don't just retry-and-forget. (1) **Detect/track** — record failure rates per test. (2) **Quarantine** — move it to a non-blocking job with a ticket, owner and deadline so it doesn't block everyone. (3) **Root-cause**: order dependence/shared state (run with random order, isolate DB per test), time dependence (freeze time), race conditions/`sleep()` (wait on conditions with timeouts), external network (mock), resource limits in CI, port collisions, unseeded randomness. (4) Fix, then un-quarantine. Auto-retry (`pytest-rerunfailures`) only as a visible, temporary measure.

### 96. Nginx: reverse proxy vs load balancer. What is `proxy_buffering` and why does it break SSE?
A **reverse proxy** sits in front of backends on behalf of clients: forwards requests, terminates TLS, caches, compresses, routes. A **load balancer** distributes traffic across multiple backends (`upstream` with round-robin, `least_conn`, `ip_hash`). Nginx does both.
`proxy_buffering on` (default) makes Nginx collect the backend response into buffers before sending it on. For SSE that means events sit in the buffer and the client sees nothing or delayed bursts. Fix: `proxy_buffering off;` for that location (or the app sends `X-Accel-Buffering: no`), plus `proxy_http_version 1.1; proxy_set_header Connection "";`, a long `proxy_read_timeout`, and `gzip off` for the stream.

### 97. Branching strategy - trunk-based vs gitflow. What did you use and would you change it?
**Trunk-based**: short-lived branches (≤1–2 days) merged to `main` frequently, behind feature flags, backed by strong CI — enables continuous delivery, fewer merge conflicts. **Gitflow**: long-lived `develop`/`release`/`hotfix` branches — suits scheduled, versioned releases but brings heavy merges and slower delivery. Modern preference is trunk-based + feature flags.
**Your story:** say what your team used and what you'd change.

### 98. How do you version and promote a Docker image from dev to prod? Tag strategy?
**Build once, promote the same immutable artifact.** Tag with the git SHA (traceable) and a semver for releases; never rely on `latest`. Promotion = deploying the same image **digest** (`sha256:...`) to the next environment (or retagging/importing it between registries), with environment-specific config injected at deploy time (env vars, ConfigMaps, Helm values) — never rebuild per environment. Scan and sign before promotion; make tags immutable in the registry.

### 99. What is supply chain security in CI - SBOM, image scanning, signed images. Have you done any of it?
- **SBOM**: a Software Bill of Materials — inventory of all components/dependencies in an artifact (Syft, CycloneDX/SPDX), so you can quickly find what's affected by a new CVE.
- **Image scanning**: Trivy/Grype/Defender for Containers scan for known vulnerabilities in CI and in the registry.
- **Signed images**: sign with cosign/Sigstore and enforce signature verification at admission (Kyverno/Gatekeeper) so only trusted-built images run.
Also: pin dependencies with hashes, Dependabot/`pip-audit`, minimal base images, provenance attestations (SLSA), protect CI secrets.
**Your story:** state exactly which of these you've really done (e.g. only image scanning).

---

## I. MONITORING / OBSERVABILITY

### 100. Metrics vs logs vs traces - what question does each answer?
**Metrics**: numeric aggregates over time — "Is something wrong, how bad, what's the trend?" (alerts/dashboards; cheap). **Logs**: discrete events with context — "What exactly happened?" **Traces**: one request's journey across services with timings — "Where did the time go / which service failed?" Metrics detect, traces locate, logs explain.

### 101. Prometheus: pull model - why? What is a counter vs gauge vs histogram vs summary?
Pull (Prometheus scrapes `/metrics`): Prometheus controls scrape rate and load, instantly knows when a target is down (`up == 0`), targets stay simple, you can debug with `curl`, and service discovery finds targets. Push (Pushgateway) is only for short-lived batch jobs.
- **Counter**: only goes up (resets on restart) — requests_total; use `rate()`.
- **Gauge**: goes up and down — memory used, queue depth.
- **Histogram**: counts observations into configurable buckets (+ `_sum`, `_count`); aggregatable across instances; quantiles computed at query time.
- **Summary**: quantiles computed client-side; accurate but can't be aggregated across instances.

### 102. Why is averaging a latency metric a bad idea? How do you get a real p99 from a histogram, and what is the error in `histogram_quantile`?
Averages hide the tail: 99 fast requests and 1 timeout looks fine on average, while real users suffer; latency distributions are skewed. And you can't average percentiles across instances either.
p99: `histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))`. The error: it **linearly interpolates inside the bucket** where the quantile falls, so accuracy depends on bucket boundaries — if p99 lands in a 1s–5s bucket the estimate could be anywhere in that range. Choose buckets around your SLO thresholds (native histograms improve this).

### 103. What is cardinality explosion in Prometheus? Give an example label that caused it.
Each unique combination of label values is a separate time series, costing memory and storage. Unbounded labels explode the count: `user_id`, `request_id`/`trace_id`, full URL path with IDs (`/users/12345`), email, client IP, error message text, churning pod names. Use bounded labels (route *template* `/users/{id}`), push high-cardinality detail into logs/traces, and watch `prometheus_tsdb_head_series`; use relabeling/sample limits as guardrails.

### 104. What are the four golden signals / RED / USE methods?
- **Four golden signals** (Google SRE): latency, traffic, errors, saturation.
- **RED** (request-driven services): Rate, Errors, Duration.
- **USE** (resources like CPU, disk, network): Utilization, Saturation, Errors.
RED for services, USE for infrastructure.

### 105. What is an SLI, SLO and error budget? Did you ever have one defined?
**SLI**: a measured indicator (e.g. % of requests that succeed in <300 ms). **SLO**: the target for it over a window (99.9% over 30 days). **SLA**: a contractual promise with penalties. **Error budget** = 100% − SLO (99.9% → ~43 min of allowed badness per 30 days). It balances feature velocity vs reliability: budget burned → slow releases and prioritise reliability. Alert on **burn rate**.
**Your story:** be honest if none was formally defined; say what you tracked informally.

### 106. Alert fatigue - how do you design an alert that's worth waking someone up for?
Page only on **user-impacting symptoms that need a human now** and are actionable, with a runbook — not on causes like "CPU > 80%". Base them on SLO **burn rate** (multi-window), use a `for:` duration to avoid flapping, separate severities (page vs ticket vs dashboard), group/dedupe in Alertmanager, assign owners, and prune noisy alerts regularly. Test: "If this fires at 3 AM, is there something a human must do right now?"

### 107. What is distributed tracing? Have you used OpenTelemetry? What is a span and trace context propagation?
Distributed tracing follows a single request across services. A **trace** is the whole journey (one trace ID); a **span** is one unit of work in it (name, start, duration, attributes, parent span ID, status). **Context propagation** passes the trace context across process boundaries — HTTP/gRPC headers (W3C `traceparent`) or message headers — so downstream spans join the same trace. **OpenTelemetry** is the vendor-neutral standard (API/SDK/Collector) with auto-instrumentation for FastAPI, requests, SQLAlchemy, Celery; export via OTLP to Jaeger/Tempo/Azure Monitor. Sampling (head vs tail) controls cost.
**Your story:** say whether you've actually instrumented anything.

### 108. EFK stack - what does each letter do, and what's the cost problem with it at scale?
**E**lasticsearch stores and indexes logs; **F**luentd (or Fluent Bit) collects, parses and ships them; **K**ibana is the search/visualisation UI.
Cost problem: Elasticsearch indexes everything (storage can be 1.5–3× raw log size), is heap/RAM hungry, needs shard/cluster management, and verbose logs at scale get expensive. Mitigate: index lifecycle management (hot/warm/cold), drop debug logs, structured logs with fewer fields, shorter retention, archive to object storage; consider Loki (label-only indexing) as a cheaper alternative.

---

## J. SCHEDULING / BACKGROUND WORK

### 109. Celery: broker vs result backend. Why is Redis a questionable broker choice?
The **broker** transports task messages from producers to workers (RabbitMQ, Redis, SQS). The **result backend** stores task states/return values (Redis, DB).
Redis as broker is questionable because it isn't a true durable message broker: data can be lost on crash/failover (async replication), it's memory-bound (a big backlog eats RAM), it lacks native ack/redelivery semantics so Celery emulates it with a **visibility timeout** (long/ETA tasks get redelivered and run twice), and routing/priority features are weaker. RabbitMQ gives real acks, durable queues and DLX. Redis is fine for small/simple workloads.

### 110. Celery `acks_late`, `prefetch_multiplier`, visibility timeout - what do they do and what bug do you get if you set them wrong?
- **`acks_late=True`**: ack after the task finishes (default is before it starts). If a worker dies mid-task the task is redelivered — at-least-once — so tasks must be **idempotent**. Default early ack = task lost on crash.
- **`worker_prefetch_multiplier`**: how many tasks each worker process reserves ahead (default 4). With long tasks, items sit prefetched on a busy worker while others idle → latency imbalance; set to 1 for long tasks.
- **Visibility timeout** (Redis/SQS broker): how long an unacked task stays hidden before redelivery. If a task (or ETA/countdown) outlasts it, the task is redelivered and runs **twice, repeatedly**.
Wrong combos: `acks_late` + non-idempotent task = duplicate side effects; short visibility timeout + long task = infinite duplicates; high prefetch + long tasks = starved workers.

### 111. A Celery task takes 3 hours. What's wrong with that and how do you restructure it?
A single 3-hour task is fragile: any worker restart/deploy kills it, visibility-timeout redelivery can double-run it, there's no progress visibility, it hogs a worker, and a failure at hour 2:59 means starting over. Restructure: split into many small **idempotent** chunks (fan-out with `group`/`chord`/chains, one task per batch/item); **checkpoint progress** in the DB so a retry resumes; dedicated queue and workers; set time limits; `acks_late` + idempotency; stream data rather than loading it all; or move orchestration to a workflow engine (Temporal/Airflow/Step Functions) for long-running pipelines. Example: bulk resume ingestion → one task per resume.

### 112. When would you use FastAPI BackgroundTasks vs Celery? What's the failure mode of BackgroundTasks?
BackgroundTasks: small, quick, fire-and-forget work after the response (send an email, write an audit log) that you can afford to lose. Celery: heavy, long, critical work needing durability, retries, scheduling, monitoring and independent scaling.
Failure mode of BackgroundTasks: runs in the **same process** — if the pod restarts/deploys/crashes, pending tasks vanish; no retries, persistence or visibility; exceptions after the response are easy to miss; CPU-heavy or blocking work competes with request handling (and starves the event loop if it blocks in an `async` task).

### 113. APScheduler in a 5-replica deployment - what goes wrong, and how do you fix it?
Each replica runs its own scheduler, so every job fires **5 times** (duplicate emails, charges, reports). Fixes: run the scheduler as a **single dedicated instance** (separate deployment, replicas=1); or guard each job with a **distributed lock** (Redis `SET NX` or Postgres advisory lock) so one replica wins; or use K8s `CronJob` (`concurrencyPolicy: Forbid`) / Celery beat (single instance). And make the jobs idempotent as a safety net.

### 114. How do you make a scheduled job idempotent and safe to run twice?
Techniques: claim each run with a unique key (`job_name + scheduled_window`) using a unique constraint/`INSERT ... ON CONFLICT DO NOTHING`; use **upserts** instead of inserts; process by state (mark `processed_at` in the same transaction as the side effect; select with `FOR UPDATE SKIP LOCKED`); pass idempotency keys to downstream calls; use a high-water-mark checkpoint; add a lock to prevent overlapping runs; write outputs atomically (temp then rename).

### 115. How do you handle a poison-pill task that keeps failing and retrying forever?
Bound the retries (`max_retries`) with exponential backoff + jitter. Separate **retryable** errors (timeouts, 503s) from **non-retryable** ones (validation errors, bad payload) and don't retry the latter. After the limit, send it to a **DLQ** or mark it `failed` in a table with the error, alert on DLQ depth, and inspect/redrive after the fix. Add task time limits and a circuit breaker for failing downstreams. In Celery: `autoretry_for`, `retry_backoff`, `max_retries`, an `on_failure` handler.

---

## K. SECURITY & AUTH

### 116. OAuth2 vs OIDC - what does OIDC add? What is the difference between an access token and an ID token?
**OAuth2** is an *authorization* framework: it lets an app get an access token to call APIs on a user's behalf; it says nothing about who the user is. **OIDC** (OpenID Connect) is an *identity* layer on top: it adds the **ID token** (a JWT with claims like `sub`, `iss`, `aud`, `exp`, `nonce`, email), the `openid` scope, the UserInfo endpoint and a discovery document (`/.well-known/openid-configuration`).
**Access token**: for the API (resource server) — says what the bearer may access; the client should treat it as opaque. **ID token**: for the client app — proves the user authenticated; should *not* be sent to APIs as a bearer token.

### 117. Authorization code flow with PKCE - why is PKCE needed, and what attack does it stop?
In the auth code flow the user logs in at the IdP and is redirected back with an authorization **code**, which the app exchanges for tokens. Public clients (SPAs, mobile) can't keep a client secret, so an attacker who **intercepts the code** (malicious app on the same redirect scheme, referrer/history leakage) could exchange it.
**PKCE**: the client generates a random `code_verifier`, sends `code_challenge = BASE64URL(SHA256(verifier))` with the auth request, and presents the original verifier when exchanging the code. The server checks the hash matches. A thief with only the code can't redeem it. Now recommended for all clients (OAuth 2.1).

### 118. JWT: how do you revoke one? Where do you store it client-side and why is localStorage debated?
JWTs are stateless and valid until `exp`, so you can't truly revoke them. Options: **short-lived access tokens** (5–15 min) + revocable refresh tokens; a **denylist** of `jti`s in Redis until expiry; a per-user "tokens valid after" timestamp/version checked on each request; opaque tokens with introspection; rotating signing keys (nuclear).
Storage: `localStorage` is readable by any JS, so an XSS bug steals the token. `httpOnly; Secure; SameSite` cookies can't be read by JS (XSS can still *use* the session but not exfiltrate the token), but they need CSRF protection. A common compromise: access token in memory + refresh token in an httpOnly cookie, or a BFF (backend-for-frontend) pattern.

### 119. Refresh token rotation and reuse detection - explain.
**Rotation**: every time a refresh token is used, the server issues a new refresh token and invalidates the old one, so each is single-use. **Reuse detection**: if an already-used refresh token is presented again, that means someone has a stolen copy (either the thief or the legit client replaying an old one) — the server revokes the **entire token family** and forces re-login. This limits the damage window of a stolen refresh token. Edge case: legitimate network retries can look like reuse, so some servers allow a small grace window.

### 120. What is the difference between authentication, authorization, and RBAC vs ABAC?
**Authentication (authN)**: who are you? **Authorization (authZ)**: what are you allowed to do? **RBAC**: permissions are attached to roles and users get roles (admin/editor/viewer) — simple, but can suffer role explosion. **ABAC**: decisions are computed from attributes of the user, resource, action and environment ("user.department == doc.department AND time in business hours") — fine-grained and flexible but more complex (policy engines like OPA/Cedar). ReBAC (relationship-based, Zanzibar-style) is a third model.

### 121. Name five items from the OWASP Top 10 and how you'd defend against each in FastAPI.
(Based on the 2021 list; newer editions reshuffle slightly but these still apply.)
1. **Broken access control** — enforce authZ on every endpoint via dependencies, check object ownership (prevent IDOR), deny by default.
2. **Cryptographic failures** — TLS everywhere, hash passwords with argon2/bcrypt, encrypt sensitive data, no secrets in code.
3. **Injection** — parameterised queries/ORM, Pydantic validation, never `shell=True` with user input.
4. **Security misconfiguration** — disable debug and `/docs` in prod, strict CORS, security headers, least privilege.
5. **Vulnerable/outdated components** — `pip-audit`/Dependabot, pinned dependencies, image scanning.
Also: **Identification & auth failures** (rate-limit login, MFA, short-lived tokens), **SSRF** (see #123), **Logging & monitoring failures** (audit logs, alerts), **Insecure design** (threat modelling).

### 122. How do you prevent SQL injection when you genuinely need dynamic SQL?
Never concatenate user input into SQL. Values → always **bind parameters**. Identifiers (table/column names, `ORDER BY` direction) can't be parameterised, so **whitelist** them against a fixed allowed set/mapping, or quote them with a safe API (psycopg `sql.Identifier`, SQLAlchemy column objects after a whitelist check). Build dynamic filters with the SQLAlchemy Core/ORM expression builder rather than strings; use `= ANY(:ids)` for IN lists; and run the app with a least-privilege DB user.

### 123. What is SSRF and where would it show up in a system that fetches URLs (like a crawler)?
**Server-Side Request Forgery**: an attacker makes *your server* send a request to a destination they choose — typically internal-only targets: the cloud metadata endpoint (`169.254.169.254` → IAM credentials), internal services/admin panels, `localhost`, databases. It shows up anywhere a user supplies a URL: crawlers, webhooks, link previews, image/PDF fetchers, import-from-URL features.
Defences: allowlist domains where possible; resolve DNS and **block private/loopback/link-local ranges after resolution**, and pin the resolved IP (DNS rebinding); re-validate on every redirect (or disable redirects); only http/https and sane ports; run fetchers in an isolated network with egress restrictions; enforce IMDSv2; timeouts and size limits; don't return raw responses to the user.

### 124. How do you store and rotate secrets? What do you do when a key leaks into a git commit?
Store in a secrets manager and inject at runtime; rotate on a schedule and on demand; prefer short-lived/dynamic credentials.
Leaked key — assume it's compromised the moment it's pushed: (1) **revoke/rotate it immediately** (the most important step, before any cleanup); (2) check access logs for misuse; (3) remove it from history (`git filter-repo`/BFG) and force-push — but forks, clones and caches still have it, which is why rotation is the real fix; (4) add prevention: pre-commit secret scanning (gitleaks), GitHub push protection; (5) write up what happened.

### 125. PII handling - encryption at rest vs in transit vs field-level. What did SOC2 require of you at CES?
**At rest**: data on disk/backups encrypted (disk/TDE/storage-service encryption, keys in KMS/Key Vault) — protects against stolen disks/snapshots, not an app-level breach. **In transit**: TLS 1.2+ everywhere, including internal hops (mTLS where needed). **Field-level (application-level)**: encrypt specific sensitive fields (SSN, phone) before storing, with envelope encryption via KMS, so DBAs, backups and logs can't read them and you can crypto-shred; cost: harder to query/index (use deterministic encryption or a blind-index hash for lookups).
SOC2 typically asks for: least-privilege access and periodic access reviews, audit logging, change management (PR approvals, CI/CD controls), encryption, vulnerability management, incident response, backup/DR, vendor management, offboarding and evidence collection.
**Your story:** replace the generic list with what you personally implemented/evidenced at CES.

---

## L. NETWORKING / OS / GENERAL

### 126. What happens, end to end, when you type a URL and hit enter? Stop at TLS handshake.
1. Browser parses the URL, checks HSTS/caches/proxy settings.
2. **DNS resolution**: browser cache → OS cache/`hosts` → recursive resolver → root → TLD → authoritative server → IP address.
3. **TCP handshake** to port 443: SYN → SYN-ACK → ACK.
4. **TLS handshake** (1.3): ClientHello (supported ciphers + key share) → ServerHello + certificate + key share → client validates the cert chain (trusted CA, hostname, expiry) → both derive session keys → Finished. Then encrypted HTTP begins.

### 127. TCP vs UDP, and where does HTTP/2 and HTTP/3 change things?
**TCP**: connection-oriented, reliable, ordered, with congestion control and retransmits. **UDP**: connectionless, no delivery/order guarantees, low overhead (DNS, video, gaming, QUIC).
**HTTP/1.1**: one request in flight per connection → browsers open many connections. **HTTP/2**: multiplexes many streams over one TCP connection, binary framing, header compression (HPACK) — but one lost packet still stalls all streams (TCP-level head-of-line blocking). **HTTP/3**: runs over **QUIC (UDP)** — independent streams (loss only affects its own stream), built-in TLS 1.3, faster connection setup (1-RTT/0-RTT) and connection migration across networks.

### 128. What is head-of-line blocking and which protocol version fixed it?
HOL blocking: an item stuck at the front of a queue blocks everything behind it. In HTTP/1.1 it's at the application level (a request waits for the previous response on the connection). **HTTP/2** fixed the application-level problem via multiplexing, but TCP-level HOL remains (one lost packet blocks all streams). **HTTP/3 (QUIC)** fixed that too with independent streams over UDP.

### 129. Explain DNS records: A, CNAME, and why TTL matters during a migration.
**A** maps a name → IPv4 address (AAAA → IPv6). **CNAME** is an alias from one name to another name; it can't coexist with other records at the same name and isn't allowed at the zone apex (use ALIAS/ANAME). Others: MX (mail), TXT, NS.
**TTL** = how long resolvers/clients cache the answer. For a migration: lower the TTL (e.g. 60–300 s) *well before* cutover (at least one old-TTL period ahead), switch the record, then raise it again afterwards. Otherwise clients keep hitting the old IP for hours. Keep the old environment running during the overlap since some resolvers ignore low TTLs.

### 130. A process is at 100% CPU on a prod box. What Linux commands do you run, in order?
1. `top`/`htop` — find the PID; look at user vs system vs iowait and load average. (`uptime`, `vmstat 1` for run-queue/context switches.)
2. `ps aux --sort=-%cpu | head` / `pidstat 1` — confirm the culprit; `top -H -p <pid>` for per-thread view.
3. `strace -p <pid> -c` (or `-f`) — what syscalls is it making/spinning on?
4. `lsof -p <pid>` / `ss -tnp` — files/sockets involved.
5. `perf top -p <pid>` — where CPU time is going; for Python use **`py-spy top --pid <pid>`** / `py-spy dump` (non-invasive stack sampling).
6. Check `journalctl`/app logs/`dmesg`; decide if it's real load, a runaway loop, GC thrash or lock spinning.
Capture diagnostics (stack dump) **before** you restart; then mitigate (restart, scale out, rate limit).

### 131. What is a file descriptor limit and how have you hit it?
Every open file, socket and pipe uses a **file descriptor**. Each process has a limit (`ulimit -n`, often 1024 soft by default) and the system has a global one (`fs.file-max`). Hitting it gives `Too many open files` (EMFILE), typically from many concurrent connections (WebSocket/SSE servers, crawlers), leaked sockets/files, or DB connections not being pooled/closed.
Diagnose: `ls /proc/<pid>/fd | wc -l`, `lsof -p <pid> | wc -l`, `cat /proc/<pid>/limits`. Fix: fix the leak (context managers, reuse HTTP sessions), and raise the limit (`ulimit -n`, systemd `LimitNOFILE`, container `--ulimit nofile`).
**Your story:** tell the real incident if you have one.

### 132. What is the difference between a load balancer's L4 and L7 mode?
**L4** (transport layer): routes on IP + port (TCP/UDP) without looking at the payload — very fast, protocol-agnostic, TLS passthrough; balancing is per **connection**, so a single long-lived connection (gRPC/HTTP2/WebSocket) sticks to one backend and load can become uneven. **L7** (application layer): understands HTTP — terminates TLS, routes by host/path/headers/cookies, rewrites, does auth/WAF, retries, and balances per **request** (good for gRPC/HTTP2 multiplexing); costs more CPU and latency. AWS: NLB (L4) vs ALB (L7). Azure: Load Balancer (L4) vs Application Gateway (L7).

