"""
03 - Cancellation, timeouts, shield, and cleanup
=================================================

Run:  python scripts/async/03_cancellation_and_timeouts.py      (Python 3.11+)

HOW CANCELLATION ACTUALLY WORKS (Round 3 Q19)
---------------------------------------------
`task.cancel()` does NOT stop the task immediately. It sets a flag; the next time
the task is resumed at an `await`, `asyncio.CancelledError` is raised *inside the
task, at that await*. So:
  - Cancellation only happens at await points. A CPU loop with no awaits can't be
    cancelled (same root cause as "blocking the loop").
  - The task gets a chance to clean up: `finally:` blocks and `async with` exits
    run normally. You can even await inside them (briefly!).
  - CancelledError inherits from BaseException (since 3.8), NOT Exception, so a
    plain `except Exception:` doesn't swallow it. Good.
  - You must RE-RAISE it. If you catch and swallow it, the task looks like it
    completed normally; TaskGroup, asyncio.timeout() and shutdown logic all break
    because they rely on the cancellation propagating.

TIMEOUT TOOLS
-------------
  asyncio.timeout(s)      3.11+ context manager. Cancels whatever is running in the
                          block when the deadline hits, converts that to TimeoutError
                          at the `async with`. Preferred. Can cover several awaits.
                          asyncio.timeout_at(loop.time() + s) for absolute deadlines
                          (great for propagating one request deadline down calls).
  asyncio.wait_for(aw, s) Older single-awaitable version. Cancels the inner task on
                          timeout and raises TimeoutError.
  asyncio.shield(aw)      Protects the INNER operation from being cancelled by the
                          OUTER cancel. The outer await still raises CancelledError;
                          the inner keeps running. Use for "commit this DB write
                          even if the client disconnects". Keep a reference to the
                          inner task or it can be GC'd.

Since 3.11, asyncio.TimeoutError is just an alias of the builtin TimeoutError.

INTERVIEW ANGLE
---------------
"Client disconnects mid-request in FastAPI/Starlette - what happens to your
handler?" -> On disconnect the server may cancel the handler task; your awaits
raise CancelledError; `finally` / `async with` release the DB connection. If the
work must complete (payment write), shield it or hand it to a queue.
"""

import asyncio
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
async def worker_with_cleanup(name: str) -> None:
    print(f"{t()} {name}: acquired fake DB connection")
    try:
        for i in range(10):
            await asyncio.sleep(0.1)  # <- each of these is a cancellation point
            print(f"{t()} {name}: step {i}")
    except asyncio.CancelledError:
        print(f"{t()} {name}: got CancelledError at an await - cleaning up")
        raise  # <-- critical
    finally:
        # finally runs on success, error AND cancellation. Release resources here.
        print(f"{t()} {name}: released DB connection (finally)")


async def demo_cancel() -> None:
    section("1. task.cancel(): CancelledError raised at the next await, finally runs")
    task = asyncio.create_task(worker_with_cleanup("job"))
    await asyncio.sleep(0.25)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print(f"{t()} caller: task.cancelled() = {task.cancelled()}")


# ---------------------------------------------------------------------------
async def swallows_cancel() -> str:
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        return "pretended nothing happened"  # BUG: swallowed
    return "finished"


async def demo_swallowing_bug() -> None:
    section("2. BUG: swallowing CancelledError breaks timeouts")
    s = time.perf_counter()
    try:
        async with asyncio.timeout(0.1):
            result = await swallows_cancel()
        print(f"no TimeoutError raised! result={result!r} after {time.perf_counter() - s:.2f}s")
        print("=> caller thinks it succeeded. Timeouts/TaskGroups silently misbehave.")
    except TimeoutError:
        print("TimeoutError (this is what you'd want)")


# ---------------------------------------------------------------------------
async def slow_call(seconds: float) -> str:
    await asyncio.sleep(seconds)
    return f"slow_call({seconds}) ok"


async def demo_timeouts() -> None:
    section("3. asyncio.timeout(): one deadline covering several awaits")
    try:
        async with asyncio.timeout(0.25):
            print(f"{t()} {await slow_call(0.1)}")
            print(f"{t()} {await slow_call(0.1)}")
            print(f"{t()} {await slow_call(0.1)}")  # total 0.3 > 0.25
    except TimeoutError:
        print(f"{t()} TimeoutError - whole block exceeded its 0.25s budget")

    section("3b. Deadline propagation with timeout_at (one budget for a whole request)")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 0.25

    async def call_downstream(name: str, cost: float) -> None:
        remaining = deadline - loop.time()
        print(f"{t()} {name}: {remaining * 1000:.0f}ms of budget left")
        async with asyncio.timeout_at(deadline):
            await asyncio.sleep(cost)

    try:
        await call_downstream("auth", 0.1)
        await call_downstream("db", 0.1)
        await call_downstream("cache", 0.1)
    except TimeoutError:
        print(f"{t()} request deadline exceeded -> return 504, don't keep working")

    section("3c. wait_for(): the older single-awaitable form")
    try:
        await asyncio.wait_for(slow_call(1.0), timeout=0.1)
    except TimeoutError:
        print(f"{t()} wait_for timed out (inner coroutine was cancelled for us)")


# ---------------------------------------------------------------------------
async def critical_write() -> str:
    print(f"{t()}   critical_write: started")
    await asyncio.sleep(0.3)
    print(f"{t()}   critical_write: COMMITTED")
    return "committed"


async def demo_shield() -> None:
    section("4. shield(): outer request cancelled, inner write still completes")
    inner = asyncio.create_task(critical_write())  # keep a reference!

    async def handler() -> str:
        return await asyncio.shield(inner)

    request = asyncio.create_task(handler())
    await asyncio.sleep(0.1)
    request.cancel()  # client disconnected
    try:
        await request
    except asyncio.CancelledError:
        print(f"{t()} handler cancelled (client gone)")
    result = await inner
    print(f"{t()} but inner write result: {result}")


# ---------------------------------------------------------------------------
async def demo_cleanup_with_timeout() -> None:
    section("5. Cleanup that itself awaits - bound it, and it's still cancellable")

    async def job() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            # Awaiting in finally is allowed. Give cleanup its own short timeout
            # so a hung close() can't block shutdown forever.
            try:
                async with asyncio.timeout(0.2):
                    await asyncio.sleep(0.05)  # e.g. await conn.close()
                    print(f"{t()} job: flushed buffers and closed connection")
            except TimeoutError:
                print(f"{t()} job: cleanup timed out, giving up")

    task = asyncio.create_task(job())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    print(f"{t()} job fully stopped")


async def main() -> None:
    await demo_cancel()
    await demo_swallowing_bug()
    await demo_timeouts()
    await demo_shield()
    await demo_cleanup_with_timeout()


if __name__ == "__main__":
    asyncio.run(main())
