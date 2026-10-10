"""
01 - Event loop, coroutines, tasks, and "blocking the loop"
=============================================================

Run:  python scripts/async/01_event_loop_and_coroutines.py

MENTAL MODEL (say this in an interview)
---------------------------------------
asyncio is *cooperative* multitasking on ONE thread. The event loop is a while-loop
that keeps a queue of "ready" callbacks and asks the OS (select/epoll/IOCP) which
sockets are ready. A coroutine runs until it hits an `await` on something that is
not ready yet; at that point it *yields control back to the loop*, and the loop
runs something else. Nothing is pre-empted. If your code never awaits, nobody
else runs. That's the whole model.

Vocabulary:
  - coroutine function : `async def f(): ...`        -> calling f() runs NOTHING,
  - coroutine object   : `f()`                       -> it just builds a paused frame.
  - await              : "run this to completion, and let the loop do other work
                          while it's waiting". Awaiting a coroutine directly is
                          SEQUENTIAL - it does not create concurrency.
  - Task               : `asyncio.create_task(f())` -> wraps the coroutine and
                          schedules it on the loop NOW. This is how you get
                          concurrency. A Task is a Future subclass.
  - Future             : low-level "a result that will exist later". You rarely
                          create one yourself; libraries do.

INTERVIEW ANGLES (Round 3 Q15, Round 2 Q1)
------------------------------------------
- "Is asyncio parallel?"  No. Concurrent, not parallel. One thread, one core.
  It wins for I/O-bound work (many sockets waiting), not CPU-bound work.
- "What is blocking the loop?"  Any sync call that takes real time inside an
  `async def`: time.sleep, requests.get, a sync DB driver, json.loads on a 50MB
  payload, a tight CPU loop. While it runs, EVERY other request on that worker
  stalls - latency spikes for everyone, health checks time out, K8s may kill the pod.
- "How do you detect it?"
    1. asyncio debug mode: `asyncio.run(main(), debug=True)` or PYTHONASYNCIODEBUG=1
       logs "Executing <Task ...> took 0.25 seconds" for any step slower than
       loop.slow_callback_duration (default 100ms). Demo below.
    2. py-spy dump / py-spy top on the live process - shows the stack the loop
       thread is stuck in. Works in prod, no code change.
    3. Loop-lag metric: a background task that sleeps 1s and measures how late it
       woke up. Export as a gauge. Lag > ~50ms = something is blocking.
- FastAPI specifically: `def` endpoints run in a threadpool (safe to block),
  `async def` endpoints run ON the loop (must never block). Putting a sync
  requests.get inside `async def` is the classic bug.
"""

import asyncio
import logging
import time

START = time.perf_counter()


def t() -> str:
    """Seconds since script start - lets you SEE what overlapped."""
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def fake_io(name: str, seconds: float) -> str:
    """Stands in for a network call. asyncio.sleep yields to the loop - that's
    exactly what a real socket read does when no data has arrived yet."""
    print(f"{t()} {name}: start")
    await asyncio.sleep(seconds)
    print(f"{t()} {name}: done")
    return name


# ---------------------------------------------------------------------------
# 1. Calling a coroutine function does nothing
# ---------------------------------------------------------------------------
async def demo_coroutine_object() -> None:
    section("1. Calling an async function just builds a coroutine object")
    coro = fake_io("never-awaited", 0.1)
    print(f"type: {type(coro).__name__}  -> nothing printed 'start', nothing ran")
    # If you forget to await it, Python warns: "coroutine ... was never awaited".
    # Closing it explicitly suppresses that warning for the demo.
    coro.close()


