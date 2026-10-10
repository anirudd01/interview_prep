"""
06 - async with, async for, async generators, asynccontextmanager
==================================================================

Run:  python scripts/async/06_async_iterators_and_context_managers.py

WHY THESE EXIST
---------------
Regular `with` calls __enter__/__exit__ synchronously - you can't await inside.
Opening a DB connection, acquiring a pool slot, or committing a transaction is
I/O, so it needs `async with` -> __aenter__/__aexit__ (both coroutines).
Same for iteration: pulling the next page from an API / next Kafka batch / next
row from a server-side cursor is I/O -> `async for` -> __aiter__/__anext__.

WHERE YOU'VE ALREADY USED THEM
------------------------------
  async with httpx.AsyncClient() as client:      # connection pool lifecycle
  async with engine.begin() as conn:             # SQLAlchemy transaction
  async with session.begin():                    # commit on success / rollback on error
  async for msg in consumer:                     # aiokafka consumer
  FastAPI `lifespan` = an @asynccontextmanager: code before `yield` is startup,
  after `yield` is shutdown. FastAPI `Depends` with `yield` works the same way
  per request (that's how your request-scoped DB session closes).

INTERVIEW GOTCHAS
-----------------
- An async generator abandoned mid-iteration (you `break` out) is not closed
  right away; its `finally` runs when it's GC'd or at loop shutdown
  (asyncio.run calls loop.shutdown_asyncgens()). If the finally releases a
  connection, that's a leak window. Fix: `contextlib.aclosing(gen)` (3.10+).
- Async generators are great for streaming responses (FastAPI StreamingResponse,
  SSE, LLM token streaming) - each `yield` sends a chunk without buffering it all.
"""

import asyncio
import contextlib
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# 1. Class-based async context manager
# ---------------------------------------------------------------------------
class FakeTransaction:
    """What `async with session.begin():` does for you."""

    async def __aenter__(self) -> "FakeTransaction":
        await asyncio.sleep(0.01)  # BEGIN round-trip
        print(f"{t()} BEGIN")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await asyncio.sleep(0.01)
        if exc_type is None:
            print(f"{t()} COMMIT")
        else:
            print(f"{t()} ROLLBACK because {exc_type.__name__}: {exc}")
        return False  # False = don't suppress the exception


async def demo_class_cm() -> None:
    section("1. __aenter__/__aexit__: commit on success, rollback on error")
    async with FakeTransaction():
        print(f"{t()}   insert order")
    try:
        async with FakeTransaction():
            print(f"{t()}   insert order")
            raise ValueError("payment declined")
    except ValueError:
        print(f"{t()} caller still sees the error (we returned False)")


# ---------------------------------------------------------------------------
# 2. @asynccontextmanager: the same thing, as a generator. Exactly like FastAPI lifespan.
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def lifespan(app_name: str):
    print(f"{t()} [{app_name}] startup: open DB pool, warm caches, load model")
    pool = {"connections": 10}
    try:
        yield pool  # <- the app runs here
    finally:
        print(f"{t()} [{app_name}] shutdown: drain + close DB pool")


async def demo_asynccontextmanager() -> None:
    section("2. @asynccontextmanager == FastAPI lifespan pattern")
    async with lifespan("api") as pool:
        print(f"{t()}   serving requests with pool={pool}")


# ---------------------------------------------------------------------------
# 3. Async generators: pagination + streaming
# ---------------------------------------------------------------------------
async def paginate(total_pages: int):
    """Yield items page by page; next page is fetched only when consumer needs it."""
    try:
        for page in range(1, total_pages + 1):
            await asyncio.sleep(0.05)  # GET /items?page=N
            print(f"{t()}   fetched page {page}")
            for item in range(3):
                yield f"p{page}-item{item}"
    finally:
        print(f"{t()}   paginate: cleanup (closing HTTP client)")


async def demo_async_generator() -> None:
    section("3a. async for over an async generator (lazy pagination)")
    async for item in paginate(2):
        print(f"{t()} got {item}")

    section("3b. async comprehension")
    items = [i async for i in paginate(1) if i.endswith("1")]
    print(f"filtered: {items}")


async def demo_early_break() -> None:
    section("4. Breaking early: use aclosing() so cleanup runs NOW, not at GC")
    async with contextlib.aclosing(paginate(5)) as gen:
        async for item in gen:
            print(f"{t()} got {item}")
            if item == "p1-item1":
                print(f"{t()} found it, break")
                break
    print(f"{t()} after block - cleanup already ran above")


# ---------------------------------------------------------------------------
# 4. Streaming tokens (LLM / SSE shape)
# ---------------------------------------------------------------------------
async def llm_stream(prompt: str):
    for token in f"Answer to '{prompt}' streamed token by token".split():
        await asyncio.sleep(0.03)
        yield token + " "


async def demo_streaming() -> None:
    section("5. Streaming like an LLM / SSE endpoint")
    # In FastAPI: return StreamingResponse(llm_stream(q), media_type="text/event-stream")
    async for tok in llm_stream("what is RAG"):
        print(tok, end="", flush=True)
    print()


async def main() -> None:
    await demo_class_cm()
    await demo_asynccontextmanager()
    await demo_async_generator()
    await demo_early_break()
    await demo_streaming()


if __name__ == "__main__":
    asyncio.run(main())
