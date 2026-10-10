"""
07 - contextvars: request-scoped state that survives concurrency
================================================================

Run:  python scripts/async/07_contextvars.py

THE PROBLEM (Round 3 Q14)
-------------------------
You want every log line to carry the request_id / correlation id / tenant id
without passing it through 15 function signatures.
  - A global variable: request B overwrites request A's id mid-flight (both run
    on the same thread, interleaved at awaits).
  - threading.local: same bug - all coroutines share ONE thread, so they share
    one thread-local.
  - contextvars.ContextVar: each asyncio Task runs in its OWN copy of the
    context, snapshotted when the task is created. Sets inside a task are
    invisible to siblings and to the parent.

Who uses it: structlog/loguru contextual logging, OpenTelemetry's current span,
Starlette/FastAPI request state helpers, SQLAlchemy async scoped sessions,
asgi-correlation-id middleware.

RULES TO REMEMBER
-----------------
  1. create_task() copies the current context -> child sees parent's values at
     spawn time; child's later set() does not leak back to the parent.
  2. Plain `await coro()` (no new task) runs in the SAME context -> a set() in
     the callee IS visible to the caller afterwards.
  3. asyncio.to_thread() copies the context into the worker thread too.
     loop.run_in_executor() does NOT (you'd use contextvars.copy_context().run).
  4. var.set() returns a Token; var.reset(token) restores the old value. Use it
     in middleware so values don't bleed between requests on reused contexts.
"""

import asyncio
import contextvars
import random
import time

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

GLOBAL_REQUEST_ID = "-"  # the broken approach, for comparison


def log(msg: str) -> None:
    """Every log line picks up the id automatically - no parameter passing."""
    print(f"[req={request_id.get():>6}] [global={GLOBAL_REQUEST_ID:>6}] {msg}")


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def db_query() -> None:
    await asyncio.sleep(random.uniform(0.01, 0.05))
    log("db_query done")  # deep in the call stack, never received the id


async def handle_request(rid: str) -> None:
    global GLOBAL_REQUEST_ID
    request_id.set(rid)
    GLOBAL_REQUEST_ID = rid
    log("start")
    await db_query()
    log("end")


async def demo_isolation() -> None:
    section("1. 3 concurrent requests: contextvar stays correct, global gets clobbered")
    async with asyncio.TaskGroup() as tg:
        for rid in ("req-A", "req-B", "req-C"):
            tg.create_task(handle_request(rid))
    print("=> 'req' column always matches its own request; 'global' shows the last writer.")


async def demo_copy_semantics() -> None:
    section("2. Tasks get a COPY: child's set() doesn't leak to parent")
    request_id.set("parent")

    async def child() -> None:
        log("child sees parent's value at spawn time")
        request_id.set("child")
        log("child after set()")

    await asyncio.create_task(child())
    log("parent after child task finished - unchanged")

    async def plain_callee() -> None:
        request_id.set("callee")

    await plain_callee()  # no task -> same context
    log("parent after plain `await callee()` - CHANGED (same context)")


async def demo_middleware_pattern() -> None:
    section("3. Middleware pattern: set + reset with a Token")

    async def middleware(rid: str) -> None:
        token = request_id.set(rid)
        try:
            log("handling inside middleware")
        finally:
            request_id.reset(token)  # restore whatever was there before

    request_id.set("outer")
    await middleware("req-Z")
    log("after middleware - restored")


async def demo_to_thread() -> None:
    section("4. to_thread copies the context into the worker thread")
    request_id.set("req-T")

    def sync_work() -> None:
        time.sleep(0.01)
        log("inside a worker thread via to_thread")

    await asyncio.to_thread(sync_work)


async def main() -> None:
    await demo_isolation()
    await demo_copy_semantics()
    await demo_middleware_pattern()
    await demo_to_thread()


if __name__ == "__main__":
    asyncio.run(main())
