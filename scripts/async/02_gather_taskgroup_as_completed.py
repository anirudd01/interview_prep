"""
02 - Running many things at once: gather vs TaskGroup vs as_completed vs wait
=============================================================================

Run:  python scripts/async/02_gather_taskgroup_as_completed.py      (Python 3.11+)

THE ONE-TABLE ANSWER (Round 3 Q16 - this is what the interviewer wants)
------------------------------------------------------------------------
                    | results order  | one child fails...              | you get
--------------------+----------------+---------------------------------+---------------------
gather(*aws)        | input order    | first exception propagates to   | list of results
                    |                | the awaiter, OTHER CHILDREN     |
                    |                | KEEP RUNNING (orphans!)         |
gather(...,         | input order    | exceptions returned as values   | list of results/excs
  return_exceptions)|                | in the list, nobody cancelled   |
TaskGroup (3.11+)   | you hold tasks | siblings CANCELLED, group waits | ExceptionGroup of
                    |                | for them, raises ExceptionGroup | ALL real failures
as_completed(aws)   | finish order   | that awaitable raises when you  | stream as they land
                    |                | await it; others untouched      |
wait(aws, ...)      | sets           | never raises; you inspect       | (done, pending)
                    |                | done tasks yourself             |

Rule of thumb:
  - Default to TaskGroup. It's *structured concurrency*: no task can outlive the
    `async with` block, failures cancel siblings, and all errors are reported.
  - Use gather(return_exceptions=True) when you want "best effort, collect all"
    (e.g. fan-out to 5 recommendation sources, use whatever succeeded).
  - Use as_completed when you want to process results as soon as each arrives
    (stream to client, first-N-wins).
  - Use wait(FIRST_COMPLETED) for racing / hedged requests, then cancel the rest.

STRUCTURED CONCURRENCY (Round 3 Q17)
------------------------------------
"Concurrency with a scope." Every task has a parent block; the block doesn't exit
until all its children are done; an error in a child cancels its siblings and
propagates to the parent. Same idea as a function call: you can't return while
your callee is still running. Without it (bare create_task / gather) you get
orphan tasks still hitting the DB after the request already returned a 500.
Comes from Trio (nurseries); anyio TaskGroup gives the same on asyncio.

THE GC GOTCHA (Round 3 Q18)
---------------------------
The event loop only keeps a *weak* reference to tasks. A fire-and-forget
`asyncio.create_task(send_email())` with no reference stored can be garbage
collected mid-flight and silently vanish. Fix: keep a strong ref in a set and
discard it in a done callback (shown in demo 6), or just use a TaskGroup.
"""

import asyncio
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def work(name: str, seconds: float, fail: bool = False) -> str:
    try:
        await asyncio.sleep(seconds)
        if fail:
            raise ValueError(f"{name} failed")
        print(f"{t()}   {name} finished")
        return name
    except asyncio.CancelledError:
        print(f"{t()}   {name} was CANCELLED")
        raise  # always re-raise CancelledError (see script 03)


# ---------------------------------------------------------------------------
async def demo_gather_failure_orphans() -> None:
    section("1. gather: one fails -> exception propagates, others KEEP RUNNING")
    try:
        await asyncio.gather(
            work("fast-fail", 0.1, fail=True),
            work("slow-A", 0.4),
            work("slow-B", 0.4),
        )
    except ValueError as e:
        print(f"{t()} caught: {e!r}  - but slow-A/slow-B are still running...")
    await asyncio.sleep(0.5)  # watch them finish AFTER we already 'handled' it
    print("=> orphans: work you thought was abandoned still completes (side effects!)")


async def demo_gather_return_exceptions() -> None:
    section("2. gather(return_exceptions=True): collect everything, nothing cancelled")
    results = await asyncio.gather(
        work("ok-1", 0.1),
        work("bad", 0.1, fail=True),
        work("ok-2", 0.2),
        return_exceptions=True,
    )
    for r in results:  # same order as the inputs, not finish order
        print(f"   result: {r!r}")
    ok = [r for r in results if not isinstance(r, BaseException)]
    print(f"=> best-effort fan-out: used {len(ok)}/{len(results)} sources")


