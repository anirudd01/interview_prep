"""
05 - Sync code inside async: threads, processes, the GIL, and crossing loop boundaries
======================================================================================

Run:  python scripts/async/05_blocking_cpu_threads_processes.py

THE DECISION TREE (Round 3 Q21, Round 2 Q1)
-------------------------------------------
You have a sync function to call from an async service. What kind of work is it?

  Blocking I/O with no async library (boto3, requests, sync DB driver, file I/O)
      -> await asyncio.to_thread(fn, *args)
         Runs in the loop's default ThreadPoolExecutor. The GIL is RELEASED while
         a thread waits on I/O, so this really does run concurrently.

  CPU-bound pure Python (parsing, scoring, big loops)
      -> await loop.run_in_executor(process_pool, fn, *args)
         Threads won't help: only one thread runs Python bytecode at a time
         (GIL). A process has its own interpreter + GIL -> real parallelism.
         Costs: args/results are pickled across the boundary, fn must be a
         top-level importable function, process startup is slow (create the pool
         once, at app startup).

  CPU-bound in a C extension that releases the GIL (numpy, hashlib on big
  buffers, zlib, many image libs)
      -> to_thread is often enough - the C code runs outside the GIL.

  Heavy or long-running (seconds+), or must survive a pod restart
      -> don't do it in the web process at all. Queue it (Celery/RabbitMQ/Kafka)
         and return a job id. (Your Round 3 Q30 answer.)

WHEN THE GIL "GENUINELY DOESN'T MATTER" (Round 2 Q1 - you missed these)
-----------------------------------------------------------------------
  1. I/O-bound work: the GIL is released during blocking syscalls (socket read,
     sleep, file read), so threads overlap fine.
  2. C extensions that release it explicitly (numpy ops, hashlib, compression).
  3. Multiprocessing: each process has its own GIL.
  Bonus 2026 answer: Python 3.13+ has an optional free-threaded build (PEP 703,
  `python3.13t`), still opt-in; and 3.12+ per-interpreter GIL for subinterpreters.

THREADS <-> LOOP
----------------
  From a worker thread you CANNOT call loop methods or await directly. Use:
    asyncio.run_coroutine_threadsafe(coro, loop) -> concurrent.futures.Future
    loop.call_soon_threadsafe(callback, *args)
  Common in: Kafka consumer threads, legacy callbacks, SDKs that call you back
  on their own thread.

FASTAPI TIE-IN
--------------
  `def` route      -> FastAPI runs it via a threadpool (anyio, default 40 threads).
                      Blocking inside is fine, but the pool size caps concurrency.
  `async def` route-> runs on the loop. Must await or offload everything slow.
"""

import asyncio
import concurrent.futures
import threading
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# Must be top-level (module scope) so ProcessPoolExecutor can pickle it by name.
def cpu_heavy(n: int) -> int:
    """Pure-Python CPU work. Holds the GIL the whole time."""
    total = 0
    for i in range(n):
        total += i * i % 7
    return total


def blocking_io(seconds: float) -> str:
    """Stand-in for requests.get / boto3 / a sync DB driver."""
    time.sleep(seconds)  # releases the GIL while sleeping, like real I/O
    return f"io({seconds}) on {threading.current_thread().name}"


# ---------------------------------------------------------------------------
async def demo_to_thread() -> None:
    section("1. Blocking I/O: direct call vs asyncio.to_thread (5 calls x 0.2s)")
    s = time.perf_counter()
    for _ in range(5):
        blocking_io(0.2)  # each one freezes the loop
    print(f"direct, sequential, loop blocked: {time.perf_counter() - s:.2f}s")

    s = time.perf_counter()
    results = await asyncio.gather(*(asyncio.to_thread(blocking_io, 0.2) for _ in range(5)))
    print(f"to_thread, concurrent:            {time.perf_counter() - s:.2f}s")
    print(f"   e.g. {results[0]}")


# ---------------------------------------------------------------------------
async def demo_cpu_threads_vs_processes(pool: concurrent.futures.ProcessPoolExecutor) -> None:
    N = 10_000_000
    jobs = 4
    section(f"2. CPU-bound: {jobs} jobs of cpu_heavy({N:,})")
    loop = asyncio.get_running_loop()
    # Warm the pool first so we time the work, not process startup (Windows
    # spawns fresh interpreters - that's why you create the pool once at startup).
    await asyncio.gather(*(loop.run_in_executor(pool, cpu_heavy, 1) for _ in range(jobs)))

    s = time.perf_counter()
    for _ in range(jobs):
        cpu_heavy(N)
    seq = time.perf_counter() - s
    print(f"sequential on the loop:   {seq:.2f}s  (and the loop was frozen the whole time)")

    s = time.perf_counter()
    await asyncio.gather(*(asyncio.to_thread(cpu_heavy, N) for _ in range(jobs)))
    print(f"threads (to_thread):      {time.perf_counter() - s:.2f}s  <- no speedup, often SLOWER (GIL contention)")

    s = time.perf_counter()
    await asyncio.gather(*(loop.run_in_executor(pool, cpu_heavy, N) for _ in range(jobs)))
    print(f"processes (run_in_executor): {time.perf_counter() - s:.2f}s  <- real parallelism")
    print("=> threads still help one thing here: the LOOP stays responsive. They just\n"
          "   don't make the CPU work itself faster.")


# ---------------------------------------------------------------------------
async def demo_thread_to_loop() -> None:
    section("3. A plain thread submitting work back to the event loop")
    loop = asyncio.get_running_loop()

    async def handle_message(msg: str) -> str:
        await asyncio.sleep(0.05)
        return f"handled {msg!r} on the loop"

    def legacy_consumer_thread() -> None:
        # Imagine a Kafka/RabbitMQ client that delivers messages on its own thread.
        for msg in ("m1", "m2"):
            fut = asyncio.run_coroutine_threadsafe(handle_message(msg), loop)
            print(f"{t()} thread got: {fut.result(timeout=1)}")  # blocks the THREAD, not the loop
        loop.call_soon_threadsafe(print, f"{t()} thread: done (scheduled via call_soon_threadsafe)")

    await asyncio.to_thread(legacy_consumer_thread)
    await asyncio.sleep(0)  # let the call_soon_threadsafe callback run


# ---------------------------------------------------------------------------
async def demo_default_executor_size() -> None:
    section("4. The default thread pool is finite")
    # Default ThreadPoolExecutor max_workers = min(32, os.cpu_count() + 4).
    # 200 concurrent to_thread calls doing slow I/O will queue behind each other.
    # For heavy offloading, set your own: loop.set_default_executor(ThreadPoolExecutor(64)).
    import os
    print(f"cpu_count={os.cpu_count()}, default max_workers=min(32, cpu+4)="
          f"{min(32, (os.cpu_count() or 1) + 4)}")


async def main() -> None:
    await demo_to_thread()
    # Create the process pool ONCE (at app startup in a real service).
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        await demo_cpu_threads_vs_processes(pool)
    await demo_thread_to_loop()
    await demo_default_executor_size()


if __name__ == "__main__":
    # The __main__ guard is REQUIRED for ProcessPoolExecutor on Windows/macOS
    # (spawn start method re-imports this module in each child).
    asyncio.run(main())
