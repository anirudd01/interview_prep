# Async refresher scripts

Runnable, stdlib-only (Python 3.11+). Each file stands alone: the module docstring
is the explanation, the demos prove it, and the timestamps in the output show what
actually overlapped. Read the docstring first, run it, then read the code.

```bash
python scripts/async/01_event_loop_and_coroutines.py
```

| File | What it covers | Interview questions |
| --- | --- | --- |
| [01_event_loop_and_coroutines.py](01_event_loop_and_coroutines.py) | Loop mental model, coroutine vs task, sequential vs concurrent, blocking the loop, loop-lag metric, debug mode | R3 Q15, R2 Q1 |
| [02_gather_taskgroup_as_completed.py](02_gather_taskgroup_as_completed.py) | gather vs TaskGroup vs as_completed vs wait, structured concurrency, orphan tasks, fire-and-forget GC gotcha | R3 Q16, Q17, Q18 |
| [03_cancellation_and_timeouts.py](03_cancellation_and_timeouts.py) | How cancel works, never swallow CancelledError, asyncio.timeout / timeout_at / wait_for, shield, bounded cleanup | R3 Q19 |
| [04_locks_semaphores_queues.py](04_locks_semaphores_queues.py) | Races across awaits, Lock, single-flight cache, Semaphore, Event, Queue + backpressure | R3 Q22, Q23 |
| [05_blocking_cpu_threads_processes.py](05_blocking_cpu_threads_processes.py) | to_thread vs process pool, when the GIL doesn't matter, thread to loop handoff, FastAPI def vs async def | R3 Q21, R2 Q1 |
| [06_async_iterators_and_context_managers.py](06_async_iterators_and_context_managers.py) | async with / async for, asynccontextmanager (FastAPI lifespan), async generators, aclosing, streaming | R3 Q25 (Depends + yield) |
| [07_contextvars.py](07_contextvars.py) | Request-ID propagation, why globals/threading.local break, copy semantics, token reset | R3 Q14 |
| [08_production_patterns.py](08_production_patterns.py) | 10k-URL worker pool, retries + full jitter, token bucket, graceful shutdown + K8s preStop | R3 Q20, Q26, Q27, Q29 |

## 60-second recap

- asyncio is one thread doing cooperative multitasking. It only switches at `await`. Concurrent, not parallel.
- Anything slow without `await` blocks every other request. Offload it: I/O goes to `to_thread`, CPU goes to a process pool, and heavy work goes to a queue.
- Default to `TaskGroup`. Use `gather(return_exceptions=True)` for best-effort fan-out, `as_completed` for streaming, and `wait(FIRST_COMPLETED)` for races.
- Cancellation is an exception raised at the next `await`. Clean up in `finally` and always re-raise.
- Single-threaded doesn't mean race-free. A check-then-act across an `await` needs a Lock. Across pods it needs the DB or Redis.
- Bound every buffer (`Queue(maxsize)`, `Semaphore`). Backpressure beats OOM.
- `contextvars` give per-task state (request ID, trace span). Globals and `threading.local` don't.

Not covered here yet (good next scripts): anyio/trio, uvloop, `asyncio.Runner`, eager task factory (3.12), async DB drivers (asyncpg pool sizing), free-threaded Python 3.13t.