# ---------------------------------------------------------------------------
# 2. await-in-a-row is SEQUENTIAL; create_task is CONCURRENT
# ---------------------------------------------------------------------------
async def demo_sequential_vs_concurrent() -> None:
    section("2a. Sequential: await, await, await  (~0.9s)")
    s = time.perf_counter()
    await fake_io("A", 0.3)
    await fake_io("B", 0.3)
    await fake_io("C", 0.3)
    print(f"total: {time.perf_counter() - s:.2f}s")

    section("2b. Concurrent: create_task x3, then await them  (~0.3s)")
    s = time.perf_counter()
    # create_task schedules immediately; the tasks start running at the next
    # point where we yield to the loop (our first await below).
    ta = asyncio.create_task(fake_io("A", 0.3))
    tb = asyncio.create_task(fake_io("B", 0.3))
    tc = asyncio.create_task(fake_io("C", 0.3))
    await ta
    await tb
    await tc
    print(f"total: {time.perf_counter() - s:.2f}s")


# ---------------------------------------------------------------------------
# 3. Blocking the loop - the #1 production asyncio bug
# ---------------------------------------------------------------------------
async def heartbeat(stop: asyncio.Event) -> None:
    """Pretend this is 'every other request on the worker'. It wants to tick
    every 100ms. Watch it freeze while the bad handler runs."""
    while not stop.is_set():
        print(f"{t()}   heartbeat tick")
        await asyncio.sleep(0.1)


async def bad_handler() -> None:
    print(f"{t()} bad_handler: calling time.sleep(0.5) - loop is FROZEN")
    time.sleep(0.5)  # sync! no await -> nobody else can run
    print(f"{t()} bad_handler: done")


async def good_handler() -> None:
    print(f"{t()} good_handler: awaiting asyncio.sleep(0.5) - loop keeps running")
    await asyncio.sleep(0.5)
    print(f"{t()} good_handler: done")


async def demo_blocking() -> None:
    for handler in (bad_handler, good_handler):
        section(f"3. {handler.__name__} next to a 100ms heartbeat")
        stop = asyncio.Event()
        hb = asyncio.create_task(heartbeat(stop))
        await asyncio.sleep(0.15)  # let the heartbeat tick a couple of times
        await handler()
        stop.set()
        await hb
    print("\nNotice: during bad_handler there is a ~0.5s gap with no ticks.")


# ---------------------------------------------------------------------------
# 4. Measuring loop lag - the metric you'd actually export in prod
# ---------------------------------------------------------------------------
async def loop_lag_monitor(interval: float, samples: int) -> list[float]:
    """Sleep `interval`, measure how late we woke up. Late = loop was busy."""
    lags = []
    for _ in range(samples):
        before = time.perf_counter()
        await asyncio.sleep(interval)
        lags.append(time.perf_counter() - before - interval)
    return lags


async def demo_loop_lag() -> None:
    section("4. Loop-lag monitor (what you'd export as a Prometheus gauge)")
    monitor = asyncio.create_task(loop_lag_monitor(0.05, 6))
    await asyncio.sleep(0.12)
    time.sleep(0.3)  # simulate a blocking call somewhere in the app
    lags = await monitor
    for i, lag in enumerate(lags):
        flag = "  <-- something blocked the loop" if lag > 0.05 else ""
        print(f"sample {i}: lag {lag * 1000:6.1f} ms{flag}")


# ---------------------------------------------------------------------------
# 5. Debug mode catches slow steps for you
# ---------------------------------------------------------------------------
async def slow_step() -> None:
    time.sleep(0.25)  # blocks inside one "step" of the task


def demo_debug_mode() -> None:
    section("5. asyncio debug mode: watch stderr for 'Executing <Task...> took 0.25 seconds'")
    logging.basicConfig(level=logging.WARNING, format="    LOG %(name)s: %(message)s")
    # debug=True also: warns on never-awaited coroutines, on non-threadsafe calls
    # from other threads, and records where each task was created.
    asyncio.run(slow_step(), debug=True)


async def main() -> None:
    await demo_coroutine_object()
    await demo_sequential_vs_concurrent()
    await demo_blocking()
    await demo_loop_lag()


if __name__ == "__main__":
    # asyncio.run(): creates a new loop, runs main() to completion, cancels any
    # leftover tasks, shuts down async generators + the default executor, closes
    # the loop. One per program entry point; don't nest it.
    asyncio.run(main())
    demo_debug_mode()  # separate asyncio.run because it needs debug=True
