# W03: Async and Concurrency

**Dates:** Mon 2026-11-02 → Sun 2026-11-08 · **PREP_TODO:** Week 3 · **Knowledge map:** `async_concurrency` (developing → solid)

**Goal:** turn the R3 B gaps (Q16 and Q17 were `gap`, Q15 was `partial`) into confident answers. Most of the material already exists as runnable code in [scripts/async/](../scripts/async/). This week the voice agent *teaches the ideas*, and the scripts *prove* them.

| Day | Mode | Plan |
| --- | --- | --- |
| Mon | 🎓 Teach | Warm-up, then concepts 1–5 (model, loop, blocking, task APIs, structured concurrency). Then run scripts 01–02 |
| Tue | 🎓 Teach | Concepts 6–11 (cancellation, primitives, threads/processes, async CM/gen, contextvars, patterns). Then run scripts 03–08 |
| Wed | 🔧 Lab | Write the bounded fetcher **from memory**; modify the scripts with predictions |
| Thu | ✍️ Recall | Cheat sheet from memory |
| Fri | 🎤 Quiz | R3 B all + an async debug scenario + misses |
| Sat | 🤖 AI | A-03, async LLM pipeline (this week's ideas applied to LLM calls) |
| Sun | 📋 Review | Checklist; compare your infographic with [infographics/W03_async.svg](infographics/W03_async.svg) |

## Sources

```pack
answers/ROUND_2_fundamentals_breadth_answers.md: 11-13, 19
answers/ROUND_3_python_and_backend_advanced_answers.md: 14-23
```

Also add `scripts/async/README.md` to the NotebookLM notebook (its 60-second recap is good audio).

## Warm-up diagnostic (Mon, 5 min)

1. "Is asyncio parallel? Why or why not?"
2. "What happens if you call `requests.get()` inside an `async def` FastAPI endpoint?" (R2 Q12)
3. "What's the difference between a coroutine and a Task?"
4. "If one task in `asyncio.gather` fails, what happens to the others?"

---

## MONDAY

### 1. The mental model: concurrency without parallelism

**Teach.**
- asyncio is **one thread** running **cooperative multitasking**. Tasks voluntarily give up control at `await` points; the event loop then runs whichever task is ready.
- That makes it **concurrent** (many things in progress) but not **parallel** (only one thing executing at any instant).
- It wins for **I/O-bound** work with many waits (HTTP calls, DB queries, LLM calls), because waiting costs nothing. It gives nothing for CPU-bound work.

**The decision table (memorise it):**

| Workload | Tool | Why |
| --- | --- | --- |
| Many concurrent I/O waits, async libraries available | asyncio | Thousands of waits on one thread, cheap |
| I/O with only sync libraries | threads (`to_thread`) | The GIL is released during I/O |
| CPU-heavy Python | processes / a separate worker service | The GIL blocks threads from parallel CPU |
| CPU-heavy in C (NumPy etc.) | threads may be fine | The C code releases the GIL |

**Picture it.** One chef with many pots. While the water boils (I/O), they chop something else. But if they spend 10 minutes kneading dough (CPU) without looking up, every pot boils over.

**Your anchor.** The Jio recommender: async FastAPI handling ~33k peak RPS of I/O-bound calls (Redis, Postgres, other services), with CPU-heavy similarity moved out to separate services. That's the decision table in practice.

**Check.** "Give me one real workload each for asyncio, threads and processes from your own projects." (R2 Q13.)

### 2. The event loop, coroutines, Tasks and Futures

**Teach.**
- `async def f()` defines a **coroutine function**. Calling `f()` returns a **coroutine object** and runs **nothing** yet.
- `await coro` runs it *inline*, inside the current task.
- `asyncio.create_task(coro)` wraps it in a **Task**, which the loop schedules to run *concurrently*. This is how you actually get concurrency.
- A **Future** is a low-level placeholder for a result that isn't ready yet. A Task is a Future that drives a coroutine.
- The loop's job: keep a ready queue of callbacks; run each one until it hits an `await` on something not ready; register interest in that I/O (via `selectors`/epoll); when the OS says the socket is ready, resume the task.
- **Sequential trap:** `await a(); await b()` runs them *one after another*. For concurrency you need tasks, `gather` or a `TaskGroup`.

**Picture it.** A coroutine is a recipe card; a Task is a cook assigned to that card; the loop is the head chef calling out who's next.

**Check.** "Difference between `async def`, a coroutine, a Task and a Future?" (R2 Q11.) Then: "Why does `await fetch(a); await fetch(b)` take twice as long as you'd hope?"

**Script.** `python scripts/async/01_event_loop_and_coroutines.py`

### 3. Blocking the loop, and detecting it in prod ⚠️ open miss

**Teach.**
- Anything that runs a long time **without an `await`** freezes *every* request on that worker. Examples:
  - `requests.get`, `time.sleep`
  - a sync DB driver
  - `json.loads` on a 50 MB payload
  - a CPU loop, or a big Pydantic validation
- **Symptoms:**
  - p99 latency spikes across *unrelated* endpoints
  - health checks time out, so K8s restarts the pod
  - CPU isn't necessarily high
- **Detection, the answer you were missing:**
  1. **asyncio debug mode** (`PYTHONASYNCIODEBUG=1` or `loop.set_debug(True)`): logs any callback that runs longer than `loop.slow_callback_duration` (100 ms by default), with the location.
  2. **A loop-lag metric:** a background task does `await asyncio.sleep(0.5)` and measures how late it wakes up. Export that as a Prometheus gauge and alert on it. Script 01 implements this.
  3. **`py-spy dump --pid`** (or `py-spy top`) on the live process shows the exact stack that's hogging the thread.
  4. Tracing: spans with a large self-time and no child I/O.
- **Fixes:** use async libraries (`httpx`, `asyncpg`), `await asyncio.to_thread(sync_fn)` for blocking I/O, a process pool or queue for CPU, and in FastAPI declare the endpoint with plain `def`, so it runs in the threadpool.

**Your anchor.** A Cellular rater calculation (CPU-heavy, sync) called from an `async def` endpoint would block all other quote requests. The fix is a process pool or a separate rating worker.

**Check.** "Your async service's p99 jumped from 200 ms to 3 s across all endpoints, but CPU is only at 40%. What do you suspect, and how do you prove it in production?" (R3 Q15; this is the exact miss.)

**Interview angle.** R3 Q15, R2 Q12.

### 4. gather vs TaskGroup vs as_completed vs wait ⚠️ open miss

**Teach.**

| API | Results | On the first error | Use when |
| --- | --- | --- | --- |
| `gather(*aws)` | A list, **in input order** | Raises the first exception to you, but **the other tasks keep running** (not cancelled!) unless you cancel them. With `return_exceptions=True`, errors come back as values in the list | Best-effort fan-out where you want every outcome |
| **`async with TaskGroup() as tg`** (3.11+) | Use `task.result()` after the block | **Cancels all sibling tasks**, waits for them, then raises an **`ExceptionGroup`** (handled with `except*`) | **The default**: all-or-nothing work with clean failure semantics |
| `as_completed(aws)` | An iterator, in **completion order** | Each await raises for its own task | Process results as they arrive (stream to the client, first-N-good) |
| `wait(aws, return_when=...)` | `(done, pending)` sets | You inspect them | Races: `FIRST_COMPLETED` (hedged requests), timeouts with manual handling |

**Picture it.**
- gather = sending five people on errands and waiting for the full report, even if one already called to say the car crashed.
- TaskGroup = a team on a rope: if one falls, everyone stops.
- as_completed = taking each person's report as they walk in.

**Your anchor.** Jio fan-out to multiple candidate sources for a recommendation:
- best effort (some sources can fail): `gather(return_exceptions=True)` plus a timeout
- an extraction step where all parts are required (Orbit: parse email + attachments + metadata): `TaskGroup`
- streaming LLM tool results to the UI: `as_completed`

**Check.** "If one task in `gather` raises, what happens to the others? And in a TaskGroup?" Then: "Which do you reach for now, and why?" (R3 Q16; this was a gap.)

**Traps.** Assuming `gather` cancels siblings on failure (it doesn't, by default). Forgetting that TaskGroup raises an `ExceptionGroup`, so a plain `except ValueError` won't match; use `except* ValueError`.

**Script.** `python scripts/async/02_gather_taskgroup_as_completed.py`

### 5. Structured concurrency and the fire-and-forget gotcha ⚠️ open miss

**Teach.**
- **Structured concurrency:** every task's lifetime is **bounded by a code block**. Tasks started inside an `async with TaskGroup()` can't outlive it. Errors propagate to the parent, and cancelling the parent cancels the children. Just like a function call: it can't "leak" past its return.
- **Unstructured:** a bare `asyncio.create_task(...)` can outlive its creator. Nobody awaits it, so exceptions vanish (at best you get "Task exception was never retrieved" in the logs), and shutdown doesn't know it exists.
- **The GC gotcha:** the event loop keeps only a **weak reference** to tasks. A task you don't store can be **garbage-collected mid-execution**. If you must fire and forget, keep a strong reference: a set of tasks plus a `task.add_done_callback(tasks.discard)`. Better, give it an owner (a TaskGroup at app scope, or a proper queue).
- TaskGroup came from the anyio/trio "nursery" idea.

**Picture it.** Structured concurrency is a parent holding their kids' hands at a crossing: nobody leaves until everyone's across. Fire-and-forget is letting a kid wander off, and the GC might literally lose them.

**Your anchor.** FastAPI `BackgroundTasks` vs `create_task` for "send a webhook after responding". BackgroundTasks has an owner (it runs after the response, inside the request lifecycle); a bare `create_task` doesn't. For anything that must survive a restart, use Celery or a queue (your R3 Q30 answer, which you got right).

**Check.** "What is structured concurrency, and why is TaskGroup safer than `create_task`?" (R3 Q17.) "What happens to a Task if nobody holds a reference to it?" (R3 Q18.)

---

## TUESDAY

### 6. Cancellation and timeouts

**Teach.**
- `task.cancel()` doesn't kill anything immediately. It **injects `CancelledError` at the task's next `await`**. The task can clean up in `finally` / `async with`, and then **must let the error propagate**.
- **Never swallow `CancelledError`.** If you catch it to clean up, re-raise it. Swallowing it breaks timeouts, TaskGroup and shutdown, and the caller thinks the work stopped when it didn't. It's a `BaseException` (since 3.8), so `except Exception` won't catch it by accident.
- **Timeouts:**
  - `async with asyncio.timeout(5):` (3.11+, the preferred way): cancels the inner block and raises `TimeoutError`
  - `asyncio.timeout_at(deadline)`: an absolute deadline, which is how you propagate a request's time budget downstream
  - `asyncio.wait_for(aw, 5)`: the older equivalent
- `asyncio.shield(aw)` protects the inner operation from *outer* cancellation (e.g. finish committing a payment record even if the client disconnects). Use it sparingly, because the shielded work keeps running unsupervised.
- Cleanup must itself be bounded: wrap cleanup awaits in a short timeout.

**Your anchor.** SSE streaming of model responses at Turing. When the annotator closes the tab, the server should cancel the upstream LLM call (stop paying for tokens). That's a `CancelledError` propagating from the disconnected stream. You'll build exactly this in A-04 next Saturday.

**Check.** "How do you cancel an in-flight async operation cleanly? Why should you never swallow `CancelledError`?" (R3 Q19.)

**Script.** `python scripts/async/03_cancellation_and_timeouts.py`

### 7. Synchronisation: Lock, Semaphore, Event, Queue

**Teach.**
- **Single-threaded doesn't mean race-free.** Any *check-then-act* that spans an `await` can interleave:

  ```python
  if key not in cache:              # task A checks...
      cache[key] = await fetch(key) # ...awaits; task B checks too -> double fetch
  ```

- `asyncio.Lock`: mutual exclusion across awaits. **Single-flight** is a lock (or a shared Future) per key, so only one fetch runs and the others await its result. This is the cache-stampede fix (W6).
- `asyncio.Semaphore(n)`: at most n inside at once. **This is how you bound concurrency** against an API rate limit or a DB pool.
- `asyncio.Event`: one-to-many signal (e.g. "shutting down", "config loaded").
- `asyncio.Queue(maxsize=n)`: producer/consumer. **A bounded queue is backpressure**: `put` awaits when it's full, so a fast producer slows to the consumers' pace instead of eating RAM.
- These are **per-process** only. Across pods you need Redis/DB locks (W6) or a real queue (W7).

**Picture it.** A Semaphore is a bouncer with a clicker; a bounded Queue is a conveyor belt that stops the loader when it's full.

**Your anchor.** Turing claim/unclaim of tasks: within one process an `asyncio.Lock` is enough, but across pods you used Redis locks. Know why the in-process lock isn't sufficient.

**Check.** "How do you implement backpressure in an async producer/consumer pipeline?" (R3 Q22.) "Can you have a race condition in single-threaded asyncio? Show me."

**Script.** `python scripts/async/04_locks_semaphores_queues.py`

### 8. Threads, processes and mixing sync with async

**Teach.**
- `await asyncio.to_thread(fn, *args)` runs a blocking function in the default thread pool, keeping the loop free. Use it for sync I/O libraries.
- **CPU-heavy:** `loop.run_in_executor(ProcessPoolExecutor(), fn, *args)`. It's truly parallel, but arguments and results are **pickled** (cost, plus picklability limits) and process start-up is expensive (warm the pool).
- Better for heavy or long work: **a separate worker service** behind a queue (Celery or a consumer). Independent scaling, retries, and no fighting the web pods for CPU.
- From another thread *into* the loop: `asyncio.run_coroutine_threadsafe(coro, loop)`.
- **FastAPI specifics:**
  - a `def` endpoint runs in a threadpool (AnyIO, 40 threads by default)
  - an `async def` endpoint runs *on the loop*, so a blocking call inside it blocks everything
  - **rule:** use `async def` only if everything inside awaits. Otherwise use `def`.
- Thread races in the classic sense: shared mutable state plus non-atomic ops. Find them with stress tests, logging thread IDs, `faulthandler`, or thread-sanitizer-style tooling. The fix is a lock, or avoiding shared state (queues, immutability).

**Your anchor.** The `scripts/async/05` numbers you saw: process pool ≈ parallel speed-up; threads were *slower* than sequential for pure-Python CPU (GIL contention).

**Check.** "How would you run a CPU-heavy function inside an async service without stalling it? Compare `run_in_executor`, a process pool and a separate worker service." (R3 Q21.) "def vs async def in FastAPI: what does FastAPI do differently?" (R2 Q19.) "Tell me about a race condition you actually debugged." (R3 Q23; prepare a real story.)

**Script.** `python scripts/async/05_blocking_cpu_threads_processes.py`

### 9. Async context managers and async generators

**Teach.**
- `async with`: `__aenter__`/`__aexit__`. Use it for connections, sessions, locks, TaskGroups and timeouts.
- `@asynccontextmanager` is the generator form. **FastAPI `lifespan` is exactly this:** create the pools before `yield`, close them after.
- `async for` over async iterators / async generators (`async def` + `yield`), for streaming rows, pages or LLM tokens.
- **The gotcha:** if a consumer breaks out of an `async for` early, the async generator's `finally` doesn't run until it's garbage-collected (or never, on loop shutdown). Wrap it in `contextlib.aclosing(gen)` for deterministic cleanup. This matters when the generator holds a DB cursor or an HTTP stream.

**Your anchor.** SSE endpoints at Turing: an async generator yielding tokens from the model stream. Client disconnect leads to cancellation leads to cleanup of the upstream stream.

**Check.** "How does a FastAPI dependency with `yield` relate to async context managers? Where does the transaction commit?" (R3 Q25; you covered this, so connect the mechanism.)

**Script.** `python scripts/async/06_async_iterators_and_context_managers.py`

### 10. contextvars: per-request state in async code

**Teach.**
- Globals are shared by every request. `threading.local` breaks in asyncio (all tasks share one thread). **`contextvars.ContextVar`** gives each task its own value: each Task runs in a **copy of the context taken when it was created**.
- Use them for request IDs, correlation/trace IDs, the current tenant, and the current user.
- Set them in middleware: `token = request_id.set(...)`, and later `request_id.reset(token)`. Logging filters then read them so every log line carries the request ID automatically.
- A child task sees the parent's values *at creation time*. Changes in the child don't flow back to the parent.
- OpenTelemetry uses contextvars for span context propagation.

**Your anchor.** Your R3 Q24 answer called correlation IDs "trace IDs". Fix the vocabulary:
- **correlation/request ID**: your app-level ID per request, echoed in responses and logs
- **trace ID**: OpenTelemetry's ID across spans and services; often the same value is used for both, but they're different concepts

Both live in contextvars.

**Check.** "What are contextvars and why do they exist for async code?" (R3 Q14.)

**Script.** `python scripts/async/07_contextvars.py`

### 11. Putting it together: the production patterns

**Teach.** These are the four patterns interviewers whiteboard:
1. **Bounded worker pool:** N workers pulling from a `Queue`, or a `Semaphore` around a `TaskGroup` fan-out, for 10k URLs with max 50 concurrent. Add **per-host** limits (a dict of semaphores), so you're not limited to the global one.
2. **Retries with exponential backoff + full jitter:** `sleep(random.uniform(0, min(cap, base * 2**attempt)))`. Retry only transient errors (timeouts, 429, 503), respect `Retry-After`, and cap the attempts *and* the total time.
3. **Token-bucket rate limiter:** refill r tokens/sec up to burst b; acquire before each call. (The token bucket was a hazy point in R3 Q26.)
4. **Global timeout + graceful shutdown:** `asyncio.timeout` around the whole job; on SIGTERM, stop intake, drain in-flight work with a deadline, then cancel the rest (the W9 K8s demo is the HTTP version).

**Check.** The R3 Q20 whiteboard, out loud: "10,000 URLs, max 50 concurrent, per-host rate limiting, retries with jitter, a global timeout." Talk through the structure before any code.

**Script.** `python scripts/async/08_production_patterns.py`

---

## Wednesday lab (60–75 min)

1. **Predict, then run:** for scripts 02, 03 and 04, change one parameter each (e.g. make a different task fail first; shorten a timeout; set the Queue maxsize to 1). **Write your predicted output first**, then run.
2. **From memory, no peeking:** write `bounded_fetch.py`:
   - `fetch_all(urls, max_concurrency=50, per_host=5, timeout_total=30)`
   - retries with full jitter on simulated transient errors (use `asyncio.sleep` + `random` to fake latency and failures)
   - a `TaskGroup`, so one *fatal* error cancels everything
   - a results dict + an errors dict
   - Then compare with `scripts/async/08_production_patterns.py` and note what you missed.
3. **Blocking detector:** add a `time.sleep(0.3)` inside an async handler in a tiny script; enable debug mode and see the slow-callback warning; then run your loop-lag monitor and watch it spike.

## Thursday cheat sheet must include

- [ ] Concurrency vs parallelism, plus the asyncio/threads/processes decision table
- [ ] Coroutine vs Task vs Future; why `await a; await b` is sequential
- [ ] 4 ways to detect a blocked loop; 3 ways to fix it
- [ ] The gather / TaskGroup / as_completed / wait table, with the on-error behaviour
- [ ] Structured concurrency in one sentence; the weak-reference task gotcha and its fix
- [ ] Cancellation mechanics, "never swallow", `timeout` vs `timeout_at` vs `wait_for`, shield
- [ ] Lock / Semaphore / Event / Queue, one use each; a race across an `await`
- [ ] FastAPI `def` vs `async def` rule
- [ ] `aclosing` and lifespan
- [ ] contextvars copy semantics; correlation ID vs trace ID
- [ ] The full-jitter formula and the token-bucket rule

## Friday quiz (40 min)

- **New:** R3 Q15–23 (all nine; Q20 as a spoken design), R2 Q11–13, Q19.
- **Debug scenario:** one from R3 J involving async, or improvise: "after adding an LLM call to an endpoint, health checks started failing."
- **Spaced review:** R3 Q15/Q16/Q17 count as misses, so a `covered` sets them to `1/2`. Also 1 W2 miss.
- **Log:** `async_concurrency` in the knowledge map; note specifically whether the TaskGroup semantics are now solid.

## Infographic brief

Already drafted as a sample: [infographics/W03_async.svg](infographics/W03_async.svg). After writing your own cheat sheet, compare with it and tell Claude what's missing or wrong for *you*, and it gets revised.

## Done when

- [ ] R3 Q16 and Q17 answered `covered` (the two gaps closed)
- [ ] The bounded fetcher was written from memory with TaskGroup + Semaphore + retries + timeout
- [ ] You can explain how to detect a blocked loop in prod in under 60 seconds
