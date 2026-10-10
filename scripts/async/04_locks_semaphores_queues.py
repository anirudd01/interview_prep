"""
04 - Races in async code, Lock, Semaphore, Event, Queue + backpressure
=======================================================================

Run:  python scripts/async/04_locks_semaphores_queues.py

"ASYNC IS SINGLE-THREADED, SO NO RACE CONDITIONS, RIGHT?"  -- WRONG
--------------------------------------------------------------------
No two coroutines run Python bytecode at the same instant, so `x += 1` with no
await in between IS atomic w.r.t. other coroutines. But any *check-then-act that
spans an await* is a race: you check, you await (others run and change state),
you act on stale data. Classic: "if not in cache: await fetch(); cache[k] = v"
-> 100 concurrent requests all miss and all hit the DB (cache stampede).

PRIMITIVES (asyncio versions - NOT thread-safe, use only within one loop)
--------------------------------------------------------------------------
  Lock          mutual exclusion across awaits.        `async with lock:`
  Semaphore(n)  at most n holders. THE tool for bounding concurrency
                (max 20 outbound HTTP calls, max 10 DB queries in flight).
  BoundedSemaphore  same, but raises if released more than acquired (catches bugs).
  Event         one-shot broadcast flag: many waiters, one set(). Shutdown signals.
  Condition     wait-until-predicate with a lock. Rarely needed; Queue covers most.
  Queue(maxsize) producer/consumer. maxsize > 0 gives BACKPRESSURE: put() awaits
                when full, so a fast producer is slowed to consumer speed instead
                of buffering unbounded memory until OOM.

BACKPRESSURE (Round 3 Q22) - say it like this
---------------------------------------------
"Every buffer between stages is bounded. When a downstream stage is slow its
queue fills, the upstream put() awaits, and the slowdown propagates back to the
source - ultimately to the Kafka consumer pausing or the HTTP server returning
429/503. Unbounded queues don't remove the problem, they convert latency into an
OOM kill." Same idea as Kafka consumer lag, TCP windows, RabbitMQ prefetch.

Threading note: these asyncio primitives are not threadsafe. For thread<->loop
handoff use loop.call_soon_threadsafe / asyncio.run_coroutine_threadsafe (script 05).
"""

import asyncio
import random
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# 1. Race condition across an await, then fixed with a Lock
# ---------------------------------------------------------------------------
class Account:
    def __init__(self, balance: int) -> None:
        self.balance = balance
        self.lock = asyncio.Lock()

    async def withdraw_racy(self, amount: int) -> bool:
        if self.balance >= amount:          # check
            await asyncio.sleep(0.01)       # e.g. await fraud_service.check()
            self.balance -= amount          # act on stale check
            return True
        return False

    async def withdraw_safe(self, amount: int) -> bool:
        async with self.lock:               # whole check-then-act is one critical section
            if self.balance >= amount:
                await asyncio.sleep(0.01)
                self.balance -= amount
                return True
            return False


async def demo_race() -> None:
    section("1. Race: 5 concurrent withdrawals of 60 from a balance of 100")
    acc = Account(100)
    ok = await asyncio.gather(*(acc.withdraw_racy(60) for _ in range(5)))
    print(f"racy : approved={sum(ok)}  final balance={acc.balance}   <-- overdrawn!")

    acc = Account(100)
    ok = await asyncio.gather(*(acc.withdraw_safe(60) for _ in range(5)))
    print(f"lock : approved={sum(ok)}  final balance={acc.balance}")
    print("=> in prod with multiple workers/pods you need a DB row lock or\n"
          "   SELECT ... FOR UPDATE / conditional UPDATE - an asyncio.Lock is per-process.")


# ---------------------------------------------------------------------------
# 2. Cache stampede + per-key lock (single-flight)
# ---------------------------------------------------------------------------
DB_CALLS = 0


async def load_from_db(key: str) -> str:
    global DB_CALLS
    DB_CALLS += 1
    await asyncio.sleep(0.05)
    return f"value-of-{key}"


