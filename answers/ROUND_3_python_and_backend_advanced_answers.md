# Round 3 — Advanced Python & Backend: Answers

Companion to `questions/ROUND_3_python_and_backend_advanced.txt`. Same numbering. Short answer for direct questions, a paragraph (or a few) for design/scenario questions.

Where a question asks "have *you* done X / what did *you* use", I give the technical answer plus a note marked **Your story:**. You have to fill those in from real experience. Don't memorise my wording for them. For the Cellular / Aurora / Orbit questions (F, G), I give a strong reference design. Compare it against what you actually built and be ready to explain where yours differed and why.

---

## A. PYTHON RUNTIME & INTERNALS

### 1. Walk me through the MRO. What does C3 linearization solve, and when have you actually needed to reason about it?
MRO (Method Resolution Order) is the order Python searches classes when looking up an attribute: `Cls.__mro__` / `Cls.mro()`. For single inheritance it's just child → parent → ... → `object`.
C3 linearization is the algorithm that builds the MRO for **multiple inheritance**. It solves the "diamond problem" (D inherits B and C, both inherit A) by guaranteeing three things: a child always comes before its parents, the left-to-right order of bases is preserved, and every class appears exactly once (so A is visited once, after both B and C). If no consistent order exists, Python raises `TypeError: Cannot create a consistent MRO` at class creation.
It matters in practice because `super()` doesn't mean "my parent", it means "the **next class in the MRO** of the instance". That's what makes cooperative multiple inheritance and mixins work: each class calls `super().method()` and the chain runs through every class once.
**Your story:** typical real cases are mixins (e.g. `TimestampMixin, SoftDeleteMixin, Base` in SQLAlchemy models, or DRF/Django class-based view mixins) where the order of bases decided which `save()`/`dispatch()` ran first. If you never truly debugged one, say so and explain how you'd reason about it with `__mro__`.

### 2. Metaclasses: what does Pydantic/SQLAlchemy use them for? Have you written one, and would you?
A metaclass is the "class of a class": it controls how a class object is **created** (`type` is the default). Its `__new__`/`__init__` run when the `class` statement executes, so it can inspect and rewrite the class body.
Pydantic (`ModelMetaclass`) uses it to read the type annotations at class-definition time and build the field definitions + validators/serializers (v2 compiles them into the Rust `pydantic-core` schema). SQLAlchemy's declarative base uses one to turn `Column`/`Mapped[...]` attributes into a mapped `Table` and register the class with the mapper/registry.
Would you write one? Rarely. Since Python 3.6, `__init_subclass__` and class decorators cover ~90% of use cases (registries, validating subclasses, injecting attributes) and are much simpler. Metaclasses also conflict when you combine two libraries that each have their own ("metaclass conflict"). Good answer: "I know how they work, I'd reach for `__init_subclass__` or a decorator first."

### 3. `__getattr__` vs `__getattribute__` vs `__get__` (descriptors). Where does `@property` fit?
`__getattribute__` is called on **every** attribute access. It's the real lookup machinery; overriding it is rare and dangerous (easy to recurse infinitely; must call `object.__getattribute__`).
`__getattr__` is only called **after normal lookup fails** (AttributeError). Good for proxies, lazy attributes, delegation wrappers.
`__get__` belongs to a **descriptor**: an object stored as a *class* attribute that defines `__get__` (and optionally `__set__`/`__delete__`). When you access `obj.attr`, `__getattribute__` finds the descriptor on the class and calls its `__get__(obj, type)`.
Lookup order: data descriptors on the class (have `__set__`) → instance `__dict__` → non-data descriptors / class attributes → `__getattr__`.
`@property` is just a built-in **data descriptor**. Methods are non-data descriptors too: that's how functions become bound methods. So are `classmethod`, `staticmethod`, SQLAlchemy columns, and Pydantic's/Django's field objects.

### 4. What is a weakref and when have you needed one? How does it help a cache?
A weak reference points to an object **without increasing its refcount**, so it doesn't keep the object alive. When the object is garbage-collected, the weakref returns `None` (or a callback fires).
Cache use: `weakref.WeakValueDictionary` holds values only while something else uses them. Once nobody else references the object, it disappears from the cache automatically. You get "dedupe live objects" (e.g. one in-memory object per ID) without a memory leak. `WeakKeyDictionary` lets you attach metadata to objects you don't own without keeping them alive. Also used for observer/callback lists so subscribers don't leak.
Caveats: not every type supports weakrefs (`int`, `str`, `tuple`, and classes with `__slots__` unless you add `__weakref__`). And a weak cache is not an LRU: entries vanish as soon as the last strong ref dies, so it's not good for "keep the last 1000 results".

### 5. What happens when you `import` a module twice? Explain `sys.modules` and how you would deliberately reload a module. What breaks when you do?
The first `import` finds the module, executes its top-level code once, and stores the module object in `sys.modules`. Every later import (anywhere in the process) just returns the cached object from `sys.modules`: the code is **not** re-executed.
To reload deliberately: `importlib.reload(mod)`. It re-executes the module's code **into the same module object**.
What breaks: anything that grabbed references to the old objects keeps them. `from mod import func` elsewhere still points to the old function. Existing instances still belong to the old class, so `isinstance(old_obj, mod.Cls)` becomes False. Module-level state (connections, registries, singletons) is re-initialised or duplicated. Submodules aren't reloaded. That's why production code doesn't hot-reload; you restart the process (uvicorn `--reload` restarts the process too).

### 6. Circular imports - why do they happen and what are the three legitimate fixes?
Module A imports B at the top, B imports A at the top. While A is half-executed, it's already in `sys.modules`, so B gets a **partially initialised** A, and `from A import X` fails with `ImportError: cannot import name X (most likely due to a circular import)` because X isn't defined yet.
Fixes:
1. **Restructure**: move the shared piece into a third module (e.g. `models.py`/`types.py`) that both import. This is the real fix and usually reveals a layering problem.
2. **Import the module, not the name, or import lazily**: `import a` and use `a.X` at call time, or move the import inside the function that needs it.
3. **Type-hint-only imports**: `from typing import TYPE_CHECKING; if TYPE_CHECKING: from a import X` and use string annotations / `from __future__ import annotations`. Very common in SQLAlchemy/Pydantic models that reference each other.

### 7. Python 3.12/3.13 free-threaded (no-GIL) builds and sub-interpreters - what changes for a backend service, and would you adopt it today?
**Free-threaded build** (PEP 703, experimental in 3.13 as `python3.13t`, officially supported but still optional in 3.14): no GIL, so threads can run Python bytecode truly in parallel on multiple cores. Single-threaded code is a bit slower (extra locking / biased refcounting), and C extensions must be rebuilt and declared thread-safe, or the interpreter re-enables the GIL.
**Sub-interpreters** (PEP 684, per-interpreter GIL in 3.12; `concurrent.interpreters` / `InterpreterPoolExecutor` in 3.14): multiple isolated interpreters in one process, each with its own GIL. Parallelism like multiprocessing but cheaper; objects aren't shared, you pass data between them.
What changes for a backend: a typical FastAPI/Django service is I/O-bound and scales by running N worker processes (gunicorn/uvicorn workers, K8s replicas), so the GIL is rarely the bottleneck. Where it helps: CPU-heavy work inside the request (parsing, scoring, pandas-free transforms) could use threads instead of a process pool, with shared memory and less RAM per core.
Would you adopt it today? Not for production yet. I'd wait until my whole dependency tree (pydantic-core, psycopg, numpy, grpc, orjson…) ships free-threaded wheels, and benchmark it. The risk is that hidden thread-safety bugs in your own code that the GIL used to mask (e.g. non-atomic `dict` check-then-set patterns) start showing up. I'd pilot it on a CPU-bound worker first.

### 8. What is `functools.lru_cache` doing internally? What's the danger of putting it on a method?
It wraps the function with a dict keyed by the call arguments (args + kwargs flattened into a hashable key) plus a doubly linked list that tracks recency. On a hit it returns the cached value and moves the entry to the front. On a miss it calls the function, stores the result, and evicts the least-recently-used entry if `maxsize` is exceeded. All operations are O(1). It's implemented in C, and it's thread-safe in the sense that the cache structure won't corrupt (but the function may run twice concurrently for the same key). Arguments must be hashable. `cache_info()` and `cache_clear()` are available.
Danger on a method: `self` is part of the key, so the cache (which lives on the class-level function, i.e. forever) holds a **strong reference to every instance** that ever called it → instances are never garbage-collected → memory leak. Also the cache is shared across all instances, and if the instance's state changes, the cached result is stale.
Fixes: `functools.cached_property` for per-instance, no-arg values; a per-instance cache created in `__init__` (`self.get = lru_cache()(self._get)`); or cache at module level on the real key (not `self`).

### 9. How would you profile a Python service that is slow but not CPU-bound? (cProfile, py-spy, yappi, memray - what does each give you?)
"Slow but not CPU-bound" means it's **waiting**: on I/O, DB, locks, the GIL, a pool, or the event loop being blocked. So you want **wall-clock** time, not CPU time.
- **cProfile**: built-in deterministic profiler. Counts every call. High overhead, needs code changes or a wrapper, and it measures the thread it's in, so it's poor for async and for production. Fine for a local script.
- **py-spy**: sampling profiler that attaches to a **running process by PID** from outside, no code changes, very low overhead, safe for production. `py-spy dump` shows the current stack of every thread (great for "what is it stuck on right now"). `py-spy top` / `record --idle` produces flame graphs including idle/waiting time. This is usually first.
- **yappi**: deterministic profiler that understands **threads and asyncio coroutines**, and can measure wall time per coroutine. Good for figuring out which async function is spending time awaiting.
- **memray** (Bloomberg): **memory** profiler, not time. It tracks every allocation, including in C extensions, and gives flame graphs of who allocated what. It's for leaks and memory spikes, not latency.
Beyond profilers, for "not CPU-bound" the best tool is usually **distributed tracing** (OpenTelemetry spans around DB/HTTP calls) plus DB slow-query logs, plus `asyncio` debug mode (`PYTHONASYNCIODEBUG=1` logs callbacks that block the loop >100ms).

### 10. You have a memory leak in a long-running FastAPI worker. How do you find it?
1. **Confirm it's a leak**: graph RSS per pod over time (Prometheus/Grafana). A sawtooth that resets on restart and climbs steadily with traffic is a leak; a plateau is just a warm cache or allocator behaviour.
2. **Narrow it down**: does it correlate with a specific endpoint or job? Reproduce locally with a load test (locust) hitting one endpoint at a time.
3. **Measure Python-level objects**: `tracemalloc`. Take a snapshot, run traffic, take another, `snapshot.compare_to(old, "lineno")` shows which lines' allocations grew. Or `memray` for a full allocation flame graph (including C extensions). `objgraph.show_growth()` / `gc.get_objects()` counts by type show which object types are multiplying; `objgraph.show_backrefs` shows what's holding them.
4. **Usual suspects**: unbounded module-level dicts/caches (in-process caches with no max size), `lru_cache` on methods, appending to a global list, request objects stored in a global, background tasks/`create_task` results never cleaned up, SQLAlchemy sessions not closed, objects captured by closures/callbacks, large response bodies buffered, logging handlers added per request, and C-extension leaks.
5. **Not-really-a-leak**: glibc malloc fragmentation (memory freed by Python but not returned to the OS). Try `MALLOC_ARENA_MAX=2` or jemalloc.
6. **Stopgap while fixing**: gunicorn `--max-requests` with jitter to recycle workers periodically. Say clearly that this is a band-aid.

### 11. What are `__init_subclass__` and `typing.Protocol` good for in real code?
`__init_subclass__` is a classmethod on a base class that runs **every time a subclass is defined**. Real uses: auto-registering plugins/handlers (`class PdfExporter(Exporter, format="pdf")` → registered in `Exporter.registry["pdf"]`), validating that subclasses define required attributes, and injecting config via class keyword args. It replaces most metaclass use cases.
`typing.Protocol` gives **structural typing** ("static duck typing"): you define the methods a type must have, and any class with those methods matches, **without inheriting** from it. Real uses: defining interfaces at the boundary of your domain (`class BlobStore(Protocol): def put(...); def get(...)`) so your Azure Blob implementation and an in-memory fake both satisfy it without coupling to a base class; typing third-party objects you can't modify. `@runtime_checkable` allows `isinstance` checks (method presence only, not signatures).