async def demo_taskgroup() -> None:
    section("3. TaskGroup: one fails -> siblings cancelled, ExceptionGroup raised")
    try:
        async with asyncio.TaskGroup() as tg:
            t1 = tg.create_task(work("slow-A", 0.4))
            tg.create_task(work("fast-fail", 0.1, fail=True))
            tg.create_task(work("also-fails", 0.1, fail=True))
            tg.create_task(work("slow-B", 0.4))
    # except* (3.11+) matches exceptions INSIDE the group by type.
    except* ValueError as eg:
        print(f"{t()} ExceptionGroup with {len(eg.exceptions)} ValueError(s):")
        for e in eg.exceptions:
            print(f"     - {e}")
    print(f"slow-A cancelled? {t1.cancelled()}  -> nothing outlived the block")

    section("3b. TaskGroup happy path: results via the task handles")
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(work(f"job-{i}", 0.1 * i)) for i in range(1, 4)]
    # Exiting the block == all tasks done. Safe to read .result() now.
    print(f"results: {[tk.result() for tk in tasks]}")


async def demo_as_completed() -> None:
    section("4. as_completed: handle results in FINISH order")
    coros = [work("slow", 0.3), work("fast", 0.1), work("medium", 0.2)]
    for next_done in asyncio.as_completed(coros):
        # In 3.11/3.12 these are new awaitables, not your original tasks, so
        # carry identity in the return value. (3.13+: `async for` yields originals.)
        result = await next_done
        print(f"{t()} got {result} -> process/stream it right away")

    section("4b. as_completed with timeout: stop waiting after 0.15s")
    try:
        for next_done in asyncio.as_completed(
            [work("x-fast", 0.1), work("x-slow", 1.0)], timeout=0.15
        ):
            result = await next_done
            print(f"{t()} got {result}")
    except TimeoutError:
        # NOTE: as_completed does NOT cancel the stragglers. x-slow keeps running
        # in the background through the next demos and only gets cancelled by
        # asyncio.run() at exit - watch for it on the last line. In real code,
        # wrap this in a TaskGroup or cancel the leftovers yourself.
        print(f"{t()} timed out waiting for the rest")


async def demo_wait_first_completed() -> None:
    section("5. wait(FIRST_COMPLETED): hedged request - race 2 replicas, cancel loser")
    replica_a = asyncio.create_task(work("replica-A", 0.3))
    replica_b = asyncio.create_task(work("replica-B", 0.1))
    done, pending = await asyncio.wait(
        {replica_a, replica_b}, return_when=asyncio.FIRST_COMPLETED
    )
    winner = done.pop().result()
    for p in pending:
        p.cancel()  # wait() never cancels for you
    await asyncio.gather(*pending, return_exceptions=True)  # let cancellation finish
    print(f"=> winner: {winner}")


# ---------------------------------------------------------------------------
_background: set[asyncio.Task] = set()


def fire_and_forget(coro) -> asyncio.Task:
    """The correct way to spawn a background task you won't await.
    Strong ref in a set; the done-callback removes it once finished."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def demo_fire_and_forget() -> None:
    section("6. Fire-and-forget without losing the task to GC")
    fire_and_forget(work("send-email", 0.1))
    print(f"live background tasks: {len(_background)}")
    await asyncio.sleep(0.2)
    print(f"after completion:      {len(_background)}")
    print("=> also log exceptions in the callback, or they only show at GC time")


async def main() -> None:
    await demo_gather_failure_orphans()
    await demo_gather_return_exceptions()
    await demo_taskgroup()
    await demo_as_completed()
    await demo_wait_first_completed()
    await demo_fire_and_forget()


if __name__ == "__main__":
    asyncio.run(main())