class SingleFlightCache:
    """Only one coroutine per key actually loads; others wait and reuse."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def get(self, key: str) -> str:
        if key in self.data:
            return self.data[key]
        lock = self.locks.setdefault(key, asyncio.Lock())  # no await -> atomic
        async with lock:
            if key not in self.data:  # double-check after acquiring
                self.data[key] = await load_from_db(key)
        return self.data[key]


async def demo_stampede() -> None:
    global DB_CALLS
    section("2. Cache stampede: 100 concurrent gets for the same cold key")
    naive: dict[str, str] = {}

    async def naive_get(key: str) -> str:
        if key not in naive:
            naive[key] = await load_from_db(key)
        return naive[key]

    DB_CALLS = 0
    await asyncio.gather(*(naive_get("user:42") for _ in range(100)))
    print(f"naive cache       -> DB calls: {DB_CALLS}")

    DB_CALLS = 0
    cache = SingleFlightCache()
    await asyncio.gather(*(cache.get("user:42") for _ in range(100)))
    print(f"single-flight     -> DB calls: {DB_CALLS}")


# ---------------------------------------------------------------------------
# 3. Semaphore: bound concurrency
# ---------------------------------------------------------------------------
async def demo_semaphore() -> None:
    section("3. Semaphore(3): 10 calls, never more than 3 in flight")
    sem = asyncio.Semaphore(3)
    in_flight = 0
    peak = 0

    async def call_api(i: int) -> None:
        nonlocal in_flight, peak
        async with sem:
            in_flight += 1
            peak = max(peak, in_flight)
            print(f"{t()} call {i} start (in flight: {in_flight})")
            await asyncio.sleep(0.1)
            in_flight -= 1

    await asyncio.gather(*(call_api(i) for i in range(10)))
    print(f"peak concurrency = {peak}")
    print("=> note: gather still created 10 coroutines up front. For 10k+ items\n"
          "   use a fixed worker pool + Queue instead (demo 5, and script 08).")


# ---------------------------------------------------------------------------
# 4. Event: one signal, many waiters
# ---------------------------------------------------------------------------
async def demo_event() -> None:
    section("4. Event: workers wait for 'config loaded' before serving")
    ready = asyncio.Event()

    async def worker(i: int) -> None:
        await ready.wait()
        print(f"{t()} worker {i} serving")

    workers = [asyncio.create_task(worker(i)) for i in range(3)]
    await asyncio.sleep(0.1)
    print(f"{t()} config loaded -> ready.set()")
    ready.set()
    await asyncio.gather(*workers)


# ---------------------------------------------------------------------------
# 5. Queue: producer/consumer pipeline with backpressure
# ---------------------------------------------------------------------------
async def demo_queue_backpressure() -> None:
    section("5. Queue(maxsize=3): fast producer gets throttled by slow consumers")
    queue: asyncio.Queue[int] = asyncio.Queue(maxsize=3)
    N_WORKERS = 2

    async def producer() -> None:
        for i in range(8):
            before = time.perf_counter()
            await queue.put(i)  # awaits while the queue is full
            waited = time.perf_counter() - before
            note = f"  (blocked {waited * 1000:.0f}ms - backpressure)" if waited > 0.01 else ""
            print(f"{t()} produced {i}, qsize={queue.qsize()}{note}")

    async def consumer(wid: int) -> None:
        while True:
            item = await queue.get()
            try:
                await asyncio.sleep(random.uniform(0.08, 0.12))  # slow work
                print(f"{t()}      worker {wid} handled {item}")
            finally:
                queue.task_done()  # ALWAYS, even on error, or join() hangs

    async with asyncio.TaskGroup() as tg:
        consumers = [tg.create_task(consumer(w)) for w in range(N_WORKERS)]
        await producer()
        await queue.join()  # waits until task_done() called for every item
        for c in consumers:  # consumers loop forever; stop them explicitly
            c.cancel()
    # 3.13+ alternative: queue.shutdown() makes get() raise QueueShutDown.
    # Pre-3.13 alternative: put one sentinel (None) per worker.
    print("all items processed, workers stopped")


async def main() -> None:
    await demo_race()
    await demo_stampede()
    await demo_semaphore()
    await demo_event()
    await demo_queue_backpressure()


if __name__ == "__main__":
    asyncio.run(main())