### 12. Explain how `dataclass`, `NamedTuple`, `TypedDict`, and Pydantic BaseModel differ and when you'd use each.
- **`dataclass`**: generates `__init__`, `__repr__`, `__eq__` for a normal class. Mutable by default (`frozen=True` for immutable), `slots=True` for memory. **No runtime validation**. Use for internal domain objects / value objects.
- **`NamedTuple`**: an immutable tuple with named fields. Lightweight, hashable, unpackable, indexable. Use for small immutable records, e.g. function return values like `(lat, lon)`.
- **`TypedDict`**: just a type hint describing a **plain dict's** keys and value types. At runtime it's a normal dict, zero overhead, no validation. Use when the data must stay a dict (JSON blobs, kwargs, legacy code) but you want mypy to check key access.
- **Pydantic `BaseModel`**: **runtime validation, parsing, coercion and serialisation** (JSON schema, aliases, custom validators). Slower to construct than a dataclass (though v2's Rust core is fast). Use at **trust boundaries**: API request/response bodies, config (`pydantic-settings`), messages from queues, LLM structured output.
Rule of thumb: Pydantic at the edges, dataclasses in the core.

### 13. Type hints: what does `mypy --strict` catch that tests don't? Do you run it in CI?
Tests only check the paths you wrote tests for. The type checker checks **every path**, including the ones nobody tested. `--strict` specifically catches: `Optional` misuse (calling `.attr` on something that can be `None`, the #1 real win), functions missing annotations (`--disallow-untyped-defs`), implicit `Any` leaking from untyped libraries, wrong argument types/counts after a refactor, returning the wrong type on an edge branch, unused `# type: ignore`, and calling untyped functions from typed code.
It's also a refactoring safety net: rename a field or change a signature and the type checker lists every broken call site.
**Your story:** say honestly whether you ran it in CI. Strong answer: mypy (or pyright) in CI on new code with `--strict`, adopted gradually per module via config overrides on legacy modules, plus pre-commit locally.

### 14. What are contextvars and why do they exist for async code? Where would you use one? (Hint: request IDs / trace IDs.)
`contextvars.ContextVar` is a variable whose value is **scoped to the current execution context**, which in asyncio means **per task**. Each `asyncio.Task` gets a copy of the context when it's created, so setting a value in one request's task doesn't leak into another request's task running concurrently on the same thread.
Why they exist: `threading.local()` is per *thread*, but in asyncio thousands of requests share **one thread**, so thread-locals would mix up request data across requests.
Use: request ID / correlation ID / trace ID set in a middleware and read by a logging filter so every log line includes it without passing it through every function. Also: current tenant ID, current user, DB session in some designs. OpenTelemetry, structlog and Starlette all use contextvars under the hood. Remember to `reset(token)` after the request.

---

## B. ASYNC / CONCURRENCY (deep)

### 15. Explain the event loop. What is a "blocking the loop" bug and how do you detect it in production?
The event loop is a single-threaded scheduler. It keeps a queue of ready callbacks/tasks and uses the OS's I/O multiplexing (epoll/kqueue) to know which sockets are ready. It runs one task until that task hits an `await` on something not ready yet; the task **voluntarily yields**, the loop parks it, runs the next ready task, and resumes the first one when its I/O completes. Concurrency comes from cooperative yielding, not parallelism.
"Blocking the loop": a task does something that takes a long time **without awaiting**: a sync HTTP call (`requests`), a sync DB driver, `time.sleep`, heavy CPU work (JSON parsing of a 50MB payload, pandas, regex, bcrypt), or reading big files synchronously. While it runs, **no other task on that worker progresses**: all concurrent requests stall, health checks time out, websockets drop.
Detecting it in production: symptom is latency spikes across *all* endpoints at once while CPU on one core is pegged (or low, if it's a blocking sync call). Tools: `loop.slow_callback_duration` + asyncio debug mode logs any callback over a threshold; a "loop lag" metric (a background task that schedules `asyncio.sleep(0.1)` and measures how late it wakes up, exported to Prometheus); `py-spy dump` shows what the main thread is stuck on; tracing shows gaps where no span progresses. Libraries like `aiodebug` do this for you.

### 16. `asyncio.gather` vs `TaskGroup` vs `as_completed` - differences in cancellation and error semantics. Which do you reach for now?
- **`gather(*aws)`**: runs them concurrently, returns results **in input order**. If one raises: by default the exception propagates to the awaiter immediately **but the other tasks keep running** (they're not cancelled, so they become orphans). With `return_exceptions=True` it waits for all and returns exceptions as values. If the `gather` itself is cancelled, it cancels all children.
- **`asyncio.TaskGroup`** (3.11+): `async with TaskGroup() as tg: tg.create_task(...)`. If any task fails, **all the other tasks are cancelled**, the block waits for them to finish cancelling, and then all errors are raised together as an `ExceptionGroup` (handled with `except*`). No orphans, ever. This is structured concurrency.
- **`as_completed(aws)`**: an iterator that yields awaitables **in completion order**, so you can process results as soon as each finishes (e.g. stream first results, or stop early). Errors surface when you await that specific item; others are not cancelled automatically. Good with a `timeout`.
Which now: **TaskGroup** by default for "do these N things, all must succeed". `gather(return_exceptions=True)` when partial failure is acceptable and I want everything back. `as_completed` when I want results as they arrive. Bound concurrency with a semaphore in all cases.

### 17. What is structured concurrency? Why is `TaskGroup`/anyio considered safer than fire-and-forget `create_task`?
Structured concurrency: **concurrent tasks have a lifetime bound to a lexical scope**. A block that starts tasks can't exit until all of them have finished. Errors propagate up to the parent, and cancellation propagates down to the children. Like how a function call can't return before its body finishes, but for concurrency.
Why safer than `create_task` fire-and-forget: a bare `create_task` gives you a task with no owner. If it raises, the exception is only logged as "Task exception was never retrieved", maybe at GC time, so errors get silently lost. If the parent request is cancelled, the child keeps running (leaking work, DB connections, holding locks). The task can even be garbage-collected mid-flight if you don't keep a reference (Q18). Shutdown can't wait for it because nothing tracks it. TaskGroup (and anyio/Trio "nurseries") make all of that impossible by construction.
For genuine background work that outlives a request, use a real job queue (Celery/arq) or an app-lifetime TaskGroup started in the FastAPI `lifespan`, not an untracked task.

### 18. What happens to a Task if nobody holds a reference to it?
The event loop only keeps a **weak reference** to tasks. If your code doesn't keep a strong reference (`asyncio.create_task(coro())` with the result discarded), the task can be **garbage-collected before it finishes**, and the work silently disappears, sometimes with a "Task was destroyed but it is pending!" warning. The Python docs explicitly warn about this.
Fix: keep references, e.g. a set `background_tasks.add(t); t.add_done_callback(background_tasks.discard)`, or use a TaskGroup, which holds them for you.

### 19. How do you cancel an in-flight async operation cleanly? What is `CancelledError` and why should you never swallow it?
Cancel with `task.cancel()`. Or, preferably, use timeouts that cancel for you: `async with asyncio.timeout(5):` (3.11+) or `asyncio.wait_for`. Cancelling a TaskGroup's scope cancels all its children.
`cancel()` doesn't kill the task immediately: it schedules a **`CancelledError` to be raised inside the task at its next `await`**. That lets the task unwind: `finally` blocks and `async with` exits run, so connections get returned to the pool, locks released, transactions rolled back.
Never swallow it: since 3.8 `CancelledError` inherits from `BaseException` precisely so that `except Exception:` doesn't catch it. If you catch it (or a bare `except:` / `except BaseException:`) and don't re-raise, the task looks like it completed normally. Then `TaskGroup`, `timeout()` and shutdown logic all break: timeouts don't fire, the app hangs on shutdown, the parent never learns the child was cancelled. Rule: catch it only to clean up, then `raise`. Also avoid long blocking work in `finally` during cancellation; use `asyncio.shield` only for tiny critical sections (e.g. finishing a commit).

### 20. [WHITEBOARD] Implement an async semaphore-bounded worker pool that fetches 10,000 URLs with max 50 concurrent, per-host rate limiting, retries with jitter, and a global timeout.
Design: one shared `httpx.AsyncClient` (connection pooling), a global `Semaphore(50)` for concurrency, a per-host limiter (here a per-host semaphore + a minimum interval between requests), retries with exponential backoff and full jitter only on retryable errors, and `asyncio.timeout` around the whole thing. Use a fixed number of workers pulling from a queue so we don't create 10,000 tasks at once.
```python
import asyncio, random, time
from collections import defaultdict
from urllib.parse import urlparse
import httpx

GLOBAL_CONCURRENCY = 50
PER_HOST_CONCURRENCY = 5
PER_HOST_MIN_INTERVAL = 0.2        # max 5 req/s per host
RETRIES = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

class HostLimiter:
    def __init__(self):
        self.sems = defaultdict(lambda: asyncio.Semaphore(PER_HOST_CONCURRENCY))
        self.locks = defaultdict(asyncio.Lock)
        self.next_allowed = defaultdict(float)

    async def acquire(self, host):
        await self.sems[host].acquire()
        async with self.locks[host]:               # space requests out per host
            now = time.monotonic()
            wait = self.next_allowed[host] - now
            self.next_allowed[host] = max(now, self.next_allowed[host]) + PER_HOST_MIN_INTERVAL
        if wait > 0:
            await asyncio.sleep(wait)

    def release(self, host):
        self.sems[host].release()

async def fetch(client, url, global_sem, hosts):
    host = urlparse(url).netloc
    for attempt in range(RETRIES):
        async with global_sem:
            await hosts.acquire(host)
            try:
                r = await client.get(url, timeout=10)
                if r.status_code not in RETRYABLE_STATUS:
                    return url, r.status_code, r.content
            except (httpx.TransportError, httpx.TimeoutException):
                pass
            finally:
                hosts.release(host)
        # back off OUTSIDE the semaphore so we don't hold a slot while sleeping
        await asyncio.sleep(random.uniform(0, min(30, 0.5 * 2 ** attempt)))   # full jitter
    return url, None, None   # gave up

async def crawl(urls, total_timeout=600):
    queue = asyncio.Queue()
    for u in urls:
        queue.put_nowait(u)
    results, global_sem, hosts = [], asyncio.Semaphore(GLOBAL_CONCURRENCY), HostLimiter()

    async def worker(client):
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            results.append(await fetch(client, url, global_sem, hosts))

    limits = httpx.Limits(max_connections=GLOBAL_CONCURRENCY)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        try:
            async with asyncio.timeout(total_timeout):
                async with asyncio.TaskGroup() as tg:
                    for _ in range(GLOBAL_CONCURRENCY):
                        tg.create_task(worker(client))
        except TimeoutError:
            pass          # return partial results; remaining URLs are still in the queue
    return results
```
Points to say out loud: honour `Retry-After` on 429; only retry idempotent requests (GETs are); the global timeout cancels everything cleanly via TaskGroup; for millions of URLs, stream results to disk/queue instead of a list; a token bucket per host is the more precise rate limiter; in production this becomes a distributed crawler with a shared Redis rate limiter (see Q69).

### 21. How would you run a CPU-heavy function inside an async service without stalling it? Compare `run_in_executor`, a process pool, and a separate worker service.
- **`run_in_executor(None, fn)` / `asyncio.to_thread(fn)`**: runs in a **thread pool**. Frees the loop, but because of the GIL a pure-Python CPU function still competes with the loop thread for the GIL, so it only really helps for blocking I/O or C code that releases the GIL (numpy, hashing, compression, many parsers). Cheap, easy, shares memory.
- **`ProcessPoolExecutor`** via `loop.run_in_executor(pool, fn, args)`: true parallelism on other cores. Costs: arguments and results must be pickled (expensive for big payloads), worker processes use extra RAM, a crashed worker breaks the pool, and it's awkward in containers (sizing CPU limits, fork vs spawn). Good for medium jobs of 100ms–few seconds that must stay synchronous with the request.
- **Separate worker service** (Celery/RQ/arq/a dedicated microservice behind a queue): the API enqueues and returns a job ID (or awaits briefly). Scales independently (different pod size, autoscaled on queue depth), isolates failures and memory, has retries and observability. Costs: infra, latency, eventual consistency, and you need a job-status API (Q30).
Rule: < ~50ms with GIL-releasing code → thread; pure-Python CPU work of moderate size that the caller must wait for → process pool; long, heavy, spiky, or needs retries → separate worker service. Also consider just making it faster first (vectorise, cache, precompute).

### 22. Backpressure in an async producer/consumer pipeline - how do you implement it?
Backpressure = when consumers are slower than producers, **the producer must slow down** instead of buffering unboundedly until you run out of memory.
In asyncio: use a **bounded** `asyncio.Queue(maxsize=N)`. `await queue.put(item)` suspends the producer when the queue is full, so the producer automatically runs at the consumer's speed. Pair with a fixed number of consumers and `queue.join()` / sentinel values for shutdown. Never use `maxsize=0` (unbounded) in a pipeline fed by something fast.
Other layers: semaphores to cap in-flight work; when reading from Kafka, pause partitions / limit `max.poll.records` and commit only after processing; for HTTP ingestion, when internal queues are full, **reject** with 429/503 + `Retry-After` (load shedding) rather than accept and queue forever; streams (`async for` over a source) are pull-based, which is natural backpressure. The key design decision is what to do when full: block (slow the producer), drop (metrics/telemetry), or reject (API).

### 23. Threading: explain a race condition you actually debugged. What tool found it?
Technical frame: a race condition is when the result depends on the interleaving of concurrent operations. The classic pattern is **check-then-act** or **read-modify-write** without atomicity: two workers read `count=5`, both write 6.
Good example shapes (pick the one that matches your experience):
- **Redis task claim (Turing RLHF dashboard)**: two annotators click "claim" at the same moment; code did `GET lock` → if empty → `SET lock`. Both saw empty and both claimed. Fix: atomic `SET key value NX EX ttl` or a Lua script. Found via duplicate assignments in the DB / logs with the same task ID and two users.
- **DB "check then insert"** producing duplicates under concurrency. Fix: unique constraint + `INSERT ... ON CONFLICT`.
- **Lost update**: two requests read a row, modify, and write back. Fix: `SELECT ... FOR UPDATE` or optimistic version column (Q39).
Tools: honestly, it's usually found from **logs/data anomalies plus reasoning**, then confirmed by a reproduction (a test that fires N concurrent requests with `asyncio.gather`/threads, or adding a deliberate `sleep` between check and act to widen the window). For threads in C/C++ there's ThreadSanitizer; in Python, `faulthandler`/`py-spy dump` for deadlocks.
**Your story:** the Redis claim/unclaim lock at Turing is the natural one. Be specific: what the symptom was, how you reproduced it, and what made the fix atomic.

---

## C. API & SERVICE DESIGN

### 24. Design the error model for a public API: error codes, shapes, correlation IDs, and how the client distinguishes retryable from terminal failures.
Use one consistent error shape everywhere. **RFC 9457 "Problem Details"** (`application/problem+json`) is the standard to cite:
```json
{
  "type": "https://api.example.com/errors/quote-not-found",
  "title": "Quote not found",
  "status": 404,
  "code": "QUOTE_NOT_FOUND",
  "detail": "Quote q_123 does not exist or you do not have access",
  "request_id": "req_8f2c...",
  "errors": [{"field": "inputs.sum_insured", "code": "MUST_BE_POSITIVE"}]
}
```
- **HTTP status** carries the class of error: 4xx = client's fault, 5xx = server's fault.
- **Stable machine-readable `code`** (an enum documented and never renamed) so clients branch on `code`, not on message text. `detail` is human-readable and may change.
- **Correlation ID**: accept `X-Request-ID` / W3C `traceparent` from the client or generate one at the edge, put it in every log line and in every error response (and a response header), so support can find the exact trace from a customer ticket.
- **Retryable vs terminal**: make it explicit, don't make clients guess. Retryable: `429` (with `Retry-After`), `503` (with `Retry-After`), `502/504`, `408`, and `409` for concurrency conflicts where re-reading and retrying makes sense. Terminal: `400/422` validation, `401/403`, `404`, `409` business conflicts, `410`. Many APIs also add a `"retryable": true` field. And document that retries on non-idempotent POSTs are only safe with an **`Idempotency-Key`** header (Q44).
- Never leak stack traces or SQL in the body; log them server-side under the request ID. Validation errors list **all** field errors at once, not one per round trip.

### 25. How do you implement request-scoped DB sessions in FastAPI without leaking connections? Where do transactions begin and commit?
Use a **dependency with `yield`**, backed by one engine/connection pool created once at app startup (lifespan):
```python
engine = create_async_engine(DB_URL, pool_size=10, max_overflow=5, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session():
    async with SessionLocal() as session:          # closes -> returns connection to pool
        async with session.begin():                # commit on success, rollback on exception
            yield session

@app.post("/quotes")
async def create_quote(body: QuoteIn, session: AsyncSession = Depends(get_session)):
    ...
```
The `async with` guarantees the session is closed and the connection returned even if the handler raises. That's what prevents leaks. FastAPI runs the code after `yield` after the response is sent (in recent versions, before the response for exceptions).
Where transactions begin/commit: **one transaction per request (unit of work)**, begun when the session first touches the DB and committed at the end of the request by the dependency, not by random functions deep in the code. Service functions receive the session and don't commit themselves. That keeps the whole request atomic.
Leak pitfalls to mention: creating an engine per request (new pool every time!), sessions stored in globals, background tasks using the request's session after it's closed (give them their own session), long-running work (HTTP calls to other services) inside an open transaction (holds a connection and locks; do I/O before/after the transaction), and pool size × number of workers × pods exceeding Postgres `max_connections` (use PgBouncer).

### 26. Implement rate limiting three ways: fixed window, sliding window log, token bucket. Which do you deploy at the edge vs in-app, and why?
- **Fixed window**: counter per key per time bucket. Redis: `INCR rl:{user}:{epoch_minute}`, `EXPIRE` 60s, reject if > limit. Cheapest (one key, O(1)). Flaw: bursts at the boundary. A client can do `limit` requests at 12:00:59 and `limit` again at 12:01:00 = 2× in 2 seconds.
- **Sliding window log**: store a timestamp for each request in a sorted set. On each request: `ZREMRANGEBYSCORE key 0 now-window`, `ZCARD key`; if < limit then `ZADD key now now`. Run it as a Lua script / MULTI so it's atomic. Exact, no boundary burst, but memory is O(requests per window) per key. Expensive at high limits. (The cheap compromise is the **sliding window counter**: weight the previous window's count by overlap.)
- **Token bucket**: bucket has capacity `B`, refills at `r` tokens/sec; each request takes one token, reject if empty. Store just `(tokens, last_refill_ts)` per key and compute the refill lazily on each request (Lua script for atomicity). O(1) memory, allows controlled **bursts** up to B while enforcing an average rate r. This is what most real systems use (AWS API Gateway, Envoy, Stripe).
```python
# token bucket core (do this atomically in Redis Lua in real life)
def allow(state, now, rate, capacity):
    tokens = min(capacity, state.tokens + (now - state.ts) * rate)
    if tokens < 1:
        return False, state._replace(tokens=tokens, ts=now)
    return True, state._replace(tokens=tokens - 1, ts=now)
```
**Edge vs in-app**: at the **edge** (API gateway, Nginx/Envoy, Cloudflare, Azure APIM/Front Door) put coarse, cheap protection: per-IP / per-API-key token bucket, to stop abuse and floods before they cost you compute. In **app** do business-aware limits that need context the edge doesn't have: per tenant, per plan tier, per expensive operation (e.g. "10 quote generations/minute", "LLM tokens per tenant per day"), using a shared Redis so all pods agree. Mention: return `429` with `Retry-After` and `RateLimit-*` headers; fail open or closed when Redis is down is a conscious choice.

### 27. A client retries aggressively on 500s and amplifies an outage. Design the fix on both sides. (Expect: exponential backoff + jitter, circuit breaker, load shedding.)
This is a **retry storm**: the service slows down → clients time out and retry → load multiplies → the service falls over completely and can't recover even after the original cause is gone.
**Client side**:
- Exponential backoff with **jitter** (full jitter: `sleep(random(0, min(cap, base * 2**attempt)))`) so retries spread out instead of arriving in synchronized waves.
- **Cap attempts** (e.g. 3) and use a **retry budget** (retries may be at most ~10% of total requests per client); never retry at multiple layers (if gateway, SDK and app all retry 3×, that's 27×).
- Only retry retryable errors (503/429/timeouts), honour `Retry-After`, and only retry idempotent operations or ones with an idempotency key.
- **Circuit breaker** (Q28): after N failures, stop calling for a cooldown and fail fast.
- Sensible timeouts with deadline propagation (don't keep working on a request whose caller has already given up).
**Server side**:
- **Load shedding**: when overloaded (concurrency limit hit, queue depth high, latency over SLO), reject excess immediately with `503 + Retry-After` (cheap) instead of accepting and timing out (expensive). Prioritise: shed low-priority traffic first, keep health checks and paid/critical traffic.
- **Rate limit per client** (Q26) so one misbehaving client can't take everyone down.
- Bounded queues and concurrency limits, short server-side timeouts.
- Make operations **idempotent** so retries are at least safe.
- Autoscaling helps, but too slowly to stop a storm. Shedding is what saves you.

### 28. Explain the circuit breaker pattern - closed/open/half-open. Have you implemented one?
A wrapper around calls to a dependency that **stops calling it when it's clearly broken**, so you fail fast instead of piling up threads/connections waiting on timeouts, and give the dependency time to recover.
- **Closed** (normal): calls go through; failures are counted (consecutive failures or error rate over a window).
- **Open**: failure threshold crossed → all calls **fail immediately** (or return a fallback, e.g. cached data / degraded response) for a cooldown period, without touching the dependency.
- **Half-open**: after the cooldown, let **a few trial requests** through. If they succeed → back to closed. If they fail → back to open, restart the cooldown.
Details worth mentioning: count only relevant failures (timeouts, 5xx, connection errors; not 4xx), state is usually per-process (fine) or shared in Redis (rarely needed), expose breaker state as a metric and alert on "open". Libraries: `pybreaker`, `purgatory` (async), `tenacity` for retries; service meshes (Istio/Envoy outlier detection) do it at the infra level.
**Your story:** say honestly whether you built one. If you only used retries + timeouts, say that, and describe where you would have added a breaker (e.g. around an LLM API or Azure function calls from Pulse).

### 29. Graceful shutdown of a FastAPI service in K8s: SIGTERM arrives. Walk through every step so no request is dropped. What is `terminationGracePeriodSeconds` and `preStop`?
What K8s does when a pod is deleted (deploy, scale-down, node drain), and these two things happen **in parallel**:
(a) the pod is marked Terminating and removed from the Service's **Endpoints** → kube-proxy/ingress controllers stop routing to it, **but this takes a few seconds to propagate**;
(b) the kubelet runs the **`preStop` hook**, then sends **SIGTERM** to the container.
The race: if the app stops accepting connections on SIGTERM immediately, load balancers that haven't been updated yet still send it traffic → connection refused / 502s.
Steps for zero dropped requests:
1. **`preStop` hook**: `exec: ["sleep", "10"]` (or `sleep` action in newer K8s). This delays SIGTERM long enough for endpoint removal to propagate everywhere, so new traffic stops arriving before the app starts shutting down.
2. **SIGTERM → uvicorn/gunicorn graceful shutdown**: stop accepting new connections, let in-flight requests finish (uvicorn `--timeout-graceful-shutdown`, gunicorn `graceful_timeout`), close keep-alive connections.
3. **Readiness probe** should start failing during shutdown (belt and braces).
4. **FastAPI `lifespan` shutdown**: after requests drain, close DB pools, flush logs/metrics/traces, stop background consumers (stop pulling new messages, finish or nack the current one so it's redelivered).
5. **`terminationGracePeriodSeconds`** (default 30s): the **total budget** from the start of termination (it includes the preStop time) until the kubelet sends **SIGKILL**. It must be > preStop sleep + the longest request drain + cleanup. For long requests / workers, raise it (e.g. 60–120s).
Also: make sure the app is **PID 1** or uses an init (tini / `exec` form in Dockerfile) so it actually receives SIGTERM. A shell-wrapped `CMD python app.py` often swallows the signal and the app just gets killed after 30s. Use a PodDisruptionBudget and a `maxUnavailable: 0` rolling update so capacity stays up during deploys.

### 30. How do you do a long-running job over HTTP? Compare polling with a job resource, webhooks, and SSE. What did you do at Aventum for document generation?
Never hold an HTTP request open for minutes: load balancers time out (often 60–230s; Azure Front Door / App Gateway have limits), pods restart, clients disconnect. Turn it into an **asynchronous job**: `POST /documents` → `202 Accepted` + `Location: /jobs/{id}`, the work happens in a worker via a queue.
- **Polling a job resource**: client calls `GET /jobs/{id}` → `{status: queued|running|succeeded|failed, progress, result_url}`. Simplest, works with any client, firewalls, retries. Cost: polling latency and wasted calls (mitigate with `Retry-After` hints / backoff). Default choice for public APIs.
- **Webhooks**: client registers a callback URL; you POST to it when done. No polling, good for server-to-server integration. Costs: the client must expose a public endpoint; you need signing (HMAC), retries with backoff, idempotent delivery (receivers must dedupe by event ID), and a dead-letter for undeliverable events. Usually offered *in addition to* polling.
- **SSE (Server-Sent Events)**: client keeps a one-way HTTP stream open and receives progress events live. Great UX for a browser showing progress or streaming LLM tokens. Costs: long-lived connections (proxy timeouts, need heartbeats, sticky-ish or pub/sub fan-out to the right pod), reconnect handling (`Last-Event-ID`). Use for the UI; still back it with a job resource so state survives disconnects.
**Your story (Aventum doc generation):** describe what Pulse actually did. Likely shape: request triggers generation via a queue / Azure Function, document stored in Blob, status tracked in DB, client polls or the UI is notified, and the document is downloaded via a SAS URL. Be precise about which of these it was.

### 31. How do you design an API that returns a 200MB result set?
Don't return 200MB in one JSON response: it's memory-heavy on both sides (server builds the whole thing in RAM), times out through gateways, and can't resume on failure. Options, depending on the use case:
- **Pagination** for interactive use: **cursor/keyset pagination** (`?after=<last_id>&limit=1000` using `WHERE id > :last ORDER BY id`), not `OFFSET` (which gets slower the deeper you go and skips/duplicates rows when data changes). Return `next_cursor`.
- **Streaming** if the client really wants it all in one call: `StreamingResponse` with **NDJSON** / CSV, reading from the DB with a server-side cursor (`yield_per` / `stream_results`) so memory stays flat. Enable gzip. Downside: if it breaks mid-way, the client restarts.
- **Async export job** for bulk/analytics (usually the best answer for 200MB): `POST /exports` → job (Q30) → worker writes the file (CSV/Parquet, compressed) to blob storage → client downloads via a **pre-signed/SAS URL** directly from S3/Blob (supports range requests/resume, CDN, doesn't touch your API pods).
Also ask: does the client really need 200MB? Often filtering, field selection (`?fields=`), or server-side aggregation is the real fix.

### 32. Multi-tenancy: how do you isolate tenants at the API, service and DB layer? Schema-per-tenant vs row-level vs DB-per-tenant. Insurance context - what did Aventum use?
**API layer**: tenant is derived from the **authenticated identity** (a JWT claim, or the API key → tenant mapping), **never** from a client-supplied header/body field alone. Per-tenant rate limits and quotas. Tenant ID in every log line and trace.
**Service layer**: tenant context set once per request (a contextvar), passed to every repository call; per-tenant config/feature flags; per-tenant queues or fair scheduling for background work so one tenant can't starve others (Q93); per-tenant encryption keys if required.
**DB layer**, three models:
- **Row-level (shared schema, `tenant_id` column)**: cheapest, easy to operate, one migration for everyone, scales to thousands of tenants. Risk: one missing `WHERE tenant_id = ...` leaks data. Mitigate with **Postgres Row-Level Security** (`CREATE POLICY ... USING (tenant_id = current_setting('app.tenant_id'))`) set per transaction, plus composite indexes starting with `tenant_id`. Noisy-neighbour risk.
- **Schema-per-tenant**: one Postgres schema per tenant, set `search_path` per request. Stronger logical isolation, per-tenant backup/restore is easier. Costs: migrations run N times, catalog bloat past a few hundred/thousand tenants, connection pooling gets trickier.
- **DB-per-tenant**: strongest isolation (security, performance, data residency, per-tenant restore, can be deleted cleanly for GDPR), per-tenant scaling. Costs: most expensive, operational overhead (N databases, N migrations, connection management), cross-tenant analytics need a separate warehouse.
Insurance context: regulated data, few large tenants (carriers/MGAs/brokers), contractual isolation requirements, and sometimes region-specific residency → often **DB-per-tenant or schema-per-tenant for big customers**, row-level for small ones (a hybrid "pooled vs silo" model).
**Your story:** state exactly what ATOMX/Aventum used (shared DB with tenant column? separate Cosmos/SQL DBs per client? separate Azure resources per client?) and why. Don't guess here; the interviewer will push.

### 33. Feature flags: how do you roll out a risky backend change to 1% of traffic?
Put the new code path behind a flag, deploy it **dark** (flag off), then turn it on gradually.
- **Deterministic bucketing**: `hash(flag_name + user_or_tenant_id) % 100 < percentage`. The same user consistently gets the same experience (no flip-flopping between requests), and raising 1% → 5% → 25% keeps the original 1% included. Choose the unit carefully: per user, per tenant (insurance: often per tenant/broker), or per request (only for stateless changes).
- Flag config lives in a flag service (LaunchDarkly, Unleash, Flagsmith, Azure App Configuration feature manager) or a DB/Redis table with caching, so you can change it **without a deploy** and kill it instantly.
- **Observability per variant**: tag metrics, logs and traces with the flag variant so you can compare error rate/latency between the 1% and the 99%. Define rollback criteria up front (error rate, p99, business metric).
- For really risky backend changes: **shadow traffic / dark launch** first (run the new path in parallel, compare results, discard its output), then 1%, then ramp.
- Hygiene: flags are tech debt; give each an owner and an expiry, and remove the old code path after full rollout. Avoid flag combinations explosion.
Alternative at infra level: canary deployment (Argo Rollouts/Flagger, or weighted ingress routing to a new version), which is per-request rather than per-user.

### 34. How do you design for replay/backfill? If a bug corrupted 3 days of processed records, what does your system need to have had in place?
You can only fix 3 days of corrupted output if you still have the **inputs** and can **re-run the processing deterministically** and **safely overwrite** the outputs. Things you need in place beforehand:
1. **Immutable raw input retained**: raw events/files/emails/requests stored as-received (blob storage "raw zone", Kafka with long retention, an event log table) for longer than your detection window.
2. **Derived data is reproducible**: processing is a function of (input + code version + config/reference data version). Record which **code version and rules version** produced each record.
3. **Idempotent writes / upserts** keyed on a natural/business key, so re-processing overwrites instead of duplicating.
4. **Lineage / audit**: each output row knows its source record ID and processing run ID, so you can find exactly what was affected ("all records processed by v1.42 between T1 and T2").
5. **A replay path**: the pipeline can be pointed at a time range or a list of IDs, and the backfill runs at a throttled rate / on separate workers so it doesn't hurt live traffic.
6. **Side effects separated**: re-processing must not re-send emails, webhooks, or re-charge payments. Side effects go through an outbox with dedup, or are disabled in backfill mode.
7. Backups/PITR as the last resort, plus audit trail/history tables to compare before/after.
Then the actual remediation: fix the bug, identify affected records, dry-run the backfill to a shadow table and diff, then apply, then notify downstream consumers.

---

## D. DISTRIBUTED SYSTEMS CORRECTNESS

### 35. Explain exactly-once processing in a pipeline that reads from Kafka and writes to Postgres. Design it properly. (Looking for: transactional outbox, idempotency keys, dedupe table, or offset-commit-after-write.)
True exactly-once **delivery** doesn't exist over a network. What you build is **at-least-once delivery + idempotent processing = effectively-once results**.
Failure to design for: you write to Postgres, then crash before committing the Kafka offset → after restart the message is redelivered → duplicate write. Or you commit the offset first, then crash before writing → message lost.
Design:
1. Disable auto-commit. Consume a message (or batch).
2. In **one Postgres transaction**: do the business write **and** record that you processed it. Either:
   - a **dedupe table** `processed_messages(message_id PRIMARY KEY)` (or `(topic, partition, offset)`), insert it with `ON CONFLICT DO NOTHING`, and if 0 rows inserted → already processed, skip; or
   - make the business write itself idempotent: an upsert keyed on a natural key / idempotency key from the event (`INSERT ... ON CONFLICT (event_id) DO NOTHING/UPDATE`); or
   - **store the Kafka offsets in Postgres** in the same transaction (`consumer_offsets(topic, partition, offset)`), and on startup/rebalance seek to the stored offset. Then the DB is the source of truth for progress and the write + offset are atomic.
3. Commit the transaction, **then** commit the offset to Kafka (offset-commit-after-write). If you crash in between, you get a redelivery, which step 2 makes harmless.
If processing also needs to *produce* events, use the **transactional outbox** (Q36) for the output side. Kafka's own "exactly-once semantics" (idempotent producer + transactions) only covers Kafka-to-Kafka (read-process-write within Kafka), not external DBs.

### 36. What is the transactional outbox pattern, and what problem does it solve that a "write to DB then publish to Kafka" does not?
Problem with "write DB, then publish": they're two separate systems with no shared transaction. If the DB commit succeeds and the publish fails (broker down, pod killed between the two lines), downstream never hears about the change: inconsistency. If you publish first and the DB commit then fails, downstream acts on something that never happened. That's the dual-write problem (Q37).
Outbox: in the **same DB transaction** as the business change, insert the event into an `outbox` table (`id, aggregate_id, event_type, payload, created_at, published_at`). The commit makes both or neither happen. A separate **relay** process reads unpublished outbox rows (polling with `FOR UPDATE SKIP LOCKED`, or CDC on the outbox table, Q41), publishes them to Kafka, and marks them published / deletes them.
Properties: no lost events; **at-least-once** publishing (the relay can crash after publish, before marking), so consumers must be idempotent (dedupe on event ID); ordering per aggregate is preserved if you publish in order and partition by aggregate ID. Clean up old rows regularly.

### 37. What is the dual-write problem? Where have you had one without realizing it?
Dual write = a single logical operation that writes to **two systems that can't share a transaction** (DB + message broker, DB + cache, DB + search index, DB + blob storage, DB + external API). Any crash or failure between the two writes leaves them inconsistent, and there's no rollback across both.
Common hidden examples: saving a row then `redis.delete(cache_key)` (if the delete fails, stale cache forever); saving to Postgres and then indexing in Elasticsearch/Azure AI Search; uploading a file to Blob then inserting the metadata row (orphan blob, or a row pointing to a missing blob); `db.commit()` then `celery_task.delay()` (task lost if broker is down; or the task runs **before** the commit is visible if you enqueue before commit); sending an email/webhook inside a transaction that later rolls back.
Fixes: outbox / CDC, making one system the source of truth and deriving the other from it asynchronously, ordering the writes so the failure mode is harmless (upload blob first, then insert row; garbage-collect orphan blobs), idempotent retries, periodic reconciliation jobs.
**Your story:** candidates you likely had: ATS (MongoDB write + Celery task enqueue + Azure Blob upload), Jio recommender (Postgres/Mongo + Redis cache), RLHF dashboard (MongoDB task data + Redis stats/locks). Pick one and say how it could break and how you'd fix it now.

### 38. Explain the saga pattern. Choreography vs orchestration - pick one for a quote -> bind -> issue policy flow and defend it.
A **saga** is a long-running business transaction across multiple services, implemented as a sequence of **local transactions**, each with a **compensating action** that semantically undoes it if a later step fails (since there's no distributed ACID transaction). E.g. "reserve capacity" is undone by "release capacity", "take payment" by "refund".
- **Choreography**: no central coordinator. Each service listens for events and reacts (`QuoteAccepted` → binding service binds → emits `PolicyBound` → issuance service issues...). Loosely coupled, no single point of control. Downside: the flow is implicit and spread across services, hard to see "where is this policy right now?", hard to change the order, and cyclic dependencies creep in.
- **Orchestration**: a central orchestrator (a state machine/workflow engine: Temporal, Azure Durable Functions, AWS Step Functions, or your own state table) tells each service what to do and handles failures/compensations. Flow is explicit and visible in one place, with timeouts and retries per step.
**For quote → bind → issue: orchestration.** Defence: it's a regulated, high-value, strictly ordered business process with human/underwriter steps and long waits (referrals, payment, subjectivities), where you must answer "what state is policy X in and why" for audit and support. Compensation logic (e.g. bind succeeded but issuance/document generation failed → retry issuance, or void the binder and notify the broker) is much safer in one explicit state machine. The flow changes with product rules, and changing one orchestrator is easier than re-wiring events across services. Choreography is still fine for the **side effects** after issuance (notify CRM, analytics, emails) where nothing needs to be compensated.

### 39. Optimistic vs pessimistic locking. Implement optimistic locking in Postgres and explain what the client does on conflict.
- **Pessimistic**: lock the row before modifying (`SELECT ... FOR UPDATE`) so others wait. Safe when contention is high and conflicts are expensive, but it holds locks (deadlock risk, lower throughput) and can't span a user's think-time between two HTTP requests.
- **Optimistic**: don't lock; detect conflicts at write time with a **version column**. Best when conflicts are rare and for "read → user edits for 5 minutes → save" flows.
```sql
ALTER TABLE quote ADD COLUMN version int NOT NULL DEFAULT 1;

-- read: SELECT id, premium, version FROM quote WHERE id = $1;   -- got version = 7
UPDATE quote
SET premium = $2, version = version + 1, updated_at = now()
WHERE id = $1 AND version = 7;
-- rowcount = 1 -> success; rowcount = 0 -> someone else changed it -> conflict
```
SQLAlchemy does this for you with `__mapper_args__ = {"version_id_col": version}` and raises `StaleDataError`.
Over HTTP, expose it with **ETags**: `GET` returns `ETag: "7"`, the client sends `If-Match: "7"` on `PUT/PATCH`, the server returns **`412 Precondition Failed`** (or `409 Conflict`) on mismatch.
Client on conflict: **re-fetch the latest version and re-apply** the change. Automatically, if the change is a commutative operation (e.g. increment, add a tag), retry a few times. If it's a human edit, show "this record was changed by someone else", display the diff, and let the user merge or overwrite. Never blindly retry with the old data, which is just a lost update again.

### 40. Two workers pick the same job from a Postgres "jobs" table. Fix it. Now do it without a distributed lock. (Expect: SELECT ... FOR UPDATE SKIP LOCKED.)
The bug: both run `SELECT ... WHERE status='pending' LIMIT 1`, both see the same row, both process it.
Fix with row locks, **SKIP LOCKED** so workers don't block on each other:
```sql
-- claim atomically in one statement
UPDATE jobs
SET status = 'running', locked_by = $worker_id, locked_at = now(), attempts = attempts + 1
WHERE id = (
    SELECT id FROM jobs
    WHERE status = 'pending' AND run_at <= now()
    ORDER BY priority DESC, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```
`FOR UPDATE` locks the row; `SKIP LOCKED` makes other workers skip rows already locked by someone else instead of waiting, so N workers each grab different jobs, with no Redis/ZooKeeper lock. The row lock is released when the claim transaction commits; the `status='running'` is what keeps others off it afterwards.
Also handle crashed workers: a **lease/visibility timeout**: a reaper resets jobs with `status='running' AND locked_at < now() - interval '10 min'` back to `pending` (so processing must be idempotent, since the job might run twice). Add a max-attempts → `failed`/dead-letter. Index on `(status, run_at)` (a partial index `WHERE status='pending'`). Alternative design: keep the transaction open while processing (lock held = lease, released automatically on crash), but that ties up a connection per in-flight job, so it's only good for short jobs. Libraries implementing this: `procrastinate`, `pgqueuer`, Oban (Elixir), graphile-worker.

### 41. What is the outbox vs CDC (Debezium) tradeoff?
Both solve "reliably publish DB changes to Kafka". Difference is **what you capture** and **how**.
- **Outbox (with polling relay)**: you explicitly write domain events into an outbox table. Events are **intentional, well-shaped domain events** (`PolicyIssued` with exactly the payload consumers need), decoupled from your table schema. Simple to build. Costs: extra writes in every transaction, a poller adds latency (polling interval) and DB load, you must clean up the table.
- **CDC (Debezium reading the Postgres WAL / logical replication)**: captures **every row change** from the transaction log without touching application code. Near-real-time, no polling load, catches changes made outside the app (manual SQL, other services). Costs: you're publishing your **internal table schema** as a public contract (rename a column → you break consumers), events are low-level row diffs (not business meaning), and you run Kafka Connect/Debezium infra; replication slots can bloat WAL if the connector stops.
Best of both, and very common: **outbox + CDC** = write domain events to the outbox table, and let Debezium's outbox event router stream that table. Intentional events, no polling, reliable.
Rule: outbox when you need domain events between services; raw CDC for data replication to a warehouse/search/cache where the table schema is acceptable.

### 42. Clock skew: why can't you use wall-clock timestamps to order events across services? What do you use instead?
Each machine's clock drifts and is corrected by NTP, so clocks across servers differ by milliseconds to seconds, and can even **jump backwards** after an NTP adjustment or a VM pause. So event A on server 1 at `10:00:00.005` may actually have happened **after** event B on server 2 at `10:00:00.010`. "Last write wins by timestamp" can then silently drop the newer write. Also, two events can have the same timestamp.
Instead:
- **Within one service/process**: `time.monotonic()` for durations (never wall clock).
- **A single authority assigns order**: a DB sequence / `BIGSERIAL`, a Kafka partition offset (total order within a partition, so partition by entity ID to order all events of one entity), a version number per aggregate (Q39). This is what you use 95% of the time.
- **Logical clocks**: **Lamport timestamps** (a counter incremented on each event and on receive set to `max(local, received)+1`) give an order consistent with causality. **Vector clocks** additionally detect *concurrent* events (used by Dynamo-style DBs for conflict detection).
- **Hybrid Logical Clocks (HLC)**: physical time + a logical counter; close to wall time but causally consistent (CockroachDB, YugabyteDB). Google Spanner uses TrueTime with bounded uncertainty and waits out the uncertainty.
Wall-clock timestamps are still fine to *store* for humans and approximate ordering; just don't use them for correctness decisions.

### 43. CAP - what does it actually say, and what does PACELC add? Where does your Jio recommender sit?
**CAP**: in a distributed data store, when a **network Partition** happens, you must choose between **Consistency** (every read sees the latest write, linearizability, or the request fails) and **Availability** (every request gets a non-error response, possibly stale). You can't "pick 2 of 3" freely, because partitions aren't optional in a distributed system. So the real choice is **C or A *during a partition***. It says nothing about normal operation.
**PACELC** adds the normal case: **if Partition → choose A or C; Else (normal operation) → choose Latency or Consistency.** Even without failures, strong consistency costs latency (synchronous replication, quorum reads). Examples: DynamoDB / Cassandra = PA/EL (available, low latency, eventually consistent by default); Spanner / single-primary Postgres with synchronous replica reads = PC/EC; MongoDB defaults are roughly PC/EC for primary reads, PA/EL if you read from secondaries.
**Jio recommender**: a news recommendation feed is the textbook **AP / PA-EL** system. Showing slightly stale recommendations (from Redis cache / a replica / a precomputed list) is far better than an error or a slow page. Availability and latency win; eventual consistency of user-interaction signals and recommendation lists is perfectly acceptable. Things like user auth or consumption counters for billing would be the C side, if any.
**Your story:** tie it to the real components: Redis for serving recs (fast, possibly stale), Postgres/Mongo for source data, Pub/Sub for async events (eventual). Say where you'd fall back (e.g. trending/popular list if personalised recs are unavailable).

### 44. Idempotency at scale: where do you store the idempotency keys and how do you expire them? What if the original request is still in flight?
Flow (Stripe-style): the client generates a unique `Idempotency-Key` (UUID) per logical operation and resends the **same key** on retries. The server stores `key → (request fingerprint, status, response)`.
**Where to store**:
- **In the same DB as the business data** (a table with `UNIQUE(tenant_id, idempotency_key)`), written **in the same transaction** as the business change. That's the strongest guarantee: the record of "done" and the actual effect commit atomically.
- **Redis** (`SET key ... NX EX 86400`) for speed and automatic expiry, when the operation's own effects are themselves idempotent or when a small risk window is acceptable. Redis can lose data on failover, so don't rely on it alone for money movement.
- Scope keys by tenant/user and endpoint; store a **hash of the request body** to reject the same key reused with a different payload (`422`).
**Expiry**: keep keys for longer than the client's maximum retry window, usually **24h–7 days**. Redis TTL; in Postgres, an `expires_at` column + a periodic cleanup job (or partition by day and drop old partitions).
**Original request still in flight**: insert the key first with `status='in_progress'` (atomic insert / `SET NX`). A second request with the same key that finds `in_progress` must **not** execute again. Return **`409 Conflict`** ("request in progress, retry later", with `Retry-After`), or wait/poll briefly for the result. When the first finishes, store the response; later duplicates get the **stored response replayed** (same status and body). If the first request crashed, the `in_progress` record needs a lease timeout after which a retry may take over (and the operation must be safe to resume).

---

## E. DATA LAYER, PERFORMANCE & SCALE

### 45. A Postgres query got slow overnight with no code change. Give me your full investigation path. (EXPLAIN ANALYZE, stats, plan flip, bloat, param sniffing.)
"No code change" ≠ nothing changed. Data volume, data distribution, statistics, load, or config changed.
1. **Confirm and scope**: is it this one query or everything? Check `pg_stat_statements` (mean/total time, calls, rows for this query over time) and DB-level metrics (CPU, IOPS, connections, locks, replication). If everything is slow, it's the box/load, not the plan.
2. **Look at the plan**: `EXPLAIN (ANALYZE, BUFFERS)` with **real production parameters**. Compare **estimated rows vs actual rows**: a big mismatch means bad statistics. Look for seq scans on big tables, nested loops over many rows, sorts/hashes spilling to disk ("external merge", `work_mem` too small).
3. **Plan flip**: the planner switched plans (e.g. index scan → seq scan, or a hash join → nested loop) because the table crossed some size threshold or the stats changed. `auto_explain` logging or a past plan helps compare. Common cause: **stale statistics** after a big bulk load/delete where autovacuum/autoanalyze hasn't run yet → fix with `ANALYZE table`. For correlated columns, `CREATE STATISTICS` (extended stats); for skewed columns, raise `default_statistics_target` on that column.
4. **Parameter-sensitive plans ("parameter sniffing")**: with prepared statements, after 5 executions Postgres may switch to a **generic plan** that's fine for typical values and terrible for a skewed one (e.g. a huge tenant). Check by comparing EXPLAIN with literal values vs `EXECUTE` of the prepared statement. Fix: `plan_cache_mode = force_custom_plan` for that session/role, or restructure the query/indexes.
5. **Bloat**: dead tuples from heavy UPDATE/DELETE that autovacuum isn't keeping up with (check `pg_stat_user_tables.n_dead_tup`, `last_autovacuum`). Bloated tables/indexes mean more pages to read. Also a **long-running transaction or an abandoned replication slot** holding back vacuum (`pg_stat_activity` for old `xact_start`, `pg_replication_slots`). Fix: tune autovacuum for that table, `VACUUM`, `REINDEX CONCURRENTLY`, `pg_repack`.
6. **Locks / contention**: query is waiting, not executing. `pg_stat_activity.wait_event`, `pg_locks`. A migration or a long transaction holding a lock.
7. **Resource / cache effects**: working set no longer fits in `shared_buffers`/RAM (buffer hit ratio dropped, `BUFFERS` shows reads instead of hits); noisy neighbour on shared storage; cloud IOPS/burst credits exhausted (very common on RDS/Azure gp2-style disks).
8. **Something did change**: an index was dropped/invalid (failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index), a Postgres minor upgrade, config change, an ORM library version upgrade changing the generated SQL.
Then fix the root cause, and add alerting on query latency from `pg_stat_statements`.

### 46. How would you shard a Postgres table by tenant? What breaks first - joins, sequences, or cross-shard transactions?
Approach: tenant_id is the **shard key**. A routing layer maps `tenant_id → shard` via a **lookup table/directory** (more flexible than `hash(tenant) % N`: lets you move a big tenant to its own shard, and adding shards doesn't reshuffle everything). Co-locate all of a tenant's tables on the same shard (every table carries `tenant_id`), so almost all queries are single-shard. Reference tables (countries, products) are replicated to every shard. Tools: **Citus** (distributed Postgres, does exactly this with `create_distributed_table('quotes', 'tenant_id')`), or app-level routing with multiple connection pools. Before sharding: vertical scaling, read replicas, partitioning, and archiving usually go a long way.
What breaks first:
- **Sequences**: break **immediately**: each shard's `SERIAL` produces 1, 2, 3 → duplicate IDs across shards; and when you move a tenant between shards, IDs collide. Fix: UUIDs (UUIDv7 for index locality), Snowflake-style IDs, or composite keys `(tenant_id, id)`.
- **Joins**: within one tenant, they keep working if data is co-located. **Cross-tenant** joins (admin dashboards, analytics, "all policies expiring this week across all tenants") break: they become scatter-gather queries in the app. Fix: send analytics to a warehouse via CDC.
- **Cross-shard transactions**: rare by design if the shard key is right (one tenant's operations stay on one shard); when needed you need 2PC or a saga, which you avoid. 
So in practice: **sequences break first** (on day 1), **cross-tenant queries/joins** are the ongoing pain, and cross-shard transactions you design out. Other pains: schema migrations across N shards, rebalancing hot tenants, uniqueness constraints that must be global (e.g. a globally unique email).

### 47. Read replicas introduce replication lag and your users see stale data after a write. How do you fix it without going back to a single primary?
This is the **read-your-writes** consistency problem. Options:
- **Route the user's reads to the primary for a short window after they write**: e.g. set a cookie/session flag or cache entry "user X wrote at T"; for the next N seconds (> typical lag), that user's reads go to the primary. Everyone else still reads replicas.
- **LSN-based / causal reads (most precise)**: after a write, get the primary's WAL position (`pg_current_wal_lsn()`), give it to the client (cookie/header/session). On a read, pick a replica that has replayed at least that LSN (`pg_last_wal_replay_lsn() >= lsn`), or wait briefly, or fall back to the primary.
- **Route by consistency need**: read-after-write paths and anything transactional (e.g. "show the quote I just saved", checkout) use the primary; listings, search, reports, dashboards use replicas.
- **Return the written data in the write response** so the UI doesn't need to re-read it immediately (optimistic UI).
- Reduce lag itself: monitor `replay_lag`, avoid huge transactions, right-size replicas. Synchronous replication (`synchronous_commit = remote_apply`) for a specific replica gives strong reads but makes writes slower and less available, so use it sparingly.

### 48. Design a schema for storing insurance quotes where the rating rules change over time but you must be able to reproduce any historical quote exactly. (Bitemporal / versioning question - very relevant to Aurora/Pulse.)
Principle: **a quote is an immutable record of the exact inputs + the exact version of the rules + the exact outputs.** Never reference "the current rules"; reference a specific, immutable version.
```sql
-- rating rules are versioned and never edited in place
CREATE TABLE rater_version (
  id            uuid PRIMARY KEY,
  product_code  text NOT NULL,
  version       int  NOT NULL,
  artifact_uri  text NOT NULL,      -- e.g. the generated module / workbook in blob storage
  artifact_hash text NOT NULL,      -- sha256 of the artifact: proves what ran
  effective_from timestamptz NOT NULL,   -- business validity (valid time)
  effective_to   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),   -- when it was published (transaction time)
  UNIQUE (product_code, version)
);

-- reference data (rate tables, factors) versioned the same way, or embedded in the rater artifact

CREATE TABLE quote (
  id              uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL,
  product_code    text NOT NULL,
  rater_version_id uuid NOT NULL REFERENCES rater_version(id),
  engine_version  text NOT NULL,          -- version of the code that executed the rater
  inputs          jsonb NOT NULL,         -- exact inputs as received (after validation)
  outputs         jsonb NOT NULL,         -- premium, taxes, breakdown
  status          text NOT NULL,          -- draft/quoted/bound/expired
  rated_at        timestamptz NOT NULL,   -- point in time used to pick the rater version
  created_at      timestamptz NOT NULL DEFAULT now()
);
-- re-quote / amendment = a NEW quote row (or quote_revision row) pointing to the previous one; never UPDATE a rated quote's inputs/outputs
```
To reproduce: load `rater_version` by ID, fetch the artifact, verify the hash, run with `inputs` → must equal `outputs`. Keep old artifacts forever (immutable blob storage with retention policy). Pin the runtime too (engine version / container image), since a library or Python upgrade can change float results.
**Bitemporal** part: **valid time** (`effective_from/to`: which rules *apply* to a policy effective on date X, e.g. a rate change for policies incepting after 1 April) vs **transaction time** (`created_at`: when *we* knew about it). That lets you answer both "what premium applies to a policy starting 1 May?" and "what would we have quoted on 10 March, given what we knew then?", even after a rule correction is published retroactively.
**Your story:** map it to Aurora/Pulse: how rater versions were stored and pinned per quote, and whether a quote stored the inputs/outputs snapshot.

### 49. How do you store an audit trail that satisfies "who changed what and when" without killing write performance?
Options, from simplest to most decoupled:
- **App-level audit table**: in the same transaction as the change, insert `(id, entity_type, entity_id, action, actor_id, request_id, changed_at, before jsonb, after jsonb / diff)`. Simple, and captures **who** (actor from the request context) and **why** (request ID, reason). Cost: one extra insert per write (append-only inserts are cheap). Keep it in a separate table with minimal indexes, partitioned by month.
- **DB triggers** writing to a history table: catches every change, including manual SQL. But triggers don't know the app user unless you pass it in (`SET LOCAL app.user_id = ...` and read `current_setting` in the trigger), and they add latency to every write.
- **CDC (Debezium/logical replication) → Kafka → audit store**: **zero overhead on the write path**, catches everything, asynchronous. Put actor info in a column on the row (`updated_by`) or a transaction-level marker so it shows up in the change stream. Audit store can be cheap append-only storage (a separate Postgres, ClickHouse, blob/Parquet, Azure Data Explorer).
- **Event sourcing**: the events *are* the audit trail. Powerful but a big architectural commitment; don't adopt it just for auditing.
Performance tricks: append-only, no updates; partition by time and archive old partitions to cold storage; store diffs instead of full snapshots for wide rows; minimal indexes (entity_id + time); write async where the regulatory requirement allows. For tamper-evidence (regulated/insurance): restrict write access (no UPDATE/DELETE grants on audit tables), immutable storage (WORM blob), or hash-chaining rows.

### 50. You need to bulk-insert 50M rows into Postgres nightly. Fastest correct approach?
**`COPY`**, not `INSERT`s. `COPY ... FROM STDIN` (psycopg 3 `cursor.copy()`, or asyncpg `copy_records_to_table`) streams rows in Postgres's bulk format and is 10–100× faster than row-by-row inserts or even `executemany`.
Correct full approach:
1. `COPY` into an **unlogged staging table** (no WAL → much faster; it's fine because staging can be reloaded if the DB crashes), with **no indexes/constraints**.
2. Validate / dedupe / transform in SQL on the staging table.
3. Merge into the real table in one set-based statement: `INSERT INTO target SELECT ... FROM staging ON CONFLICT (key) DO UPDATE ...` (or `MERGE` in PG15+). Or, if it's a full replace, build a new table and **swap** it in with a rename in a transaction, or **attach it as a partition** (`ALTER TABLE ... ATTACH PARTITION`), which is near-instant.
4. If loading directly into an empty table: create indexes **after** loading (one index build is much faster than 50M incremental updates), and drop/disable FK checks during the load, then validate.
5. `ANALYZE` afterwards so the planner has stats (Q45).
Tuning: increase `maintenance_work_mem` for index builds, `max_wal_size` to reduce checkpoints during the load, load in parallel chunks (e.g. by file or key range) with several connections, batch commits (e.g. per 1M rows, so a failure doesn't redo everything). Make the job **idempotent** (re-running the night's load produces the same result) and watch replication lag on replicas.

### 51. Explain the difference between a materialized view, a summary table maintained by triggers, and a scheduled aggregation job. Pick one for a dashboard - why?
- **Materialized view**: a query whose result is stored on disk. `REFRESH MATERIALIZED VIEW` recomputes **the whole thing** (Postgres has no incremental refresh natively); `REFRESH ... CONCURRENTLY` (needs a unique index) lets reads continue during the refresh. Simple, declarative. Data is stale between refreshes; the refresh cost grows with total data size.
- **Summary table maintained by triggers**: every insert/update on the base table updates the aggregate row immediately. Always **real-time**, but adds latency to every write, and creates **hot-row lock contention** (every order updating the same "today's total" row serialises writes), plus logic hidden in triggers is hard to debug and test.
- **Scheduled aggregation job** (cron/Celery/Airflow): your code computes aggregates and upserts them into a summary table. Can be **incremental** (only process rows since the last watermark), handles complex logic, retries, monitoring. Staleness = schedule interval. More code to own.
For a dashboard: usually a **scheduled incremental aggregation job** (or a materialized view refreshed concurrently every few minutes if the data is small and the query simple). Dashboards tolerate minutes of staleness, and you don't want to tax the write path with triggers. Trigger-based only when you truly need real-time numbers and the write rate is low. At large scale, move it to an OLAP store (ClickHouse, BigQuery, Azure Data Explorer) fed by CDC.

### 52. How would you implement soft deletes without destroying every index in the system?
Soft delete = `deleted_at timestamptz NULL` instead of `DELETE`. Problems: every query must remember `WHERE deleted_at IS NULL`, deleted rows bloat indexes and make them less selective, and **unique constraints break** (you can't recreate a user with the same email because the soft-deleted row still holds it).
Fixes:
- **Partial indexes**: `CREATE INDEX ... ON quote (tenant_id, created_at) WHERE deleted_at IS NULL;` Indexes only contain live rows, so they stay small and fast.
- **Partial unique indexes**: `CREATE UNIQUE INDEX ON users (email) WHERE deleted_at IS NULL;` → uniqueness only among live rows.
- Make the filter automatic: a view (`active_quotes`), Postgres RLS policy, or an ORM-level global filter (SQLAlchemy `with_loader_criteria` / a custom query class), so developers can't forget it.
- If soft-deleted rows are rarely read, **move them to an archive table** (`quote_deleted`) on delete (trigger or app code). The main table stays clean, and you keep the data for audit/restore.
- Remember GDPR "right to erasure": soft delete is not deletion; you may need a hard-delete/anonymisation job after the retention period. And FKs: decide what happens to children of a soft-deleted parent.

### 53. JSONB in Postgres: when is it right, and what index do you need for containment queries? When does it become an anti-pattern?
Right for: genuinely **variable/semi-structured** data, such as per-product rating inputs that differ by line of business, raw payloads from external APIs/webhooks (store as received), extracted document fields (Orbit/Ayana extraction results), user preferences/settings, event metadata. Good when you mostly read/write the blob as a whole and filter on a few keys.
Indexes:
- **GIN index** for containment `@>` and key-existence `?` queries: `CREATE INDEX ON quote USING gin (inputs);` supports `WHERE inputs @> '{"state": "TX"}'`. Use the **`jsonb_path_ops`** operator class (`USING gin (inputs jsonb_path_ops)`) when you only need `@>`: it's smaller and faster.
- **B-tree expression index** for one specific key used for equality/range/sort: `CREATE INDEX ON quote ((inputs->>'state'));` or `((inputs->>'sum_insured')::numeric)`. Often better than GIN when you always query the same key.
- Or a **generated column** (`GENERATED ALWAYS AS (inputs->>'state') STORED`) with a normal index.
Anti-pattern when: you put **core, always-present, relational fields** in JSONB (no type safety, no constraints, no FKs, the planner has no statistics on keys inside JSONB → bad row estimates and bad plans); you frequently **update single keys** in big documents (Postgres rewrites the whole value, and big values get TOASTed); you join on JSONB fields; or you use it to avoid schema design ("we'll just put it in a JSON column"). Rule: if you query it, filter on it, or every row has it → make it a real column.

---

## F. THE CELLULAR PROBLEM - EXCEL -> PYTHON TRANSPILER (tailored, high signal)

> These are about your own system. Below is a strong reference answer for each. Before an interview, go through them and note where Cellular actually did something different. "We did X because of constraint Y; ideally I'd do Z" is a great answer. Bluffing a design you didn't build is not.

### 54. Design it from scratch on the board: given an .xlsx rater workbook, produce a Python module exposing `rate(inputs) -> outputs`. Cover: parsing, dependency graph, codegen, and the public API.
**Pipeline**: `xlsx → parse → model (cells + formulas + names) → formula AST → dependency graph → prune → codegen → generated module + metadata → tests → publish`.
1. **Parsing**: `openpyxl` reads cells, formulas (as strings), cached values (with `data_only=True` for the last-calculated values, which you use as test oracles), defined names, data validations (dropdowns = allowed input values), and sheet structure. Parse each formula string into an **AST** with a proper Excel formula grammar (tokenizer like `openpyxl.formula.Tokenizer`, or a Lark/pycel/formulas-library parser): function calls, operators with Excel precedence, references (`A1`, `$A$1`, `Sheet2!B3:D10`, named ranges, whole columns).
2. **Contract**: define which cells are **inputs** and which are **outputs**. Best done by a convention/config agreed with the actuaries/underwriters: a named range per input/output (`in_sum_insured`, `out_premium`) or an "Inputs"/"Outputs" sheet, plus types/allowed values from data validation. This becomes the API schema.
3. **Dependency graph**: nodes = cells (and ranges); edges = "formula of X references Y". Build it from the ASTs. Then **prune**: keep only the cells reachable backwards from the outputs (real raters have thousands of cells that are notes, scratch calculations or other products). Constants that never depend on inputs are **folded** to literal values at build time.
4. **Codegen**: topologically sort the remaining formula cells and emit Python: each cell becomes an expression/assignment, Excel functions map to a **runtime library** (`xl.VLOOKUP`, `xl.ROUND` with Excel semantics, error values, etc.). Lookup tables become constant data structures (dicts/tuples, or separate data files).
5. **Public API**: `rate(inputs: RaterInputs) -> RaterOutputs` with Pydantic models generated from the input/output contract (types, enums from dropdowns, required/optional), plus `METADATA = {workbook_hash, rater_version, generated_at, generator_version}`. Pure function: no I/O, no globals, deterministic. Then served behind an API (FastAPI / Azure Function) that loads the right version.
6. **Verification**: run the generated module against the workbook's own cached values plus a corpus of test cases evaluated by real Excel (Q62). Publish only if it passes.
**Your story:** walk through what Cellular actually did at each step: the parser you used, how inputs/outputs were identified, whether you generated source code, and how the module was exposed via Azure (Functions? an API?).

### 55. How do you build the cell dependency graph, and how do you evaluate it? Topological sort vs lazy memoized evaluation - which and why?
**Build**: for each formula cell, walk its AST and collect references; expand ranges to cells (or, for huge ranges, keep a range node that depends on its cells, to avoid millions of edges); resolve named ranges and cross-sheet references to fully qualified addresses (`Sheet!A1`). Edges go precedent → dependent. Dynamic references (`OFFSET`, `INDIRECT`) can't be resolved statically: either make them depend on the whole possible range (conservative) or treat them specially (Q60).
**Evaluate**:
- **Topological sort** (Kahn's algorithm): compute an order once at build time where every cell comes after its precedents, then evaluate in that order. Detects cycles for free (nodes left over = cycle). It's **ideal for codegen**: the topo order *is* the order of the generated statements, so generated code is straight-line, fast, readable, with no runtime graph. Downside: evaluates every reachable cell even if a branch isn't needed (e.g. both branches of an `IF`).
- **Lazy memoized evaluation**: `evaluate(cell)` recursively evaluates its precedents on demand, caching results. Only computes what's needed (skips the untaken `IF` branch, which also matches Excel's lazy `IF` semantics: an error in the untaken branch doesn't propagate). Handles dynamic references naturally because it resolves them at runtime. Downside: recursion depth issues on long chains, runtime overhead per call, harder to generate as clean code.
**Which**: **topological order for codegen** (static, fast, auditable), with **lazy semantics preserved inside expressions**: `IF`, `IFERROR`, `CHOOSE`, `AND/OR` compile to Python conditional expressions so the untaken branch isn't evaluated. Fall back to lazy/interpreted evaluation only for the dynamic-reference subgraphs. That's the best answer.

### 56. How do you handle circular references and Excel's iterative calculation setting?
**Detect**: find cycles in the dependency graph with Tarjan's **strongly connected components** (SCCs). Each SCC with >1 node (or a self-reference) is a cycle.
**Policy**:
- If the workbook does **not** have iterative calculation enabled, a cycle is a bug in the workbook (Excel shows a warning and the values are garbage/0) → **fail the build** with a clear error naming the cells, and send it back to the rater owner.
- If iterative calculation **is** enabled (common in insurance for things like "premium includes a commission that's a percentage of premium", or tax-on-tax): read the workbook's settings (`calcPr` in `workbook.xml`: `iterate`, `iterateCount` default 100, `iterateDelta` default 0.001). Generate code that treats each SCC as a unit: evaluate the cycle cells repeatedly in a fixed order (starting from the cached/initial values, typically 0), until the max change is < `iterateDelta` or `iterateCount` iterations is reached, exactly as Excel does. The rest of the graph stays topologically sorted around the condensed SCC.
- Even better: when the cycle is a simple algebraic loop (`premium = base + premium * 0.1`), work with the business to **rewrite it in closed form** (`premium = base / 0.9`) for exactness. Iterative results can differ slightly from Excel because Excel's iteration order depends on its internal calc chain, so verify against Excel's output with a tolerance and document it.

### 57. Excel's numeric semantics differ from Python's - 1900 leap year bug, float display rounding, implicit type coercion of "" and TRUE, blank vs zero. How do you get bit-identical outputs?
You implement a **runtime library that emulates Excel's semantics**, not Python's, and test it against real Excel.
- **Dates**: Excel stores dates as serial numbers with the **1900 leap-year bug** (Excel thinks 29 Feb 1900 existed; serial 60). Convert serials with that quirk (day 1 = 1900-01-01; serials > 60 are offset by one). Also check the workbook's **1904 date system** flag. Implement date functions (`DATE`, `EDATE`, `YEARFRAC`, `DATEDIF`, `NETWORKDAYS`) to Excel's exact rules (`YEARFRAC` basis conventions are notoriously tricky).
- **Floats**: both use IEEE 754 doubles, so basic arithmetic matches bit for bit. Differences: Excel **displays/compares with 15 significant digits** and does some "close to zero" snapping (e.g. `=1*(0.5-0.4-0.1)` can show 0 while Python gives `-2.7e-17`). Implement **`ROUND` the Excel way** (round half **away from zero**, applied on a decimal representation) because Python's `round()` uses banker's rounding and binary floats (`round(2.675, 2) == 2.67` in Python, 2.68 in Excel). Using `Decimal(repr(x))` / `decimal.ROUND_HALF_UP` in the `ROUND` implementation is the usual trick. Also `MOD` with negatives, `INT` (floors toward −∞), integer division, `^` precedence (in Excel `-2^2 = 4` because unary minus binds tighter).
- **Coercion**: in arithmetic `TRUE → 1`, `"" → #VALUE!` (when it's a literal string in a formula, e.g. `="" + 1`), numeric strings `"3" + 1 = 4`, but in `SUM(range)` text and booleans in the range are **ignored** while `SUM("3", TRUE)` as direct arguments counts them. Comparisons are case-insensitive for text, and type ordering is `numbers < text < booleans`.
- **Blank vs zero vs empty string**: a **blank** cell is 0 in arithmetic, `""` in string context, ignored by `AVERAGE`/`COUNT`; a cell containing `""` (from a formula) is text, so `COUNTA` counts it and `ISBLANK` is FALSE. So you need a distinct **`BLANK` sentinel type**, not `None`/0.
Bit-identical in practice: define the target as "matches Excel's stored value exactly for integers/strings/booleans, and within 1 ulp or to the cent for monetary outputs after the workbook's own `ROUND`". Rater outputs are almost always rounded in the workbook, which makes exact matching achievable. And prove it with differential testing (Q62).

### 58. How do you implement Excel error propagation (#N/A, #DIV/0!, #VALUE!) in Python such that it flows through arithmetic the way Excel does?
Model errors as **values**, not Python exceptions, because in Excel an error is a value that flows through the graph and can be caught by `IFERROR`/`ISNA`, and a cell holding an error doesn't stop other cells from computing.
```python
class XlError:
    __slots__ = ("code",)
    def __init__(self, code): self.code = code
    def __repr__(self): return self.code

NA, DIV0, VALUE, REF, NAME, NUM, NULL = (XlError(c) for c in
    ("#N/A", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#NULL!"))

def xl_div(a, b):
    a, b = to_number(a), to_number(b)       # returns an XlError on bad coercion
    if isinstance(a, XlError): return a      # first error wins, left to right
    if isinstance(b, XlError): return b
    if b == 0: return DIV0
    return a / b
```
Rules to implement: every operator and function checks its arguments and **returns the first error** it encounters (left-to-right, matching Excel's evaluation order). Functions differ: `SUM(range)` returns the first error in the range; `IFERROR(x, alt)` / `IFNA` / `ISERROR` / `ISNA` / `ERROR.TYPE` **consume** errors; `IF(cond, a, b)` only propagates an error from the branch actually taken (so the codegen must be lazy there, see Q55); lookups return `#N/A` on no match; `AGGREGATE` can ignore errors. Python exceptions (`ZeroDivisionError`, `ValueError`) must be caught inside the runtime functions and converted to the right Excel error. If an **output** cell ends up as an error, the API returns a structured domain error ("rater returned #N/A for premium: likely an input outside the rate table") rather than a 500.
Alternative: operator overloading via wrapper number types. Cleaner generated code, but slower and leakier; explicit runtime functions are more predictable.

### 59. Array formulas / dynamic arrays / spill ranges - how do you model those?
- **Legacy array formulas (CSE, `{=SUM(A1:A10*B1:B10)}`)**: a formula evaluated element-wise over ranges, producing either a single value or an array written to a fixed block of cells. Model ranges as **2D arrays** (list of lists, or numpy arrays for performance) and implement element-wise broadcasting of operators with Excel's rules (row × column broadcast, mismatched sizes produce `#N/A` in the extra cells).
- **Dynamic arrays (Excel 365: `FILTER`, `SORT`, `UNIQUE`, `SEQUENCE`, `XLOOKUP` returning arrays)**: one formula in an anchor cell **spills** into neighbouring cells, and the spill size depends on the data at runtime. Other formulas refer to it with `A1#`. Model: the anchor cell's value is an **array**; the spilled cells are virtual "views" into it (`cell(r,c) = anchor_value[r-r0][c-c0]`). In the dependency graph, anything referencing a cell inside the possible spill area or `A1#` depends on the **anchor**. If the spill size can vary with inputs, the codegen can't treat spilled cells as fixed variables, so they must be resolved through the anchor at runtime. `#SPILL!` occurs if the spill area would overlap non-empty cells.
- In the file, `openpyxl` exposes array formulas (`ArrayFormula` with its `ref` range); dynamic-array formulas are stored with `_xlfn.`/`_xlws.` prefixes and a `cm` metadata attribute. So the parser must recognise those.
Practical answer: support CSE and the common dynamic functions; for anything unsupported, **fail the build loudly** listing the cell and function, rather than generating wrong code.

### 60. How do you represent a cell reference and a range so that functions taking references (OFFSET, INDIRECT, VLOOKUP) still work after codegen?
Most functions just need **values**: pass the evaluated value (scalar or 2D array). But some functions need the **reference itself**, not its value: `OFFSET(A1, 2, 3)`, `INDIRECT("Rates!B" & row)`, `ROW()`, `COLUMN()`, `CELL`, `INDEX` returning a reference, `SUM(A1:INDEX(...))`. So the runtime needs a **reference type**:
```python
@dataclass(frozen=True)
class Ref:
    sheet: str
    row1: int; col1: int
    row2: int; col2: int       # single cell when row1==row2 and col1==col2
```
and a **workbook-state object** the generated code can resolve references against at runtime: `ctx.value(ref)` returns the value (scalar or 2D array) for a Ref. Codegen passes `Ref` objects to reference-taking functions and plain values to everything else (decided at compile time by a function signature table: which args are "by reference").
- **VLOOKUP/HLOOKUP/INDEX/MATCH/XLOOKUP**: usually over **constant lookup tables** → compile the table to a constant 2D array and pass that. Optimise exact-match lookups into dicts at build time (Q63), and implement approximate match (`TRUE`/omitted 4th arg = sorted range, finds largest value ≤ key) exactly like Excel, since rating tables use bands a lot.
- **OFFSET**: compute a new `Ref` from the base Ref + offsets, then resolve it. Its target is dynamic, so in the dependency graph it conservatively depends on the whole region it could address (or the whole sheet).
- **INDIRECT**: parse the string at runtime into a Ref. It's statically opaque, so either (a) constant-fold it if its argument is constant at build time (common!), (b) depend on the whole referenced sheet, or (c) reject it and ask the rater author to use `INDEX`/`CHOOSE` instead. Volatile functions also break caching, so reducing them is a win.
To support runtime resolution, the generated module needs access to the values of all cells that might be referenced dynamically, so keep those cells (and the constant sheets) in the generated data, not pruned.

### 61. Codegen strategy: emit Python source, build an AST, or build an interpreter over an IR? Argue all three, then pick.
- **Emit Python source text** (templates/string building): generated `.py` files that people can **read, diff, review, step through in a debugger, and version in git**. Runs at native CPython speed after import; easy to ship as a package. Downsides: string building is error-prone (quoting, escaping, name collisions), huge workbooks produce huge files (CPython has limits on function size / nesting and compile time), and changing the generated code means regenerating everything.
- **Build a Python AST** (`ast` module, then `compile()`): same runtime speed as source, but **correct by construction** (no quoting/escaping bugs) and you can still `ast.unparse()` it to get readable source for audit and diffs. Slightly more verbose to write the generator. Basically "source codegen done safely".
- **Interpreter over an IR**: parse into an intermediate representation (the graph + formula ASTs serialised as JSON) and ship a **generic evaluator** that walks it at runtime. No codegen at all: a new workbook version is just new **data**, not new code, so no deploy, no code-injection risk, and one engine to test and harden. Easy to add tracing ("explain this premium" by logging every node's value). Downsides: slower (interpretive overhead per node, maybe 10–50×), and less readable for a human than generated Python.
**Pick**: **AST → compile, and `ast.unparse` the result into a readable, versioned source artifact** for audit and debugging. Strong alternative is the IR interpreter if workbooks change very frequently, performance isn't critical, and you want "upload and go live without deploy" (you can also do both: the IR is the canonical artifact, compiled to Python as an optimisation). For a regulated domain, readable generated code + the original workbook hash is very strong evidence for auditors.
**Your story:** say which one Cellular actually used and the trade-off you felt (e.g. file size, debugging, deploy cadence).

### 62. How do you test this? Design a differential-testing harness against real Excel / LibreOffice across 500 workbooks. What's your pass criteria and how do you handle floating point?
**Differential testing**: the oracle is Excel itself. For each workbook, generate many input vectors, compute outputs with Excel and with the generated module, compare.
1. **Corpus**: the 500 real workbooks (anonymised if needed) + synthetic micro-workbooks, one per supported function / edge case (blank handling, errors, date quirks, rounding).
2. **Input generation**: from the input contract: boundary values, every dropdown option, values at rate-table band edges (e.g. sum insured exactly 100000, 100000.01, 99999.99), empty/optional inputs, plus random sampling and **property-based** generation (Hypothesis, Q74). Maybe 50–500 vectors per workbook.
3. **Oracle runs**: real **Excel** (the ground truth, since raters are authored and signed off in Excel) driven on a Windows box via COM/`xlwings` or the Excel Online/Graph API (`workbook/application/calculate`), writing inputs, recalculating, reading outputs. **LibreOffice headless** is cheaper and runs in Linux CI, but it has its own differences from Excel, so it's a secondary oracle, never the final word. Cache the oracle results keyed on `(workbook hash, input hash)`; Excel runs are slow.
4. **Compare** outputs cell by cell: strings, booleans and error codes must match **exactly**; numbers **exactly** when the output is rounded in the workbook (monetary outputs), otherwise with a tolerance like `abs(a-b) <= max(1e-9 * |b|, 1e-12)` (relative + absolute), or "equal after rounding to 15 significant digits", which is Excel's own precision. Never a tolerance on currency: premium must match to the cent.
5. **Pass criteria**: a workbook version is publishable only at **100% match** on its test suite. Any mismatch blocks publication and produces a report: which output, which inputs, the expected vs actual, and the **first divergent intermediate cell** (compare intermediate cells too, to localise bugs quickly). Track a corpus-wide pass rate as the engine's health metric over time, and add every bug found as a permanent regression case.
6. Run the whole corpus in CI on every change to the transpiler/runtime library, since a change to the `ROUND` implementation can break 200 workbooks at once.

### 63. Performance: a rater is called 10,000 times/minute with different inputs. What do you precompute, cache, or JIT?
10k/min ≈ 170 req/s. Very doable; the trick is doing **nothing at request time that could be done at build time**.
**Precompute at build/import time**:
- **Constant folding**: everything not dependent on inputs (often 70–90% of a rater: rate tables, factors, derived constants) is computed once at codegen, so it's a literal in the generated code.
- **Prune** all cells not on a path from inputs to outputs.
- **Lookups → hash maps**: exact-match `VLOOKUP`/`MATCH` over constant tables become dict lookups (O(1) instead of scanning); approximate-match band lookups become `bisect` over a sorted list (O(log n)).
- Load and import each rater version **once per process** (module cache keyed on version), never per request. Generated code is plain Python with local variables, with no graph walking at runtime.
**Cache**: results keyed by `(rater_version, hash(canonical inputs))`, in-process LRU and/or Redis, useful because brokers re-quote the same risk many times; safe because `rate()` is a pure function of (inputs, version). Partial caching of input-dependent but rarely-changing sub-results (e.g. the territory-factor subtree depends only on postcode) if profiling shows it matters.
**JIT / faster execution**: profile first. Most raters are scalar branchy logic where interpretive overhead is low after codegen; numba/Cython help only for numeric loops / array formulas. Vectorise with numpy when **batch rating** (pricing 10k variants of a portfolio at once). PyPy is an option for pure-Python heavy code. Horizontal scale: pure function → stateless workers, scale on CPU.
Measure with a load test (locust) and report p50/p99 per rater version; the slowest rater is usually one with a huge `SUMPRODUCT`/array formula, so optimise those specifically.

### 64. A business user uploads a new version of the workbook. How do you version, diff, validate, and roll out the regenerated module safely?
1. **Version**: store the uploaded file immutably (blob storage, content hash = identity), assign `product + version number`, record uploader and change note. Regenerate the module; the artifact is tagged with workbook hash + generator version.
2. **Diff**: show a **semantic diff**, not a binary one: inputs/outputs contract changed? (added/removed/renamed input → API breaking change!), which formulas changed (cell, old formula, new formula), which constants/rate-table values changed, which named ranges moved. Also a **behavioural diff**: run the test corpus (and a sample of real historical quotes) through old and new versions and report which outputs changed and by how much ("premium changed for 12% of test cases; max +4.2%; all in territory band 3"). Business confirms that the changes are the **intended** ones.
3. **Validate**: structural checks (no unsupported functions, no unexpected circular refs, contract compatible), differential test vs Excel (Q62) must pass 100%, plus business-defined assertions/smoke cases with known expected premiums signed off by the actuary/underwriter.
4. **Approve**: a maker-checker step: the person who uploaded can't approve; record the approval (audit trail, regulated pricing change).
5. **Roll out**: publish as a new version **alongside** the old one (never overwrite). Activation by **effective date** (the rate change applies to quotes with inception ≥ date X; Q48), optionally **shadow mode** first (compute the new version in parallel on live traffic, log differences, return the old result), then a flag/percentage rollout per tenant/broker. Existing quotes stay pinned to the version that produced them.
6. **Rollback**: switching the active version back is a config change, instant, no deploy.
**Your story:** describe how a rater update actually went live in Cellular / Pulse (ADO pipeline triggered by upload? manual review? who signed off?).

### 65. Now the LLM-agent version: you replaced this with an agent. How do you keep determinism and auditability when a regulator asks "why was this premium 4,312?"
Key principle: **the LLM must never compute the premium at request time.** LLMs are non-deterministic and can't be audited at the arithmetic level. Use the agent as a **build-time tool** (to understand/convert the workbook) and keep the **runtime calculation deterministic code**.
Good design:
- The agent's job is to **produce an artifact**: it reads the workbook, writes/updates Python rating code (or the IR), generates test cases and documentation. That artifact then goes through **exactly the same gate** as the transpiler output: differential tests against Excel (Q62), human code review, approval, versioning (Q64). Once approved it's frozen and hashed. The runtime path is `rate(inputs)` on frozen code: same inputs → same output, every time.
- Where the agent participates at runtime at all (e.g. mapping a messy submission email to structured rater inputs), it only does **extraction**, the output is validated against the input schema and shown to a human/underwriter for confirmation, and the extracted inputs are **stored** with the quote. The premium is still computed by deterministic code.
- If LLM output must be reproduced: pin the model **version** (not an alias), temperature 0, record the full prompt, tools, retrieved context, raw response and token usage per call. Note that even temperature 0 isn't guaranteed bit-identical across runs/providers, which is exactly why you store outputs rather than relying on re-running.
**Answer to the regulator**: "Quote Q was produced at time T by rater version V (artifact hash H, approved by person P on date D, effective from E), with these exact stored inputs. Re-running V on those inputs reproduces 4,312. Here's the calculation trace: base rate from table row X = …, × territory factor 1.15, × claims-loading …, + tax …" To provide that, the runtime should be able to emit an **explanation trace** (each intermediate named value), which is straightforward with generated code or an IR interpreter (Q61).
**Your story:** be honest about how the agent you built at Espire actually worked (did it compute at runtime or generate code?), and if it computed at runtime, say how you'd harden it as described above.

---

## G. DOMAIN-SHAPED BACKEND DESIGN (from his actual work)

> Same note as section F: these are reference designs. Line them up against what you actually built and be ready to say what you'd change.

### 66. Design the email-ingestion service for Orbit/Ayana: Graph/IMAP polling, dedupe, attachment extraction, ordering, retries, and per-tenant isolation. What's the hardest part?
**Ingestion**: prefer **Microsoft Graph change notifications (webhooks)** on each mailbox for low latency, **plus delta-query polling** (`/messages/delta` with a stored `deltaLink` per mailbox) as the reliable backbone, since webhooks can be missed and subscriptions expire (max ~3 days for mail, so a renewal job is needed). IMAP (with `UIDVALIDITY` + last UID per folder) only for non-M365 tenants. Auth per tenant via app registration with admin consent / application access policy restricting which mailboxes the app can read. Webhook handler does nothing except validate and enqueue the message ID (respond fast, Graph retries otherwise).
**Pipeline** (queue between each stage: Service Bus / storage queue):
1. **Fetch** full message + MIME by ID → store **raw `.eml` immutably in Blob** (raw zone; enables replay, Q34) → record metadata row.
2. **Dedupe**: same email can arrive via webhook and delta, via retries, or as the same message in multiple mailboxes (shared inbox + CC). Key on `(tenant, mailbox, Graph immutable ID)` with a unique constraint, plus `internetMessageId` (RFC 5322 Message-ID) for cross-mailbox duplicates, plus a content hash for attachments. Use immutable IDs (`Prefer: IdType="ImmutableId"`), because normal Graph IDs change when a mail is moved between folders.
3. **Attachment extraction**: handle nested emails (`.msg`/`.eml` inside emails), zips, inline images, PDFs (text layer vs scanned → OCR / Azure Document Intelligence), Excel/Word. Virus scan before processing. Store each attachment in Blob with a hash.
4. **Classification and information extraction** (LLM / Document Intelligence): what kind of email (new business submission, renewal, endorsement, claim, chaser), extract fields → structured submission → kick off the onboarding workflow.
**Ordering**: global ordering doesn't matter; per **conversation/thread** it does (a "please ignore the previous submission, updated schedule attached" follow-up must apply after the original). Group by `conversationId` and process per conversation sequentially (Service Bus **sessions** keyed by conversation ID give you FIFO per key with parallelism across keys), and use `receivedDateTime` + versioning so a late-arriving older email doesn't overwrite newer state.
**Retries**: each stage idempotent; retries with backoff; Graph throttling (429 with `Retry-After`, per-mailbox and per-tenant limits) must be respected; poison messages → dead-letter queue with an alert and a "reprocess" button.
**Per-tenant isolation**: separate credentials per tenant (Key Vault), tenant ID on every record and blob path (or separate containers/storage accounts per tenant), per-tenant concurrency limits so one broker's 5,000-email backlog doesn't delay everyone (fair queuing, Q93), PII handling and retention policies per tenant.
**Hardest part**: honestly, it's **not** the plumbing. It's (a) the **messiness of real email content** (forwarded chains, replies quoting old submissions, attachments that are photos of documents, information split across emails) for reliable extraction, and (b) **exactly-once business effect**: making sure one real-world submission creates exactly one piece of new business despite duplicates, forwards and follow-ups. A close third: Graph subscription lifecycle and throttling at scale.
**Your story:** say which of these Orbit actually did (polling vs webhooks, where dedupe happened, what broke most often).

### 67. Design policy document generation at scale: templated PDFs, 50-page docs, spikes at month end, must be reproducible and immutable once issued.
**Architecture**: API receives "generate document for policy P, version V" → writes a job row → enqueues → **autoscaled worker pool** renders → stores PDF → updates job → notifies (Q30).
**Templating**: versioned templates (HTML/Jinja + CSS rendered with **WeasyPrint**/headless Chromium/Playwright, or DOCX templates via `docxtpl` → converted to PDF with LibreOffice/Gotenberg; dedicated engines for heavy layouts). Templates are versioned exactly like rater versions: each document records the template version used. Clauses/wordings pulled from a versioned clause library.
**Reproducible**: a document is a pure function of **(data snapshot, template version, clause versions, renderer version, fonts/assets)**. So: snapshot the exact data (policy + quote + inputs) as JSON at issuance and store it; pin the renderer in a container image; embed fonts (no system font dependency); never fetch "live" data while rendering (no `now()`; pass the issue date in). Then regenerating gives the same content (byte-identical PDFs are hard because PDFs embed timestamps/IDs; set those deterministically or define reproducibility as "same content", and keep the original file anyway).
**Immutable once issued**: store the issued PDF in Blob with **immutability policies (WORM / legal hold)** and versioning, record its **SHA-256** in the DB, optionally digitally sign the PDF. Any change after issuance is an **endorsement** that produces a *new* document version; the old one is never overwritten.
**Month-end spikes**: queue absorbs the spike; workers autoscale on **queue depth** (KEDA on Service Bus / Azure Functions premium / Container Apps); priority queues (an interactive "broker is waiting for this one now" job beats a batch renewal run); pre-generate batch work (renewals) ahead of month end where the business allows; rendering is CPU/memory heavy (headless Chrome), so cap concurrency per pod and size pods accordingly. Cache shared assets/static pages.
**Ops**: idempotent jobs keyed on `(policy, version, doc_type)`, retries with DLQ, rendering timeout, metrics on render time per template, a visual regression test for templates (render known fixtures and diff images/text) in CI.

### 68. Design the resume-ingestion pipeline from the Jio ATS again, but for 1M/day instead of 100k. What changes?
Numbers first: 1M/day ≈ **12/s average**, peaks maybe 5–10× (campus drives, job-post deadlines) → design for **~100–150/s peak**. 100k/day was ~1.2/s. Storage: at ~200KB per resume → ~200GB/day raw.
What changes:
- **Ingestion**: uploads go **directly to blob storage via SAS URLs**, not through the API pods; a blob-created event (Event Grid) enqueues processing. API stays thin.
- **Queue/workers**: Celery + Redis broker may struggle on durability and visibility at this volume → move to a durable broker (Kafka / Service Bus / RabbitMQ quorum queues), split into stages (parse → extract → embed → match → index) each with its own queue and **independently autoscaled** workers (KEDA on queue depth), so the slow stage (OCR, LLM/ML extraction) doesn't block the fast ones.
- **The ML/parsing step becomes the bottleneck and the cost driver**: batch inference on GPUs, a model server (Triton / vLLM / managed endpoint) instead of loading models in Celery workers, dedupe before expensive work (hash of file and normalised text: the same candidate uploads the same CV to 20 jobs → parse once, match 20 times).
- **Storage**: MongoDB needs sharding (by candidate ID) or move search/matching to a dedicated engine: **Elasticsearch/OpenSearch or a vector DB** for candidate search and semantic matching, instead of querying Mongo. Lifecycle policies on blobs (cool/archive tiers for old resumes).
- **Matching**: from "match each resume against all open jobs" (N×M explodes) to **retrieval-then-rank**: embed resumes and jobs, ANN search for top-k candidates, then a precise scoring model on just those.
- **Reliability**: idempotency per resume, DLQ for unparseable files, backpressure, rate limits per tenant/company in the RIL group, replay from raw blobs.
- **Observability and cost**: per-stage throughput/latency/error dashboards, cost per resume as a tracked metric.
- **Compliance**: PII at 10× scale: encryption, retention/deletion policies, access audit.
What doesn't change: the overall shape (upload → async pipeline → results). 10× usually means "make each stage independently scalable and remove the shared bottleneck", not a rewrite.
**Your story:** state what the real 100k/day system's bottleneck was (parsing? ML model? Mongo writes?) and how many workers/pods it took. Interviewers will ask you to defend the 100k number.

### 69. Design a crawler control plane (DataWeave): scheduling, politeness, proxy rotation, dedupe, change detection, and "silently returning garbage" detection.
**Control plane vs data plane**: the control plane decides **what to crawl, when, and how** (stored in Postgres: sites, URL frontier, schedules, configs, proxy pools, job state). The data plane is a pool of stateless fetcher/parser workers pulling from queues (Kafka/RabbitMQ), storing raw HTML to S3 and parsed records to the warehouse.
- **Scheduling**: each URL/product has a crawl frequency based on priority and how often it changes (adaptive: pages that change often get crawled more; stable pages less). A scheduler computes `next_crawl_at` and pushes due URLs into queues **partitioned by domain**. Respect client SLAs (e.g. "prices for these 50k SKUs refreshed every 6 hours").
- **Politeness**: per-domain rate limit and concurrency (token bucket in Redis per domain, Q26), respect `robots.txt` and crawl-delay, crawl during off-peak hours, back off on 429/503, randomised but bounded request spacing. Per-domain queues make this natural.
- **Proxy rotation**: a pool of proxies (datacenter/residential, per geography since prices differ by region) with health scores: success rate, latency, block rate per (proxy, domain). Pick proxies weighted by health, retire/cool-down proxies that get blocked, sticky sessions where the site needs cookies, rotate user agents/headers consistently with the proxy. Headless browser (Playwright) only for JS-heavy sites since it's ~10× costlier.
- **Dedupe**: URL normalisation (lowercase host, strip tracking params, sort query params, canonical link tag) + hash; content dedupe by hash of the extracted fields (or SimHash for near-duplicate pages); product-level dedupe across URL variants.
- **Change detection**: hash the **extracted structured data** (price, stock, title), not the raw HTML (ads, timestamps and CSRF tokens change every load); store only deltas/new versions; emit change events (price drop) downstream; feed change frequency back into scheduling.
- **"Silently returning garbage" detection** (the most important part and the one most people miss): the site returns 200 OK but with a captcha/blocked page, a geo-redirect, a "default" price, an empty listing, or the layout changed and selectors now grab the wrong element. Detect with:
  - **Schema/data validation** on extracted records: required fields present, types, price within plausible range, currency correct.
  - **Statistical checks per site/run**: extraction success rate, field null rates, number of products per category page, distribution of prices compared to the previous run (e.g. 40% of prices changed by > 50% → almost certainly a parser problem, not a market event). Alert and **quarantine** the batch instead of publishing it.
  - **Page fingerprints**: detect block/captcha pages by known markers, response size anomalies, page title.
  - **Canary/golden URLs**: known pages with known values crawled every run; if their values come out wrong, the parser is broken.
  - Keep raw HTML so you can re-parse after fixing selectors (replay, Q34).
**Your story:** this is your DataWeave centralised crawler. Talk about the actual scale (sites, URLs/day), what the stack was (Kafka, Lambda, S3, Athena, Qubole), and a real "garbage data" incident if you have one.

### 70. Design the task claim/lock system from the RLHF dashboard properly, assuming Redis can lose data. What are the correctness requirements and what do you give up?
**Requirements**: (1) **mutual exclusion**: a task is worked on by at most one annotator at a time, or at least only one annotator's submission is accepted; (2) **liveness**: a task claimed by someone who closes their laptop must become available again (lease expiry); (3) **no lost work**: a submitted annotation is never silently dropped or overwritten; (4) fair distribution / no duplicate effort (nice to have).
**Why Redis alone isn't enough**: Redis replication is asynchronous; a failover can lose the latest `SET NX` → two annotators both "hold" the lock. Redlock across several Redis nodes is debated (Kleppmann vs antirez) because of process pauses and clock assumptions; with GC pauses or network delays a lock holder may still act after its lease expired. So: **a lock is a performance optimisation; correctness must be enforced at the system of record.**
**Proper design**:
- Make the **database (MongoDB here, or Postgres) the source of truth for claims**: claim with an atomic conditional update: `findOneAndUpdate({_id: task, $or: [{status: "open"}, {lease_expires_at: {$lt: now}}]}, {$set: {status: "claimed", claimed_by: user, lease_expires_at: now + 30m}, $inc: {claim_version: 1}})`. In Postgres: `UPDATE ... WHERE id = $1 AND (status = 'open' OR lease_expires_at < now()) RETURNING claim_version` (or `SKIP LOCKED` for "give me the next task", Q40). Only one wins, atomically, durably.
- The returned **`claim_version` is a fencing token**. On submit: `UPDATE task SET status='done', result=... WHERE id=$1 AND claimed_by=$user AND claim_version=$token`. If the lease expired and someone else re-claimed it (version incremented), the stale submit is rejected (the UI says "this task was reassigned") instead of overwriting.
- **Heartbeats** from the UI extend the lease while the annotator is active.
- **Redis stays as a cache**: fast "available tasks" lists, counters/stats, presence. If Redis loses data, you rebuild it from the DB; nothing incorrect happens, it's just briefly slower/less accurate.
**What you give up**: some **latency/throughput** (a DB write per claim instead of a Redis op: fine at annotator scale, hundreds of claims per minute, not millions); occasional **wasted work** (an annotator whose lease expired loses their in-progress work, mitigated with heartbeats and autosave of drafts); and **stats in Redis may be briefly inaccurate** after a failure (eventually reconciled from the DB).
**Your story:** be upfront that the Turing version used Redis locks (per your resume), what TTL you used and what happened on expiry, and present this as "how I'd harden it".

---

## H. TESTING & QUALITY

### 71. What is your actual testing pyramid for a FastAPI service? What percentage is unit?
Rough shape: **~60–70% unit, ~20–30% integration, ~5–10% end-to-end/contract/smoke.**
- **Unit** (fast, no I/O): domain logic, pricing/validation rules, pure functions, Pydantic models and validators, utility code. Run in milliseconds, thousands of them, on every save.
- **Integration**: API endpoints via `httpx.AsyncClient` / `TestClient` against a **real Postgres (testcontainers)** and real Redis, with external HTTP services stubbed (`respx`), so you test routing, dependencies, serialization, SQL, transactions and migrations together. For a CRUD-heavy FastAPI service this layer gives the most confidence per test, and it's fine for it to be bigger than the textbook pyramid says (the "testing trophy" view).
- **E2E / smoke**: a few critical user journeys against a deployed environment after each deploy. **Contract tests** for APIs other teams consume (Q76).
- Plus static checks (ruff, mypy) and migration tests (upgrade/downgrade on a real DB).
The percentage matters less than the rule: **every test should fail for exactly one reason and run fast enough that people run them.**

### 72. How do you test code that talks to Postgres - mocks, testcontainers, or a shared test DB? Defend your choice.
**Testcontainers (a real Postgres in Docker), same major version as production.** Defence:
- **Mocks** of the DB/session test that you called the ORM the way you *think* is right, not that the SQL actually works. They miss SQL errors, constraint violations, transaction behaviour, `ON CONFLICT`, JSONB operators, locking (`SKIP LOCKED`), migrations. SQLite as a substitute also lies (different types, no JSONB/arrays, different locking).
- **Shared test DB**: tests interfere with each other (flaky, order-dependent), parallel CI runs collide, the schema drifts from migrations, and someone always leaves junk data in it.
- **Testcontainers**: real behaviour, isolated per test run, disposable, works in CI (Docker available) and locally. To keep it fast: start the container **once per test session**, run migrations once, then isolate each test with a **transaction that's rolled back** at the end (or `SAVEPOINT`s / truncate between tests); use `pytest-xdist` with one DB per worker.
Mocks still have a place: unit tests of domain logic shouldn't touch the DB at all. Inject a repository interface (Protocol) and use an in-memory fake there.

### 73. How do you test async code and code with timers/retries without sleeping?
- Async tests: `pytest-asyncio` (or `anyio`'s pytest plugin) with `async def test_...`.
- **Don't sleep in tests; control time.** Options: inject the clock and sleep function as dependencies (`retry(..., sleep=fake_sleep)`, `now=lambda: fixed_time`) so tests pass a fake that records calls and returns immediately; `freezegun` / **`time-machine`** to freeze/advance wall-clock time; for asyncio, patch `asyncio.sleep` with an `AsyncMock`, or use a fake/virtual-time event loop (e.g. `looptime` plugin for pytest makes `asyncio.sleep(60)` complete instantly while advancing loop time; Trio has `MockClock` natively).
- For retries: assert on the **sequence of delays requested** (e.g. `[0.5, 1, 2]` within jitter bounds) and the number of attempts, using a stub that fails N times then succeeds (`respx` for HTTP, `side_effect=[err, err, ok]`).
- For timeouts: make the awaited thing an `asyncio.Event` that never gets set and use a tiny timeout, or virtual time.
- For "eventually" conditions in integration tests, poll with a short timeout instead of a fixed `sleep(5)`.
Tenacity has `retry.wait`/`sleep` hooks that can be overridden for tests.

### 74. What is property-based testing (Hypothesis) and where would it have caught a bug for you? (Strong fit for the Excel transpiler.)
Instead of hand-written examples, you state a **property that must hold for all inputs**, and Hypothesis **generates hundreds of inputs** (including nasty edge cases: 0, negatives, NaN, huge numbers, empty strings, unicode), and when it finds a failure, it **shrinks** it to the minimal failing example.
```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False), st.integers(0, 6))
def test_xl_round_matches_reference(x, digits):
    assert xl_round(x, digits) == reference_excel_round(x, digits)
```
Typical properties: round-trip (`parse(serialize(x)) == x`), **equivalence with an oracle** (new implementation == old/reference implementation; generated rater == Excel/LibreOffice on random inputs), invariants (premium is never negative; result is monotonic in sum insured; sorting is idempotent), and "doesn't crash" (fuzzing an API endpoint with `schemathesis`, which generates requests from your OpenAPI schema).
Where it would have caught bugs for you: the transpiler's runtime functions are perfect targets: `ROUND` half-cases (`2.675`), negative `MOD`, date serial conversions around 1900-02-29, string/number coercion, approximate `VLOOKUP` at exact band boundaries. Random inputs find the boundary values humans forget. Also: parsers of extracted documents/emails, and pagination/cursor logic.
**Your story:** if you haven't used Hypothesis, say so and name where you'd apply it first (Cellular runtime functions).

### 75. How do you test a Celery task end to end?
Layers:
1. **Unit-test the logic, not Celery**: keep the task body thin and call a plain function (`def process_resume(resume_id)`) that you test directly. Most bugs live there.
2. **Task in isolation**: call `task.apply(args=...)` (runs synchronously in-process, returns an EagerResult) or `task.run(...)`. Or `CELERY_TASK_ALWAYS_EAGER=True` in tests. Note eager mode skips serialization, routing and the broker, so it can hide bugs (e.g. non-JSON-serializable arguments, task not registered).
3. **Real end to end**: `celery.contrib.testing` has a `celery_worker` pytest fixture that starts an **in-process worker thread** against a real broker (Redis/RabbitMQ via testcontainers) and a real result backend. Then: trigger via the API (or `task.delay()`), wait on `result.get(timeout=10)` or poll the DB for the expected side effect, assert. This catches serialization, routing/queue names, retries, ack behaviour.
4. Test **retry and failure paths**: force the dependency to fail (mock/stub), assert `task.retry` behaviour and that it ends up in the failure state / DLQ after max retries; test **idempotency** by running the same task twice and asserting a single effect (Celery delivers at-least-once, especially with `acks_late`).
5. For chains/chords/canvas: test the workflow with the real worker fixture, since eager mode doesn't faithfully emulate chords.

### 76. Contract testing between services - have you done it? What problem does it solve that integration tests don't?
Contract testing checks that a **consumer's expectations** of a provider's API (requests it sends, fields it reads, status codes it handles) match what the **provider actually returns**, **without** deploying both services together.
Consumer-driven (Pact): the consumer's tests run against a Pact mock and record a **contract** ("when I GET /quotes/123 I expect 200 with `premium` as a number"), published to a Pact Broker; the provider's CI **verifies** every consumer's contract against the real provider code. Each side is tested independently, quickly, in its own pipeline. `can-i-deploy` checks whether a version is compatible with what's deployed in production.
What it solves that integration tests don't: integration/E2E tests need **all services deployed together** in a shared environment, which is slow, flaky, expensive, and with N services there are too many version combinations to test. Contract tests catch the most common cross-service break (provider renames/removes a field or changes a type that some consumer depends on) **at the provider's PR**, before deploy, and tell the provider exactly *which* consumer would break. Lighter alternatives: OpenAPI schema as the contract with breaking-change detection in CI (`oasdiff`), schema registries for Kafka events (Avro/Protobuf compatibility rules).
**Your story:** most likely you haven't run Pact. Say what you did instead (shared Pydantic schemas package, OpenAPI checks, manual coordination) and what broke because of it.

### 77. How do you write a test that reproduces a race condition deterministically?
Races are timing-dependent, so you **remove the timing randomness** by controlling the interleaving:
- **Inject synchronisation points (hooks)**: make the code under test call a hook between "check" and "act" (or patch a function that runs between them). In the test, the hook makes worker A **pause on an `Event`/`Barrier`** until worker B has completed its check. Now both have read the stale state, guaranteed, every run. Then release A and assert that the invariant holds (only one claim succeeded / the counter is correct).
```python
# two coroutines both pass the "is it free?" check before either writes
barrier = asyncio.Barrier(2)
async def slow_check(*a, **kw):
    r = await real_check(*a, **kw)
    await barrier.wait()             # force both to get here before either acts
    return r
with patch("app.claims.is_free", slow_check):
    results = await asyncio.gather(claim(task, "u1"), claim(task, "u2"), return_exceptions=True)
assert sum(r is True for r in results) == 1
```
- For DB races, use **two real connections/transactions** in the test and interleave statements manually: tx1 reads, tx2 reads, tx2 writes and commits, tx1 writes → assert the conflict is detected (optimistic locking) or tx1 blocked (row lock).
- Stress tests (run 1000 concurrent attempts) are useful to *find* races, but they're probabilistic, so don't rely on them as regression tests.
- Tools for model-level checking exist (e.g. TLA+ for designs, `loom` in Rust), but the hook/barrier technique is the practical answer in Python.

### 78. What does "good coverage" mean to you, and where is coverage a misleading metric?
Good coverage means **the important behaviours and failure modes are tested**: business rules, edge cases, error paths, concurrency/idempotency, and every bug that reached production has a regression test. Line coverage is a useful **signal for finding untested code**, not a goal. A sensible bar: high coverage (85%+, with **branch** coverage) on core domain logic, lower is fine on glue code; and coverage should not drop on new PRs (diff coverage).
Misleading because:
- Coverage says a line **ran**, not that its result was **checked**. A test with no meaningful assertions still gives 100%. (**Mutation testing**, e.g. `mutmut`, measures whether tests actually catch changes in the code.)
- Line coverage misses branches/conditions (`if a and b`) and combinations of inputs; 100% line coverage on a pricing function says nothing about boundary values.
- It ignores what isn't in the code: missing validation, missing error handling, integration behaviour (SQL correctness when the DB is mocked), concurrency.
- Targets get gamed (tests written to hit lines rather than verify behaviour), and they push effort toward trivial code (getters, config) instead of risky code.

---

## I. CODE & DESIGN JUDGEMENT

### 79. Show me how you'd structure a FastAPI codebase for a 12-person team. Where do domain logic, IO, and framework code live? What is your dependency direction?
**Structure by feature/domain module (vertical slices), with layers inside each**, not one giant `routers/ models/ services/` split across the whole app (that forces every change to touch 5 folders and creates merge conflicts across a 12-person team).
```
app/
  main.py                # create_app(), lifespan, middleware, router registration
  core/                  # config (pydantic-settings), logging, security, db engine/session, errors
  quotes/
    api.py               # FastAPI router: HTTP only (parse, auth, call service, map errors -> HTTP)
    schemas.py           # Pydantic request/response models (API contract)
    service.py           # use cases / orchestration (business workflow, transactions)
    domain.py            # pure domain logic & entities: no FastAPI, no SQLAlchemy, no I/O
    repository.py        # DB access (SQLAlchemy), returns domain objects
    models.py            # ORM models
    clients.py           # adapters for external services (rater API, blob, LLM)
  policies/ ...
  documents/ ...
tests/ (mirrors app/)  ·  migrations/ (alembic)
```
**Dependency direction: inward, toward the domain.** `api → service → domain`; `service → repository/clients` through **interfaces** (Protocols) defined on the domain/service side. Domain depends on nothing (no FastAPI, no ORM, no HTTP), so it's trivially unit-testable and survives framework changes. Framework code (FastAPI, SQLAlchemy, Azure SDKs) is at the edges. Modules talk to each other through their **service** layer (a public interface), never by reaching into another module's tables/repository. This is clean / hexagonal architecture, applied pragmatically.
Team-level guard rails: enforce the import rules with `import-linter`; ownership per module (CODEOWNERS); one shared `core`, kept small.

### 80. When do you introduce a repository/service layer, and when is it ceremony?
**Ceremony** when: the app is mostly CRUD with little business logic, the service just passes through to the repository, which just passes through to the ORM (three files to add one field), small team, short-lived service. SQLAlchemy's Session already *is* a repository/unit-of-work; wrapping it 1:1 adds nothing.
**Worth it** when:
- **Service layer**: real business workflows (quote → bind involves validation, rating, several entities, external calls, events). The logic needs one home that's reusable from the API, CLI, workers and tests, and that owns the transaction boundary.
- **Repository**: complex or reused queries you want named and tested once (`find_expiring_policies(tenant, window)`), you need to swap or fake storage (domain unit tests with an in-memory repo), multiple data sources behind one interface (Postgres + Cosmos + cache), or enforcing cross-cutting rules like tenant filtering in one place.
Pragmatic rule: start with route → service (functions) → ORM directly; **extract a repository when the same query shows up in two places or tests start needing a DB just to test logic.** Introduce layers when the pain appears, not prophylactically.

### 81. What's your rule for when a module becomes a separate service? What's the cost of getting it wrong in each direction?
Default: **modular monolith** first. Split a module into a service when there's a concrete forcing reason, such as:
- **Different scaling or resource profile** (PDF rendering, OCR, ML inference: CPU/GPU/memory heavy, spiky; shouldn't share pods with the API).
- **Different deployment cadence / ownership**: a separate team owns it and is blocked by the shared release train.
- **Fault isolation**: a crash/leak/heavy load in it must not take down the core.
- **Different security/compliance boundary** (PII/payment processing, tenant data residency).
- **Different tech** genuinely needed (e.g. a Go/Rust component, or a vendor runtime).
And only when the **boundary is stable** and the interface is narrow (few calls, mostly async). If two modules share a DB table or need a transaction across them, they're not ready to be split.
Cost of getting it wrong:
- **Split too early**: a distributed monolith: network calls instead of function calls (latency, partial failures, retries), distributed transactions/sagas for things that used to be one DB transaction, data duplicated and consistency issues, harder local dev/debugging/tracing, versioned APIs, N pipelines, more infra cost, and if the boundary was wrong, moving logic across services is very expensive.
- **Split too late**: a monolith where teams step on each other, deploys are slow and risky, one hot component forces scaling everything, a memory leak in one feature kills all of them; and extracting later is painful because the boundaries have eroded (shared tables, tangled imports).
Too early is usually the more expensive mistake; a well-modularised monolith (Q79) keeps "split later" cheap.

### 82. Review this mentally: a function with 6 boolean parameters and 200 lines. Walk me through your refactor, step by step, safely, with no test coverage.
1. **Pin down current behaviour before changing anything: characterisation tests.** Find the real call sites (which flag combinations are actually used: often only 4–5 of the 64 possible). Write tests that call the function with those combinations and representative inputs and **assert whatever it currently returns** (golden master / snapshot tests), including side effects (mock the I/O and record calls). The point is "unchanged", not "correct". If production logs or recorded traffic exist, replay them as test data.
2. **Make the call sites readable without changing behaviour**: make the booleans keyword-only (`def f(data, *, send_email=False, ...)`), update callers to use keywords. Pure safety win.
3. **Small, mechanical refactors with IDE support**, running the tests after each: extract method for each coherent block (validation, calculation, persistence, notification); rename variables; replace nested ifs with guard clauses. Commit after each step.
4. **Attack the flags**: booleans usually mean the function is doing several jobs. Options:
   - Flags that pick **different behaviours** → split into separate functions per real use case (`create_quote`, `requote`, `create_quote_for_import`) that share the extracted helpers.
   - Flags that toggle **optional steps** (send_email, audit) → move those steps out to the caller, or pass a small options object (dataclass) / strategy.
   - Mutually exclusive flags → an `Enum` (`mode=Mode.DRAFT`).
5. **Migrate callers one at a time** to the new functions; keep the old function as a thin wrapper delegating to the new ones until no callers remain, then delete it. Each step is a separate small PR that's easy to review and to revert.
6. Throughout: no behaviour changes mixed with refactoring (if you find a bug, write it down, fix it in a separate PR); deploy in small increments; watch metrics/errors after each.

### 83. Dependency injection in Python - `Depends`, containers, or plain constructor passing? What do you prefer at scale?
- **FastAPI `Depends`**: great for **request-scoped things at the HTTP boundary**: DB session, current user, tenant, settings, pagination params. Supports `yield` cleanup and test overrides (`app.dependency_overrides`). Downside: it only works inside FastAPI's request handling, so if your services depend on `Depends`, they can't be reused from Celery workers, CLIs or scripts.
- **DI containers** (`dependency-injector`, `lagom`, `punq`): central wiring, scopes, auto-resolution. Useful in very large apps with many implementations to swap; but they add magic and indirection, and stack traces get harder to read. Python's dynamic nature makes them less necessary than in Java/.NET.
- **Plain constructor injection**: services receive their dependencies as constructor/function arguments (`QuoteService(repo, rater_client, clock)`), typed as Protocols. Explicit, framework-free, trivially testable (pass fakes).
**Preference at scale**: **plain constructor injection for the service/domain layer, wired in one composition root, with `Depends` only at the edge** to build the request-scoped objects and hand them to services. A worker or CLI has its own small composition root that builds the same services. A container only if the wiring itself becomes a real burden, which is rare in Python.

### 84. How do you handle configuration across 5 environments? What never goes in code?
- **12-factor style**: the same build artifact (container image) is promoted through all environments; only **configuration differs**, injected via **environment variables** (plus mounted files for big configs).
- In the app: one typed settings class (**`pydantic-settings`**) that reads env vars, validates types at startup and **fails fast** on missing/invalid config. Sensible defaults only for non-sensitive, dev-friendly values.
- Per-environment values live in infra/deploy config: Helm values per env / Kustomize overlays / Terraform variables / ADO pipeline variable groups / Azure App Configuration (also handles feature flags and dynamic refresh). Config is version-controlled and reviewed like code.
- **Secrets**: in **Azure Key Vault / AWS Secrets Manager / GCP Secret Manager**, delivered via Key Vault references, the CSI secrets driver, or External Secrets Operator into K8s. Better still, **managed identity / workload identity** so many secrets (DB passwords, storage keys) don't exist at all. Rotate regularly.
**Never in code (or in the repo)**: secrets, passwords, API keys, connection strings with credentials, private keys/certs, tokens; environment-specific hostnames/URLs; customer data. Also not in Docker images and not in logs. Add secret scanning (gitleaks, GitHub/ADO secret scanning) in CI and pre-commit, since one leaked key in git history means rotating it, not just deleting the commit.

### 85. What is your stance on ORMs? SQLAlchemy 2.0 vs raw SQL vs query builder - and where do you draw the line?
**SQLAlchemy 2.0 by default**, used with eyes open:
- **ORM** for normal transactional work: CRUD on entities, relationships, unit of work, identity map, migrations via Alembic (autogenerate as a starting point), type-checked `Mapped[]` models. Productive and safe (parameterized queries, no injection).
- **SQLAlchemy Core (the query builder layer)** for dynamic queries built from filters (search endpoints with optional filters), bulk operations (`insert().values([...])`, `on_conflict_do_update`), and set-based updates. Composable and still database-agnostic-ish.
- **Raw SQL** (`text()` with bound parameters, or a `.sql` file) for queries where SQL is simply the best language: complex reporting, window functions, CTEs/recursive CTEs, Postgres-specific features (`SKIP LOCKED`, `LATERAL`, JSONB operators, `COPY`), and performance-critical queries you've hand-tuned with EXPLAIN.
**Where I draw the line**: the moment I'm fighting the ORM to produce a specific SQL query, or I can't predict what SQL it will run, I write the SQL. And regardless of layer: always check the generated SQL for hot paths (`echo=True` in dev, query logging), watch out for **N+1 queries** (use `selectinload`/`joinedload` deliberately; SQLAlchemy 2.0's `lazy="raise"` makes accidental lazy loads fail loudly), and keep lazy loading off in async code (it raises errors there anyway).
Against "ORMs are bad": the problems usually come from not understanding the SQL they generate, not from ORMs themselves.

---

## J. DEBUG SCENARIOS (pick at least one - highest signal in this file)

> Interviewers grade the **process** here: hypotheses in priority order, what data you'd look at to confirm/reject each, and mitigation before root cause. Talk in that order.

### 86. p99 latency on one endpoint jumped from 200ms to 9s. p50 is unchanged. CPU is flat. Walk me through your diagnosis. What are the top 5 hypotheses in priority order?
p50 unchanged + one endpoint + CPU flat → **most requests are fine; a subset is waiting on something**. It's waiting, not computing.
First steps: when did it start (correlate with deploys, config changes, traffic shifts, a dependency's incident)? Which requests are slow: pull **traces of the slow requests** (exemplars from the p99 bucket) and see which span takes the 9s. Check whether it's specific tenants/inputs/pods.
Top 5 hypotheses, in order:
1. **Data-dependent slow query**: specific tenants/inputs hit a bad plan or a huge result (a big tenant with a generic prepared-statement plan, a missing index on a new filter, a growing table crossing a plan-flip threshold, Q45). Check: slow query log / `pg_stat_statements`, the DB span duration in traces, which parameters the slow requests had.
2. **Pool exhaustion / queueing**: DB or HTTP client **connection pool** too small (or leaking connections), so some requests wait for a free connection. Very characteristic: 9s ≈ a pool timeout/wait. Check pool metrics (checked-out, waiters, wait time), `pg_stat_activity` (idle in transaction?), the gap in the trace *before* the DB span starts.
3. **Lock contention**: some requests wait for row/table locks (a hot row updated by many requests, a long transaction, a migration, `SELECT FOR UPDATE`). Check: `pg_locks`, `wait_event` in `pg_stat_activity`, lock-wait logging (`log_lock_waits`).
4. **A slow or flaky downstream dependency** called by this endpoint (external API, Azure service, LLM, auth/JWKS fetch) with slow tail or **timeouts + retries** (e.g. 3s timeout × 3 attempts = 9s!). Check: outbound HTTP spans, the dependency's status page, retry logs. That 9s being a suspiciously round multiple is a strong clue.
5. **Event loop blocking / resource contention on some pods**: a sync call or heavy CPU work in an async endpoint blocks other requests on the same worker intermittently (p50 is fine because most requests don't coincide with it), or one bad pod/node (noisy neighbour, CPU throttling from K8s limits: CPU is "flat" on average but throttled in bursts; check `container_cpu_cfs_throttled_seconds_total`), GC pauses, a cold cache for certain keys (cache stampede after an eviction).
Mitigate while investigating: set sane timeouts, roll back a correlated deploy, add the missing index, raise pool size if DB has headroom, rate-limit the heavy tenant.

### 87. A service works fine for 6 days then falls over every 7th day at 3am. Where do you look?
Two families: **something periodic happens at that time**, or **something accumulates and hits a limit after ~6 days**.
**Scheduled things at ~3am weekly**:
- Batch/cron jobs: weekly reports, backups, `VACUUM FULL`/reindex, data exports, cache warm-ups, log rotation, a big ETL/backfill hogging the DB or the network.
- Cloud/infra maintenance windows: managed DB (RDS/Azure SQL/Postgres Flexible Server) maintenance/failover, node OS patching / AKS node image auto-upgrade, certificate or secret rotation (a credential rotated weekly but the app caches the old one → auth fails until restart), DNS changes.
- Third-party maintenance windows of a dependency.
- Timezone/DST edges, if it's not literally every week.
**Accumulation (time-to-exhaustion ≈ 6–7 days)**:
- **Memory leak** reaching the container limit → OOMKill (Q10). Check memory graphs: linear climb?
- **Resource leaks**: file descriptors, DB connections, threads, temp files/disk filling up (logs written to local disk, `/tmp` filling), inode exhaustion.
- **Counters/caches/queues** growing unbounded; a token/session that expires after 7 days and isn't refreshed (e.g. a refresh token or a Graph subscription that expires); a token bucket or ID counter overflow.
Where to look: plot memory, FDs, connections, disk and queue sizes over **two full weekly cycles** and see what climbs; check the cron/K8s CronJob schedules, cloud maintenance settings and activity logs for that window; read the logs from 2:30–3:30am of the last failures; check whether the 7-day period resets on **deploys/restarts** (if it's "7 days after a restart", it's accumulation; if it's "every Sunday 3am" regardless of restarts, it's scheduled).

### 88. Requests intermittently hang for exactly 60 seconds then succeed. What's your first guess?
"Exactly 60s" means a **timeout default** is being hit, followed by a retry that succeeds. First guesses:
- **A stale/dead pooled TCP connection**: a load balancer, NAT gateway or firewall (Azure LB / NAT idle timeout ~4 min, AWS NLB 350s, etc.) silently dropped an idle connection in the pool; the client sends on it, gets no response, waits for a 60s read timeout, then reconnects and succeeds. Fix: TCP keepalives, `pool_pre_ping` / `pool_recycle` (SQLAlchemy), client-side idle timeout shorter than the infra's idle timeout.
- **DNS**: a resolver timing out (e.g. one of the nameservers unreachable, IPv6 AAAA lookups timing out, the classic conntrack race in Kubernetes with UDP DNS: usually 5s multiples though) before falling back.
- **A proxy/gateway default timeout of 60s**: Nginx `proxy_read_timeout` defaults to 60s, as do many LB idle timeouts; the upstream is slow/stuck for some requests, the proxy times out at 60s, and the client retries.
- A lock wait timeout or a pool checkout timeout configured to 60s.
Diagnose: find which hop the 60s lives in from traces (where does the gap sit?), grep configs for `60`, check whether it happens after idle periods (stale connections) or under load.

### 89. Your Celery queue depth is growing but worker CPU is 20%. What's happening?
Workers aren't CPU-bound, so they're **busy waiting** or **not actually pulling work**. Likely causes:
- **Tasks are I/O-bound and concurrency is too low**: each worker process (prefork) is blocked on a slow DB/HTTP call/LLM API; with concurrency = number of CPU cores, almost all time is waiting. Fix: raise concurrency, or use the gevent/eventlet pool / threads for I/O-heavy tasks, separate queues for slow tasks.
- **A slow or saturated downstream**: the DB/API the tasks call got slower (or is rate-limiting with 429s and tasks retry/sleep), so throughput per worker dropped. Check task duration metrics and the dependency.
- **Prefetching** issues: with default prefetch multiplier, a worker reserves many messages, and if one long task blocks the process, the prefetched short tasks sit idle on that worker. Fix: `worker_prefetch_multiplier=1` + `acks_late=True` for long tasks.
- **Workers stuck/hung**: deadlocks, a task with no timeout waiting forever on a socket. Check `celery inspect active` (what's running and for how long), set `soft_time_limit`/`time_limit`, `py-spy dump` a worker.
- **Workers not consuming the right queue** / routing misconfiguration: tasks routed to a queue no worker listens to (after a deploy renamed a queue or task); or some workers died/disconnected (check `celery inspect ping`, worker count, broker connections).
- **Retry storms / ETA tasks**: lots of tasks scheduled with `countdown` sitting in workers' memory; or tasks failing and re-queueing themselves, inflating the queue.
- **Broker issues**: Redis memory full / evictions, RabbitMQ flow control.
Look at: active vs reserved tasks per worker, task runtime histogram, task failure/retry rate, worker count over time, the dependency latency.

### 90. After a deploy, error rate is fine but a downstream partner says they're getting duplicate webhooks. How do you confirm and fix?
**Confirm**: get the partner's examples (event IDs, timestamps, payload). Search our webhook delivery logs/table by event ID: is it the **same event ID delivered twice** (a retry/duplicate send), or **two different event IDs for the same underlying change** (we generated the event twice)? Check the timing: within seconds (concurrent senders) or minutes apart (retries)? Correlate with the deploy time.
**Likely causes after a deploy**:
- **More replicas/instances now run the sender**: e.g. a scheduler/poller (APScheduler, a cron loop, an outbox relay) that was previously running in one process is now running in every pod/worker, so each one picks up and sends the same events. Very common.
- **The outbox relay / job claim lost its locking** (no `SKIP LOCKED` / lock in the new code), so two relays send the same rows.
- **Retry logic changed**: e.g. the timeout became shorter than the partner's response time, so we treat slow-but-successful deliveries as failures and resend; or we now retry on 2xx-but-unexpected-body.
- Duplicate event **emission**: a code path now publishes the event twice (e.g. both in a service and in a model hook), or a consumer now processes messages at-least-once without dedupe (`acks_late` with redeliveries during the rolling deploy itself).
**Fix**: immediate mitigation: roll back, or scale the sender to one/disable the duplicate scheduler. Real fix: single active sender via claim-based delivery (DB row claim with `SKIP LOCKED` or a leader lease), a **unique event ID per event** included in the payload/headers (e.g. `webhook-id`) and stable across retries, delivery state stored per (event, endpoint) so you never resend a delivered event, timeouts aligned with the partner. And tell partners **webhooks are at-least-once and they must dedupe on the event ID**: duplicates will always be possible (that's the industry norm, e.g. Stripe, and the Standard Webhooks spec). Add a test/alert for duplicate deliveries per event ID.

### 91. Pods are being OOMKilled but your app's own memory profiler says usage is flat. Explain how both can be true.
The kernel's cgroup counts the **container's total memory**, but a Python profiler (tracemalloc etc.) only counts **Python object allocations**. The gap:
- **Native memory**: C extensions (numpy, pandas, PIL, lxml, pydantic-core, ML libs, DB drivers) allocate outside Python's allocator, invisible to tracemalloc.
- **Allocator fragmentation / memory not returned to the OS**: Python frees objects but glibc malloc keeps the pages (fragmented arenas), so RSS stays high or grows while "live Python memory" is flat. Multiple threads → many malloc arenas. Fix: `MALLOC_ARENA_MAX=2`, jemalloc.
- **Other processes in the container**: gunicorn/uvicorn **multiple workers** (the profiler measured one worker; there are 8), subprocesses (LibreOffice/Chromium for PDF rendering, OCR), a sidecar sharing the limit if configured per-pod. Forked workers gradually un-share copy-on-write pages, so total RSS grows.
- **Page cache / tmpfs counted against the cgroup**: files written to an `emptyDir` with `medium: Memory` or `/dev/shm` count as memory; heavy file I/O inflates page cache (usually reclaimable, but dirty pages and tmpfs aren't).
- **The limit itself**: the container limit is just too low for peak (a spike between profiler samples: one huge request loading a 500MB file), or memory **request ≪ limit** and the node is under pressure (node-level eviction rather than container OOMKill, which is a different message).
Diagnose: compare container metrics (`container_memory_working_set_bytes`, RSS vs cache) to the profiler; `kubectl describe pod` (OOMKilled vs Evicted); check per-process RSS inside the container; memray (tracks native allocations too).

### 92. Postgres connections are exhausted. Everything you can do in the next 10 minutes, and everything you do in the next 10 days.
**Next 10 minutes (stop the bleeding)**:
- Look at `pg_stat_activity`: who holds the connections (group by `application_name`, `usename`, `client_addr`, `state`). Look for many **`idle in transaction`** (leaked sessions/transactions), long-running queries, and a single service/pod/job hogging connections.
- **Kill the offenders**: `pg_terminate_backend(pid)` for idle-in-transaction connections and runaway queries (carefully; not replication/admin ones). Set `idle_in_transaction_session_timeout` (e.g. 60s) and `statement_timeout` for the app role if not set.
- Stop the source: pause/scale down the batch job or the service that's hogging connections; roll back the deploy if it correlates; temporarily reduce replicas of non-critical consumers.
- If an autoscaler just scaled pods from 10 to 40 (each with a pool of 20 → 800 connections), cap the replicas.
- Superuser reserved connections (`superuser_reserved_connections`) let you get in as admin to do this.
**Next 10 days (fix it properly)**:
- **Connection pooler: PgBouncer** in transaction-pooling mode (or the managed pooler on Azure Flexible Server / RDS Proxy), so thousands of app connections map to a few dozen real Postgres connections. Mind transaction-mode caveats (session-level features like prepared statements / advisory locks / `SET` need care).
- **Connection budget**: compute `pods × workers × pool_size + overflow` for every service and make sure it's < `max_connections` with headroom for admins, migrations and replicas; cap HPA max replicas accordingly. Separate pools/roles per service with `CONNECTION LIMIT` per role so one service can't starve the others.
- **Fix leaks in the code**: sessions not closed, transactions held open across external HTTP calls (Q25), background tasks using sessions; add pool metrics (checked-out, overflow, wait time) and alerts at 70–80% of `max_connections`.
- Timeouts everywhere: `statement_timeout`, `idle_in_transaction_session_timeout`, pool checkout timeout, `pool_pre_ping`.
- Move read-heavy traffic to replicas; batch jobs to their own role with limits. Consider whether `max_connections` should be raised (only with enough RAM; it's not the real fix).
- A postmortem, with the timeline and the guard rails added.

### 93. A single tenant's traffic is degrading everyone else. Design the fix.
"Noisy neighbour". Fix at every layer, from quick to structural:
1. **Visibility first**: per-tenant metrics (requests, latency, errors, DB time, queue depth, LLM tokens), so you can see who is causing it and prove it.
2. **Per-tenant rate limits and quotas** at the gateway and in-app (token bucket per tenant, Q26), tiered by plan; return 429 with `Retry-After`. Short-term: throttle that tenant specifically.
3. **Fair scheduling of background work**: instead of one FIFO queue (where one tenant's 100k jobs block everyone), use per-tenant queues with round-robin/weighted fair consumption, or cap concurrent jobs per tenant (a per-tenant semaphore in Redis), or partition by tenant with weights. Service Bus sessions / Kafka partitioning by tenant help.
4. **Concurrency isolation (bulkheads)**: separate worker pools / connection pools per tenant tier (big tenants get their own pool), so their saturation doesn't exhaust shared resources. Per-tenant DB statement timeouts / role connection limits.
5. **Data-layer fixes**: the tenant's queries are slow because of their data volume → tenant-aware indexes, partitioning by tenant, and plans that work for large tenants (Q45 parameter sniffing).
6. **Physical isolation for the largest tenants**: dedicated deployment / dedicated DB or shard ("silo" model, Q32, Q46), with cost passed on in pricing.
7. **Load shedding by priority** when overall capacity is exhausted: degrade the over-quota tenant first.
Also talk to the tenant: often it's an integration bug on their side (retry loop, polling every 100ms) that a conversation fixes faster than code.

### 94. Data corruption found in production, source unknown, 3 days old. What is your order of operations? (Watch for: stop the bleeding, preserve evidence, comms, then fix.)
1. **Declare an incident** and assign roles (incident commander, comms, investigators). Corruption is a severity-1-type event, especially with insurance/financial data.
2. **Stop the bleeding**: prevent more corruption. If the source is unknown, narrow it fast: which tables/fields/tenants are affected and since when → correlate with deploys, migrations, jobs, config changes 3 days ago. Then roll back the suspect deploy, pause the suspect jobs/consumers/integrations, or put affected features in read-only mode. Stopping writes to the affected data beats a perfect diagnosis.
3. **Preserve evidence**: **before** fixing anything, take a snapshot/backup of the current state, export the affected rows, keep logs (extend retention so they don't roll off!), preserve Kafka offsets/queues, audit tables, and the deployed versions. Don't "fix" rows by hand in a way that destroys the trail.
4. **Communicate**: inform stakeholders and leadership early with what you know and don't know; affected customers/tenants per the contract; in a regulated domain (insurance, GDPR), legal/compliance must assess whether it's a reportable incident with deadlines (GDPR: 72h for personal-data breaches). Regular status updates.
5. **Assess the blast radius**: exactly which records, which fields, which tenants, and what downstream consumers already used the bad data (documents issued, invoices, partner integrations, reports, emails sent). Those need their own remediation.
6. **Find the root cause** using the evidence: audit trails, history tables, CDC/WAL, logs with request IDs, code diffs.
7. **Repair**: options: restore from PITR into a **separate** instance and compare/copy back the correct values; replay from raw inputs (Q34); or a scripted correction. Dry-run on a copy, verify with business owners, apply in a transaction with a record of every change, keep the corrupted values in a backup table.
8. **Verify** with reconciliation checks, then **re-enable** paused functionality.
9. **Blameless postmortem** and prevention: data validation/constraints that would have caught it, monitoring/alerts on data anomalies (detection took 3 days: why?), better audit/replay capability, tests.

---

## K. ENGINEERING PRACTICE / MODERN EXPECTATIONS

> Mostly opinion and experience questions. The answers below are a frame to hang your own experience on, not lines to recite.

### 95. What does your dev loop look like in 2026? Are you using AI coding agents, and what do you refuse to let them do?
Frame: yes, AI agents (Claude Code, Copilot, Cursor) are part of the daily loop, and the senior skill is **directing and verifying** them, not typing.
Typical loop: write/clarify the task (often a short design note or a failing test first) → let the agent explore the codebase, draft code and tests → **review the diff like a junior's PR** → run tests, type checks and linters locally (fast feedback: pre-commit, pytest-watch) → small PRs → CI → deploy behind a flag with observability.
Where agents shine: boilerplate, tests (especially characterisation tests), refactors across many files, reading unfamiliar code, migrations, scripts, first drafts of docs, debugging assistance with logs/stack traces.
What I refuse to let them do (or never without review): **push to main / deploy to production**, run destructive commands against real environments (dropping data, `terraform apply` on prod, force pushes), touch **secrets/credentials** or paste customer data/PII into prompts, make **security-sensitive changes** (auth, crypto, permission checks) without line-by-line human review, add dependencies without vetting (supply-chain risk / hallucinated package names), and **merge code I don't understand**: "the AI wrote it" is never an excuse in an incident review. Also: they're not allowed to make tests pass by weakening the tests.
**Your story:** mention concrete use (e.g. you built an MCP for Pulse and an agent at Espire, so you know both sides).

### 96. How do you review a 2,000-line PR from a junior?
First, the meta point: a 2,000-line PR is itself the problem, and part of the review is teaching them to slice work. But it exists, so:
1. **Talk before reading**: a 15-minute walkthrough with the author: what problem, what approach, where the risky parts are. Saves hours and is less demoralising than 80 written comments.
2. **Top-down**: read the description, tests and public interfaces/schema changes first. Is the **approach** right? If the design is wrong, say so now and stop. Don't nitpick lines in code that will be rewritten.
3. **Ask to split** if possible (refactor/moves vs behaviour changes vs new feature; migration separate from code), and land it in parts behind a flag.
4. **Focus on what matters, in order**: correctness and edge cases, data/migrations (irreversible!), security (authz, injection, secrets), concurrency/idempotency, error handling, performance traps (N+1, unbounded queries), tests that actually assert behaviour, observability. **Let tools handle style** (ruff, formatters, mypy); don't spend human attention on formatting.
5. **Comments**: label severity (`blocking:` / `suggestion:` / `nit:` / `question:`), explain the *why* and link to docs, praise good parts genuinely. For repeated issues, comment once and say "same elsewhere".
6. **Follow-up**: pair on the hardest fix; afterwards, coach on smaller PRs / earlier design check-ins so it doesn't recur.

### 97. What's your approach to writing a design doc? What sections are non-negotiable?
Write one when the change is expensive to reverse, crosses teams/services, or has real alternatives worth debating. Keep it short (2–6 pages), write it **before** building, circulate early as a draft for feedback, and record the decision.
Non-negotiable sections:
1. **Context and problem**: why now, who's affected, with numbers.
2. **Goals and non-goals**: non-goals prevent scope creep and endless debates.
3. **Requirements/constraints**: functional + non-functional (scale, latency, availability, compliance/data residency, cost, deadline).
4. **Proposed design**: architecture diagram, data model, APIs/contracts, key flows, failure handling.
5. **Alternatives considered** and why they were rejected: the most valuable section for reviewers and for future readers.
6. **Risks, trade-offs and open questions**.
7. **Rollout and rollback plan**: migration, feature flags, backfill, how to undo.
8. **Observability and operations**: metrics, alerts, SLOs, runbook impact.
9. **Security/privacy** considerations (in insurance: always).
Plus cost estimate and milestones when relevant. Afterwards, keep a short ADR (architecture decision record) in the repo that links to it.

### 98. How do you decide between building and buying? Give a real example where you chose to buy.
Criteria:
- **Is it core/differentiating?** Build what makes the business unique (e.g. the rating engine, domain workflows); buy commodity capabilities (auth/identity, payments, email delivery, observability, PDF rendering engines, OCR, feature flags, search infra).
- **Total cost of ownership**, not license price vs dev salary: building means owning maintenance, on-call, security patches, upgrades and scaling forever. Buying means license/usage costs that grow with scale, integration work, and vendor dependence.
- **Time to market**: how soon is it needed?
- **Fit and control**: does the product meet ~80% of needs without contortions? Compliance/data residency (can data leave our tenant?), SLAs, vendor viability, lock-in and exit cost (can we migrate off it?), extensibility (APIs, webhooks).
- **Team capability**: do we have the expertise to build *and* operate it well?
Example frames from your background (pick the true one): **buying** managed services instead of self-hosting (Azure Document Intelligence for extraction / OCR instead of training your own; Azure AI Search for the RAG index; managed Postgres instead of running it on VMs; Sentry/Grafana Cloud instead of self-hosted EFK; an identity provider (Auth0/Cognito/Entra) for SSO instead of hand-rolling OAuth). The reverse example also impresses: GeoStorm was about **moving away from ArcGIS** (a bought SaaS) to a built PostGIS backend, so you can explain when buying stopped making sense (cost, lock-in, needing control).
**Your story:** you need one real example with the actual reasoning and outcome.

### 99. What technical debt are you carrying at Espire right now, and what's your plan for it?
No universal answer; it's about your project. A strong answer has this shape:
- **Name 2–3 specific debts** and *why* they exist (deliberate trade-offs to hit a deadline vs accidental). Likely candidates for the Aventum/ATOMX work: missing or thin automated tests around Cellular-generated modules or the agent; manual steps in rater publication/deploy; inconsistent error handling or observability across Azure Functions; duplicated logic between Cellular and the agent replacement; config/secrets handling; lack of versioning/reproducibility guarantees.
- **Impact, quantified**: "every rater update needs ~2 hours of manual verification", "incidents take long to debug because there's no correlation ID across functions".
- **Plan**: prioritise by impact × cost of delay; pay it down incrementally inside feature work (boy-scout rule, ~15–20% capacity) rather than a big-bang rewrite; tie it to business outcomes so it gets prioritised; track it visibly (backlog with owners); prevent new debt (CI checks, templates).
- Show **judgement**: some debt is fine to keep (code that rarely changes and works).
**Your story:** this is entirely yours; prepare it concretely, as the interviewer will ask follow-ups.

### 100. If you joined us on Monday and were handed a 4-year-old Python monolith with no tests and 3 people who understand it, what do you do in weeks 1, 4 and 12?
**Week 1: learn and don't break anything.**
- Get it running locally and deploy something trivial through the pipeline (find out how deploys actually work).
- Sessions with each of the 3 experts: architecture walkthrough, the scary parts, the incident history, "what would you fix first". Record these and write them up: the biggest risk is **knowledge concentrated in 3 heads** (bus factor).
- Read the observability: dashboards, error tracker, logs, slow queries. If there isn't any, note that as priority #1.
- Map the system: modules, data stores, external integrations, cron jobs, hot paths (where change and bugs concentrate, from git history: churn × complexity).
- Ship one small, low-risk fix to learn the process. No refactors.
**Week 4: build safety nets.**
- **Observability baseline**: error tracking (Sentry), structured logs with request IDs, key metrics and alerts on critical flows.
- **Characterisation/smoke tests** for the most critical and most-changed paths (Q82), plus a CI pipeline that runs them, with lint/type check on changed files only.
- Make deploys safe: repeatable pipeline, staging environment, rollback procedure, maybe feature flags.
- Documentation: architecture overview, runbooks, onboarding guide (written while I'm still new and can see what's confusing). Spread knowledge: pair the 3 experts with others.
- Agree with the team on a short list of pain points to tackle, in order of business impact.
**Week 12: improve deliberately.**
- Test coverage on core business flows and a habit that every bug fix comes with a test.
- Start **incremental modularisation** (modular monolith, Q79, Q81) of the highest-churn area; **strangler fig** pattern for anything that truly needs replacing (new code beside the old, traffic moved gradually); no big-bang rewrite.
- Upgrade the runtime/dependencies if they're end-of-life (security).
- Measurable outcomes to show: deploy frequency up, change failure rate and MTTR down, onboarding time for a new engineer down, more than 3 people able to work on each area.
Main message to land: **understand before changing, add safety nets before refactoring, reduce risk and knowledge concentration first, then improve incrementally with measurable outcomes.**
